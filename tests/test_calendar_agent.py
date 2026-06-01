"""Tests for Calendar Agent and related services."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date, datetime, timedelta
import tempfile
import os
import json

from src.services.calendar_session_manager import CalendarState, calendar_session_manager

# Test CalendarService
class TestCalendarService:
    """Tests for CalendarService CRUD operations."""

    @pytest.fixture
    def temp_data_path(self):
        """Create temporary directory for test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def calendar_service(self, temp_data_path):
        """Create CalendarService instance with temp storage."""
        from src.services.calendar_service import CalendarService
        
        # CalendarService uses constructor for configuration
        service = CalendarService(local_storage_path=temp_data_path)
        return service

    def test_add_event(self, calendar_service):
        """Test adding a calendar event."""
        user_id = "U123456"
        chat_id = "user_U123456"
        # Use future date relative to today to avoid is_past() filtering
        future_date = date.today() + timedelta(days=30)
        event = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Test Event",
            event_date=future_date,
            description="Test description",
            reminder_days=[7, 3, 1, 0],
        )
        
        assert event is not None
        assert event.event_id is not None
        assert len(event.event_id) > 0

    def test_get_user_events(self, calendar_service):
        """Test retrieving user's events."""
        user_id = "U123456"
        chat_id = "user_U123456"
        
        # Use future dates relative to today to avoid is_past() filtering
        future_date_1 = date.today() + timedelta(days=30)
        future_date_2 = date.today() + timedelta(days=60)
        
        # Add some events
        calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Event 1",
            event_date=future_date_1,
        )
        calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Event 2",
            event_date=future_date_2,
        )
        
        events = calendar_service.get_user_events(user_id)
        
        assert len(events) == 2
        assert any(e.title == "Event 1" for e in events)
        assert any(e.title == "Event 2" for e in events)

    def test_get_user_events_empty(self, calendar_service):
        """Test retrieving events for user with no events."""
        events = calendar_service.get_user_events("U_NO_EVENTS")
        assert len(events) == 0

    def test_remove_events_by_ids(self, calendar_service):
        """Test removing events by their IDs."""
        user_id = "U123456"
        chat_id = "user_U123456"
        
        # Use future dates relative to today to avoid is_past() filtering
        future_date_1 = date.today() + timedelta(days=30)
        future_date_2 = date.today() + timedelta(days=60)
        
        # Add events
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Event 1",
            event_date=future_date_1,
        )
        event2 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Event 2",
            event_date=future_date_2,
        )
        
        # Remove first event (note: argument order is event_ids, user_id)
        removed_count, failed_count = calendar_service.remove_events_by_ids([event1.event_id], user_id)
        
        assert removed_count == 1
        assert failed_count == 0
        
        events = calendar_service.get_user_events(user_id)
        assert len(events) == 1
        assert events[0].title == "Event 2"

    def test_remove_events_wrong_user(self, calendar_service):
        """Test that user cannot remove another user's events."""
        user_id1 = "U123456"
        user_id2 = "U789012"
        chat_id = "user_U123456"
        
        # Use future date relative to today to avoid is_past() filtering
        future_date = date.today() + timedelta(days=30)
        
        event = calendar_service.add_event(
            user_id=user_id1,
            chat_id=chat_id,
            title="User 1 Event",
            event_date=future_date,
        )
        
        # Try to remove with different user (note: argument order is event_ids, user_id)
        removed_count, failed_count = calendar_service.remove_events_by_ids([event.event_id], user_id2)
        
        assert removed_count == 0
        assert failed_count == 1  # The removal should fail
        
        # Event should still exist
        events = calendar_service.get_user_events(user_id1)
        assert len(events) == 1

    def test_get_events_needing_reminder(self, calendar_service):
        """Test retrieving events that need reminders."""
        user_id = "U123456"
        chat_id = "user_U123456"
        
        # Add event with reminder today (0 days before)
        today = date.today()
        event = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Today's Event",
            event_date=today,
            reminder_days=[0],  # Remind on the day
        )
        
        # Get events needing reminder for 0 days before
        events = calendar_service.get_events_needing_reminder(days_before=0)
        
        # Should find the event (reminder_days includes 0, which is today)
        assert any(e.event_id == event.event_id for e in events)

    def test_mark_event_notified(self, calendar_service):
        """Test marking an event as notified for a specific reminder day."""
        user_id = "U123456"
        chat_id = "user_U123456"
        
        event = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Test Event",
            event_date=date.today() + timedelta(days=7),
            reminder_days=[7, 3, 1, 0],
        )
        
        # Mark as notified for 7-day reminder
        calendar_service.mark_event_notified(event.event_id, days_before=7)
        
        # Get the event and check notified dates
        events = calendar_service.get_user_events(user_id)
        event = next(e for e in events if e.event_id == event.event_id)
        
        # Check that the reminder date is in notified_dates
        reminder_date = (event.event_date - timedelta(days=7)).isoformat()
        assert reminder_date in event.notified_dates


class TestCalendarSessionManager:
    """Tests for CalendarSessionManager state management."""

    @pytest.fixture
    def session_manager(self):
        """Create CalendarSessionManager instance."""
        from src.services.calendar_session_manager import calendar_session_manager
        return calendar_session_manager

    def test_start_add_flow(self, session_manager):
        """Test starting add event flow."""
        chat_id = "test_chat_123"
        user_id = "U123456"
        
        session_manager.start_add_flow(chat_id, user_id)
        
        assert session_manager.is_in_calendar_flow(chat_id)
        session = session_manager.get_session(chat_id)
        assert session is not None
        assert session.user_id == user_id
        
        # Cleanup
        session_manager.end_session(chat_id)

    def test_start_removal_flow(self, session_manager):
        """Test starting remove events flow."""
        chat_id = "test_chat_789"
        user_id = "U123456"
        events = [{"event_id": "test1", "title": "Test Event"}]
        
        session_manager.start_removal_flow(chat_id, user_id, events)
        
        assert session_manager.is_in_calendar_flow(chat_id)
        
        # Cleanup
        session_manager.end_session(chat_id)

    def test_session_ownership(self, session_manager):
        """Test that only session owner can interact."""
        chat_id = "test_chat_ownership"
        user_id1 = "U123456"
        user_id2 = "U789012"
        
        session_manager.start_add_flow(chat_id, user_id1)
        
        assert session_manager.is_session_owner(chat_id, user_id1)
        assert not session_manager.is_session_owner(chat_id, user_id2)
        
        # Cleanup
        session_manager.end_session(chat_id)

    def test_end_session(self, session_manager):
        """Test ending calendar session."""
        chat_id = "test_chat_end"
        user_id = "U123456"
        
        session_manager.start_add_flow(chat_id, user_id)
        assert session_manager.is_in_calendar_flow(chat_id)
        
        session_manager.end_session(chat_id)
        assert not session_manager.is_in_calendar_flow(chat_id)


class TestCalendarAgent:
    """Tests for CalendarAgent message handling."""

    @pytest.fixture
    def calendar_agent(self):
        """Create CalendarAgent instance."""
        from src.agents.calendar_agent import CalendarAgent
        import src.agents.calendar.remove_flow as remove_flow_module

        remove_flow_module._remove_flow_instance = None
        return CalendarAgent()

    @pytest.fixture
    def mock_event(self):
        """Create mock LINE MessageEvent."""
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123456"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "test_reply_token"
        event.message = MagicMock()
        event.message.text = "test"
        return event

    @pytest.fixture
    def mock_line_api(self):
        """Create mock LINE MessagingApi."""
        return MagicMock()

    @pytest.fixture(autouse=True)
    def cleanup_calendar_chat(self):
        calendar_session_manager.end_session("user_U123456")
        calendar_session_manager.end_session("group_G123")
        yield
        calendar_session_manager.end_session("user_U123456")
        calendar_session_manager.end_session("group_G123")

    @pytest.mark.asyncio
    async def test_should_handle_view_trigger(self, calendar_agent, mock_event):
        """Test that agent handles view triggers."""
        # Test various view triggers
        view_triggers = [
            "Ms. Green calendar",
            "my events",
            "my reminders",
            "Ms. Green my calendar",
        ]
        
        for trigger in view_triggers:
            result = await calendar_agent.should_handle(mock_event, trigger)
            assert result is True, f"Should handle: {trigger}"

    @pytest.mark.asyncio
    async def test_should_handle_add_trigger(self, calendar_agent, mock_event):
        """Test that agent handles add triggers."""
        add_triggers = [
            "Ms. Green add event",
            "Ms. Green remind me",
            "Ms. Green calendar add",
        ]
        
        for trigger in add_triggers:
            result = await calendar_agent.should_handle(mock_event, trigger)
            assert result is True, f"Should handle: {trigger}"

    @pytest.mark.asyncio
    async def test_should_handle_remove_trigger(self, calendar_agent, mock_event):
        """Test that agent handles remove triggers."""
        remove_triggers = [
            "Ms. Green remove event",
            "Ms. Green delete event",
            "Ms. Green calendar remove",
        ]
        
        for trigger in remove_triggers:
            result = await calendar_agent.should_handle(mock_event, trigger)
            assert result is True, f"Should handle: {trigger}"

    @pytest.mark.asyncio
    async def test_should_not_handle_random_text(self, calendar_agent, mock_event):
        """Test that agent ignores unrelated messages."""
        random_texts = [
            "hello",
            "translate this",
            "zeus search something",
            "news",
        ]
        
        for text in random_texts:
            result = await calendar_agent.should_handle(mock_event, text)
            assert result is False, f"Should not handle: {text}"

    @pytest.mark.asyncio
    async def test_should_not_handle_instructional_text(self, calendar_agent, mock_event):
        """Test that agent ignores instructional text containing trigger phrases.
        
        CRITICAL: This test ensures the trigger fix is working correctly.
        Previously, substring matching caused false positives like:
        'you can say zeus add event' triggering the calendar agent.
        """
        instructional_texts = [
            "If you guys have any important events you would like zeus to remind you of just say zeus add event IN A DM TO ZEUS",
            "you can say zeus add event to create a reminder",
            "just say zeus scrape to scan messages",
            "try using zeus remove event to delete",
            "the command is zeus calendar but you need to DM",
            "say zeus events to see your calendar",
        ]
        
        for text in instructional_texts:
            result = await calendar_agent.should_handle(mock_event, text)
            assert result is False, f"Should NOT handle instructional text: {text}"

    @pytest.mark.asyncio
    async def test_routes_remove_selection_and_preview_with_done(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )
        calendar_agent.remove_flow.send_message = AsyncMock()
        calendar_agent.remove_flow.send_message_with_quick_reply = AsyncMock()

        handled = await calendar_agent.handle(mock_event, "1", mock_line_api)
        assert handled is True

        handled = await calendar_agent.handle(mock_event, "done", mock_line_api)

        assert handled is True
        session = calendar_session_manager.get_session("user_U123456")
        assert session is not None
        assert session.state == CalendarState.CONFIRMING_REMOVAL

    @pytest.mark.asyncio
    async def test_mixed_remove_selection_is_rejected_through_agent_routing(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )

        should_handle = await calendar_agent.should_handle(mock_event, "1,done")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "1,done", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "invalid selection" in reply_text

    @pytest.mark.asyncio
    async def test_unrelated_comma_text_is_not_hijacked_during_remove_session(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )

        should_handle = await calendar_agent.should_handle(mock_event, "1,000 students attended")

        assert should_handle is False

        handled = await calendar_agent.handle(mock_event, "1,000 students attended", mock_line_api)

        assert handled is False
        mock_line_api.reply_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_keyword_prefixed_mixed_remove_input_is_rejected_during_remove_session(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )

        should_handle = await calendar_agent.should_handle(mock_event, "1, done please")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "1, done please", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "invalid selection" in reply_text

    @pytest.mark.asyncio
    async def test_stale_delete_code_is_rejected_after_session_is_gone(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("user_U123456")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("user_U123456") is None

        should_handle = await calendar_agent.should_handle(mock_event, "delete deadbeef")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "delete deadbeef", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_delete_code_without_remove_context_falls_through(self, calendar_agent, mock_event):
        should_handle = await calendar_agent.should_handle(mock_event, "delete deadbeef")

        assert should_handle is False

    @pytest.mark.asyncio
    async def test_stale_remove_selection_followup_is_rejected_after_session_is_gone(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("user_U123456")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("user_U123456") is None

        should_handle = await calendar_agent.should_handle(mock_event, "1,3")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "1,3", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_done_without_remove_context_still_falls_through(self, calendar_agent, mock_event):
        should_handle = await calendar_agent.should_handle(mock_event, "done")

        assert should_handle is False

    @pytest.mark.asyncio
    async def test_recent_remove_expiry_does_not_hijack_other_user(self, calendar_agent, mock_event):
        mock_event.source.group_id = "G123"
        mock_event.source.user_id = "U_OWNER"
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("group_G123") is None

        mock_event.source.user_id = "U_OTHER"

        should_handle = await calendar_agent.should_handle(mock_event, "done")

        assert should_handle is False

    @pytest.mark.asyncio
    async def test_cancel_does_not_get_hijacked_after_recent_remove_expiry(self, calendar_agent, mock_event):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("user_U123456")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("user_U123456") is None

        should_handle = await calendar_agent.should_handle(mock_event, "cancel")

        assert should_handle is False

    @pytest.mark.asyncio
    async def test_starting_and_canceling_add_flow_clears_recent_remove_marker(self, calendar_agent, mock_event):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("user_U123456")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("user_U123456") is None

        calendar_session_manager.start_add_flow("user_U123456", "U123456")
        assert calendar_session_manager.cancel_flow("user_U123456") is True

        should_handle = await calendar_agent.should_handle(mock_event, "done")

        assert should_handle is False

    @pytest.mark.asyncio
    async def test_other_user_new_flow_does_not_clear_expired_owner_remove_context(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_agent.remove_flow.send_message = AsyncMock()
        mock_event.source.group_id = "G123"
        mock_event.source.user_id = "U_OWNER"
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("group_G123") is None

        calendar_session_manager.start_add_flow("group_G123", "U_OTHER")
        assert calendar_session_manager.cancel_flow("group_G123") is True

        mock_event.source.user_id = "U_OWNER"

        should_handle = await calendar_agent.should_handle(mock_event, "done")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "done", mock_line_api)

        assert handled is True
        calendar_agent.remove_flow.send_message.assert_awaited_once()
        reply_text = calendar_agent.remove_flow.send_message.await_args.args[2].lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_preview_yes_gets_explicit_delete_or_cancel_guidance(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        should_handle = await calendar_agent.should_handle(mock_event, "yes")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "yes", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "delete <code>" in reply_text
        assert "cancel" in reply_text

    @pytest.mark.asyncio
    async def test_preview_done_gets_explicit_delete_or_cancel_guidance(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        handled = await calendar_agent.handle(mock_event, "done", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "delete <code>" in reply_text
        assert "cancel" in reply_text

    @pytest.mark.asyncio
    async def test_preview_cancel_alias_ends_remove_flow(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        handled = await calendar_agent.handle(mock_event, "quit", mock_line_api)

        assert handled is True
        assert calendar_session_manager.get_session("user_U123456") is None
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "no events were removed" in reply_text

    @pytest.mark.asyncio
    async def test_done_after_remove_cancel_gets_stale_response(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        handled = await calendar_agent.handle(mock_event, "quit", mock_line_api)

        assert handled is True
        assert calendar_session_manager.get_session("user_U123456") is None

        mock_line_api.reset_mock()

        should_handle = await calendar_agent.should_handle(mock_event, "done")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "done", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_all_and_none_after_remove_cancel_get_stale_response(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        handled = await calendar_agent.handle(mock_event, "quit", mock_line_api)

        assert handled is True
        assert calendar_session_manager.get_session("user_U123456") is None

        for text in ("all", "none"):
            mock_line_api.reset_mock()
            should_handle = await calendar_agent.should_handle(mock_event, text)
            assert should_handle is True

            handled = await calendar_agent.handle(mock_event, text, mock_line_api)

            assert handled is True
            mock_line_api.reply_message.assert_called_once()
            reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
            assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_plain_yes_after_remove_cancel_falls_through(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        handled = await calendar_agent.handle(mock_event, "quit", mock_line_api)

        assert handled is True
        assert calendar_session_manager.get_session("user_U123456") is None

        for text in ("yes", "no", "ใช่", "ไม่"):
            should_handle = await calendar_agent.should_handle(mock_event, text)
            assert should_handle is False

    @pytest.mark.asyncio
    async def test_plain_numeric_reply_after_remove_cancel_falls_through(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")

        handled = await calendar_agent.handle(mock_event, "quit", mock_line_api)

        assert handled is True
        assert calendar_session_manager.get_session("user_U123456") is None

        should_handle = await calendar_agent.should_handle(mock_event, "1")

        assert should_handle is False

    @pytest.mark.asyncio
    async def test_delete_code_after_remove_success_gets_stale_response(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        preview = calendar_session_manager.finalize_remove_selection("user_U123456")
        assert preview is not None
        calendar_agent._calendar_service = MagicMock()
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        handled = await calendar_agent.handle(mock_event, f"delete {preview['code']}", mock_line_api)

        assert handled is True
        assert calendar_session_manager.get_session("user_U123456") is None

        mock_line_api.reset_mock()

        should_handle = await calendar_agent.should_handle(mock_event, f"delete {preview['code']}")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, f"delete {preview['code']}", mock_line_api)

        assert handled is True
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_non_owner_cannot_confirm_remove_preview(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        preview = calendar_session_manager.finalize_remove_selection("user_U123456")
        calendar_agent._calendar_service = MagicMock()
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        assert preview is not None
        handled = await calendar_agent.handle(mock_event, f"delete {preview['code']}", mock_line_api)

        assert handled is True
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async.assert_not_awaited()
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "only the person who started this removal flow" in reply_text

    @pytest.mark.asyncio
    async def test_stale_remove_preview_returns_explicit_error(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        preview = calendar_session_manager.finalize_remove_selection("user_U123456")
        calendar_agent._calendar_service = MagicMock()
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        assert preview is not None
        handled = await calendar_agent.handle(mock_event, "delete deadbeef", mock_line_api)

        assert handled is True
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async.assert_not_awaited()
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_old_delete_code_is_rejected_after_reselection(self, calendar_agent, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )
        calendar_agent._calendar_service = MagicMock()
        calendar_agent.remove_flow._calendar_service = calendar_agent._calendar_service
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        preview = calendar_session_manager.finalize_remove_selection("user_U123456")
        assert preview is not None

        calendar_session_manager.apply_remove_selection("user_U123456", "2")

        handled = await calendar_agent.handle(mock_event, f"delete {preview['code']}", mock_line_api)

        assert handled is True
        calendar_agent.remove_flow._calendar_service.remove_events_by_ids_async.assert_not_awaited()
        mock_line_api.reply_message.assert_called_once()
        reply_text = mock_line_api.reply_message.call_args[0][0].messages[0].text.lower()
        assert "stale or expired" in reply_text

    @pytest.mark.asyncio
    async def test_unrelated_group_text_is_ignored_during_remove_session(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        mock_event.source.group_id = "G123"
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )

        should_handle = await calendar_agent.should_handle(mock_event, "hello everyone")

        assert should_handle is False

        handled = await calendar_agent.handle(mock_event, "hello everyone", mock_line_api)

        assert handled is False
        mock_line_api.reply_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_remove_trigger_restarts_active_remove_session(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "user_U123456",
            "U123456",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("user_U123456", "1")
        calendar_session_manager.finalize_remove_selection("user_U123456")
        calendar_agent.remove_flow.start_remove_flow = AsyncMock(return_value=True)

        should_handle = await calendar_agent.should_handle(mock_event, "Ms. Green remove event")

        assert should_handle is True

        handled = await calendar_agent.handle(mock_event, "Ms. Green remove event", mock_line_api)

        assert handled is True
        calendar_agent.remove_flow.start_remove_flow.assert_awaited_once_with(
            mock_event,
            mock_line_api,
            "user_U123456",
            "U123456",
        )

    @pytest.mark.asyncio
    async def test_inline_add_bulk_fallback_routes_to_scrape_flow_with_text_first(
        self,
        calendar_agent,
        mock_event,
        mock_line_api,
    ):
        calendar_agent.scrape_flow.handle_scrape_trigger = AsyncMock(return_value=True)

        with patch.object(calendar_agent, "_parse_inline_add", return_value=None), patch.object(
            calendar_agent,
            "_looks_like_bulk_dates",
            return_value=True,
        ):
            handled = await calendar_agent.handle(
                mock_event,
                "Ms. Green add tomorrow\n1. June 20 science fair\n2. June 21 parent meeting",
                mock_line_api,
            )

        assert handled is True
        calendar_agent.scrape_flow.handle_scrape_trigger.assert_awaited_once_with(
            mock_event,
            "Ms. Green add tomorrow\n1. June 20 science fair\n2. June 21 parent meeting",
            mock_line_api,
            "user_U123456",
            "U123456",
        )

    @pytest.mark.asyncio
    async def test_calendar_agent_accepts_configured_alias_prefix(self, calendar_agent, mock_event):
        result = await calendar_agent.should_handle(mock_event, "Ms. Green scrape")
        assert result is True

    def test_get_priority(self, calendar_agent):
        """Test agent priority."""
        assert calendar_agent.get_priority() == 6


class TestCalendarDeleteAndLiveBulkAdd:
    """Regression tests for delete flow and live bulk-add flow."""

    @pytest.mark.asyncio
    async def test_remove_confirmation_calls_service_with_user_id(self, monkeypatch):
        from src.agents.calendar_agent import CalendarAgent
        from src.services.calendar_session_manager import calendar_session_manager, CalendarState

        agent = CalendarAgent(calendar_service=MagicMock())
        agent._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(2, 0))

        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123456"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "reply"
        event.message = MagicMock()
        event.message.text = "delete deadbeef"

        line_api = MagicMock()

        chat_id = "user_U123456"
        # Seed a removal session
        session = calendar_session_manager.get_or_create_session(chat_id, "U123456")
        session.reset()
        session.state = CalendarState.CONFIRMING_REMOVAL
        session.events_for_removal = [
            {"event_id": "e1", "title": "Event 1", "date": "Jun 10"},
            {"event_id": "e2", "title": "Event 2", "date": "Jun 11"},
        ]
        session.selected_event_ids = ["e1", "e2"]
        session.removal_revision = 3
        session.removal_confirmation_code = "deadbeef"
        session.update()

        await agent.handle(event, "delete deadbeef", line_api)

        agent._calendar_service.remove_events_by_ids_async.assert_awaited_once_with(["e1", "e2"], "U123456")


    @pytest.mark.asyncio
    async def test_live_bulk_add_starts_listening_on_trigger(self, monkeypatch):
        from src.agents.calendar_agent import CalendarAgent
        from src.services.calendar_session_manager import calendar_session_manager, CalendarState

        agent = CalendarAgent(calendar_service=MagicMock())

        # Avoid friend check hitting LINE API
        async def _fake_is_friend(_event, _api):
            return False
        monkeypatch.setattr(agent, "_is_friend", _fake_is_friend)

        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123456"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "reply"
        event.message = MagicMock()
        event.message.text = "Ms. Green add event"

        line_api = MagicMock()
        chat_id = "user_U123456"

        # Ensure clean
        calendar_session_manager.end_session(chat_id)

        handled = await agent.handle(event, "Ms. Green add event", line_api)
        assert handled is True

        session = calendar_session_manager.get_session(chat_id)
        assert session is not None
        # "Ms. Green add event" now triggers interactive add flow, not live bulk add
        assert session.state == CalendarState.AWAITING_DATE


class TestReminderService:
    """Tests for ReminderService scheduling."""

    @pytest.fixture
    def temp_data_path(self):
        """Create temporary directory for test data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def reminder_service(self, temp_data_path):
        """Create ReminderService instance with mocked dependencies."""
        from src.services.reminder_service import ReminderService
        from src.services.calendar_service import CalendarService
        
        # Create mock LINE bot API
        mock_line_api = MagicMock()
        
        # Create real calendar service for testing
        calendar_service = CalendarService(local_storage_path=temp_data_path)
        
        service = ReminderService()
        service.configure(
            line_bot_api=mock_line_api,
            calendar_service=calendar_service,
            reminder_hour=8
        )
        return service

    def test_configure(self, reminder_service):
        """Test reminder service configuration."""
        assert reminder_service._reminder_hour == 8

    def test_format_reminder_message_urgent(self, reminder_service):
        """Test urgent reminder message formatting."""
        from src.services.calendar_service import CalendarEvent
        
        event = CalendarEvent(
            event_id="test123",
            user_id="U123456",
            chat_id="user_U123456",
            title="Important Meeting",
            event_date=date.today(),
            description="Team meeting",
            reminder_days=[0],
            notified_dates=[],
            created_at=datetime.now(),
        )
        
        message = reminder_service._format_reminder_message(event, days_until=0)
        
        assert "🚨" in message  # Urgent indicator
        assert "TODAY" in message or "Important Meeting" in message

    def test_format_reminder_message_upcoming(self, reminder_service):
        """Test upcoming reminder message formatting."""
        from src.services.calendar_service import CalendarEvent
        
        event = CalendarEvent(
            event_id="test123",
            user_id="U123456",
            chat_id="user_U123456",
            title="Future Event",
            event_date=date.today() + timedelta(days=7),
            description="Week away",
            reminder_days=[7],
            notified_dates=[],
            created_at=datetime.now(),
        )
        
        message = reminder_service._format_reminder_message(event, days_until=7)
        
        assert "📅" in message or "⏰" in message  # Calendar indicator
        assert "7" in message or "days" in message

    def test_stop_is_backward_compatible_without_scheduler(self, reminder_service):
        """Shutdown should tolerate legacy callers that invoke stop() directly."""
        reminder_service.stop()

        assert reminder_service._scheduler_job_id is None


class TestDateParsing:
    """Tests for date parsing in calendar flows."""

    def test_parse_iso_date(self):
        """Test parsing ISO format dates."""
        from dateutil.parser import parse
        
        result = parse("2025-06-15")
        assert result.date() == date(2025, 6, 15)

    def test_parse_natural_date(self):
        """Test parsing natural language dates."""
        from dateutil.parser import parse
        
        result = parse("June 15, 2025")
        assert result.date() == date(2025, 6, 15)

    def test_parse_thai_format(self):
        """Test parsing Thai-style dates (day/month/year)."""
        from dateutil.parser import parse
        
        # Note: dateutil may interpret this differently based on locale
        # We use dayfirst=True for Thai convention
        result = parse("15/06/2025", dayfirst=True)
        assert result.date() == date(2025, 6, 15)


class TestImageAnalyzerDateDetection:
    """Tests for date detection in ImageAnalyzerAgent."""

    @pytest.fixture
    def image_analyzer_agent(self):
        """Create ImageAnalyzerAgent instance."""
        from src.agents.image_analyzer_agent import ImageAnalyzerAgent
        return ImageAnalyzerAgent()

    def test_extract_dates_from_analysis(self, image_analyzer_agent):
        """Test extracting dates from analysis response."""
        analysis = """
        Here is what I see in the image: A school announcement with dates.
        
        ---DATES_DETECTED---
        [{"date": "2025-06-09", "title": "Final Grades Due", "description": "Submit all grades"}]
        ---END_DATES---
        """
        
        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)
        
        assert len(dates) == 1
        assert dates[0]["date"] == "2025-06-09"
        assert dates[0]["title"] == "Final Grades Due"

    def test_extract_multiple_dates(self, image_analyzer_agent):
        """Test extracting multiple dates."""
        analysis = """
        School calendar detected.
        
        ---DATES_DETECTED---
        [
            {"date": "2025-06-09", "title": "Final Grades", "description": ""},
            {"date": "2025-07-03", "title": "Enrollment", "description": "New student enrollment"}
        ]
        ---END_DATES---
        """
        
        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)
        
        assert len(dates) == 2
        assert dates[0]["date"] == "2025-06-09"
        assert dates[1]["date"] == "2025-07-03"

    def test_extract_no_dates(self, image_analyzer_agent):
        """Test when no dates are detected."""
        analysis = "This is just a regular image with no dates."
        
        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)
        
        assert len(dates) == 0

    def test_strip_dates_section(self, image_analyzer_agent):
        """Test stripping dates section from response."""
        analysis = """
        Here is the content.
        
        ---DATES_DETECTED---
        [{"date": "2025-06-09", "title": "Test", "description": ""}]
        ---END_DATES---
        """
        
        cleaned = image_analyzer_agent._strip_dates_section(analysis)
        
        assert "---DATES_DETECTED---" not in cleaned
        assert "Here is the content" in cleaned


class TestImageAnalyzerSessionManager:
    """Tests for ImageAnalyzerSessionManager date storage."""

    @pytest.fixture
    def session_manager(self):
        """Create ImageAnalyzerSessionManager instance."""
        from src.services.image_analyzer_session_manager import image_analyzer_session_manager
        return image_analyzer_session_manager

    def test_store_detected_dates(self, session_manager):
        """Test storing detected dates in session."""
        chat_id = "test_chat_dates"
        user_id = "U123456"
        
        session_manager.start_session(chat_id, user_id)
        
        dates = [
            {"date": "2025-06-09", "title": "Event 1", "description": ""},
            {"date": "2025-07-03", "title": "Event 2", "description": ""},
        ]
        
        session_manager.store_detected_dates(chat_id, dates)
        
        retrieved = session_manager.get_detected_dates(chat_id)
        assert len(retrieved) == 2
        assert retrieved[0]["title"] == "Event 1"

    def test_waiting_for_calendar_confirmation(self, session_manager):
        """Test calendar confirmation state."""
        chat_id = "test_chat_confirm"
        user_id = "U123456"
        
        session_manager.start_session(chat_id, user_id)
        session_manager.store_detected_dates(chat_id, [
            {"date": "2025-06-09", "title": "Test", "description": ""}
        ])
        
        assert session_manager.is_waiting_for_calendar_confirmation(chat_id)

    def test_clear_session_clears_dates(self, session_manager):
        """Test that clearing session also clears detected dates."""
        chat_id = "test_chat_clear"
        user_id = "U123456"
        
        session_manager.start_session(chat_id, user_id)
        session_manager.store_detected_dates(chat_id, [
            {"date": "2025-06-09", "title": "Test", "description": ""}
        ])
        
        session_manager.clear_session(chat_id)
        
        retrieved = session_manager.get_detected_dates(chat_id)
        assert len(retrieved) == 0
