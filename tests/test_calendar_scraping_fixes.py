"""
Test suite for Calendar Scraping and Event Deletion features.

Tests the following functionality:
1. Date extraction with dateparser integration
2. JSON parsing improvements for GPT responses
3. Event deletion flow
4. Bulk event addition with intelligent mode selection
5. "Dear all, meeting on Friday" pattern detection
"""

import pytest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from src.services.date_extraction_service import date_extraction_service
from src.services.calendar_service import calendar_service
from src.services.calendar_session_manager import calendar_session_manager, CalendarState


class TestDateExtraction:
    """Test date extraction improvements."""
    
    @pytest.mark.asyncio
    async def test_extract_from_dear_all_meeting_format(self):
        """Test extraction from 'Dear all, meeting on Friday' format."""
        # Use explicit date format that regex can parse
        tomorrow = date.today() + timedelta(days=1)
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        
        messages = [
            f"Dear all, team standup meeting on {tomorrow_str}"
        ]
        
        events = await date_extraction_service.extract_events_from_messages(messages)
        
        # Should extract at least the meeting (fallback uses regex for ISO dates)
        assert len(events) > 0
        # Should have a date in the future
        assert all(evt.event_date >= date.today() for evt in events)
    
    @pytest.mark.asyncio
    async def test_year_validation_rejects_yyyy_placeholder(self):
        """Test that YYYY placeholders in dates are rejected."""
        # Simulate a bad GPT response with YYYY placeholder
        bad_json = '''[
            {"date": "YYYY-01-15", "title": "Test Event", "description": "", "source_text": "test", "confidence": "high"}
        ]'''
        
        today = date.today()
        events = date_extraction_service._parse_extraction_response(bad_json, today)
        
        # Should reject the event with YYYY placeholder
        assert len(events) == 0
    
    @pytest.mark.asyncio
    async def test_json_parsing_with_markdown_blocks(self):
        """Test JSON parsing handles markdown code blocks."""
        json_with_markdown = '''```json
        [
            {"date": "2026-01-15", "title": "Test Event", "description": "", "source_text": "test", "confidence": "high"}
        ]
        ```'''
        
        today = date(2026, 1, 1)
        events = date_extraction_service._parse_extraction_response(json_with_markdown, today)
        
        assert len(events) == 1
        assert events[0].title == "Test Event"
        assert events[0].event_date == date(2026, 1, 15)
    
    @pytest.mark.asyncio
    async def test_dateparser_fallback_for_relative_dates(self):
        """Test that dateparser handles relative dates like 'tomorrow', 'next Friday'."""
        messages = [
            "Meeting tomorrow at 2pm",
            "Review session next Friday"
        ]
        
        events = await date_extraction_service.extract_events_from_messages(messages)
        
        # Should extract at least one event
        assert len(events) > 0
        # Events should be in the future
        today = date.today()
        assert all(evt.event_date >= today for evt in events)
    
    @pytest.mark.asyncio
    async def test_enhanced_title_extraction(self):
        """Test improved title extraction from context."""
        # Use explicit dates that regex can parse
        tomorrow = date.today() + timedelta(days=1)
        day_after = date.today() + timedelta(days=2)
        
        messages = [
            f"Dear all, quarterly review meeting on {tomorrow.strftime('%Y-%m-%d')}",
            f"Everyone, project deadline is {day_after.strftime('%Y-%m-%d')}"
        ]
        
        events = await date_extraction_service.extract_events_from_messages(messages)
        
        # Should extract events
        assert len(events) >= 1
        
        # Titles should not be just "Event" - should have some meaningful text
        titles = [evt.title.lower() for evt in events]
        assert all(len(t) > 5 for t in titles)  # More than just "Event"


class TestEventDeletion:
    """Test event deletion functionality."""
    
    def setup_method(self):
        """Clear calendar before each test."""
        # Clear all events for test user
        self.test_user_id = "test_user_deletion_123"
        self.test_chat_id = f"user_{self.test_user_id}"
        
        # Clean up any existing events from previous tests
        events = calendar_service.get_user_events(self.test_user_id)
        for event in events:
            calendar_service.remove_event(event.event_id, self.test_user_id)
    
    def test_remove_single_event(self):
        """Test removing a single event."""
        # Add an event
        event = calendar_service.add_event(
            user_id=self.test_user_id,
            chat_id=self.test_chat_id,
            title="Test Event to Delete",
            event_date=date.today() + timedelta(days=7),
            description="This should be deleted",
            reminder_days=[1],
            is_friend=True
        )
        
        # Verify event was added
        events = calendar_service.get_user_events(self.test_user_id)
        assert len(events) == 1
        
        # Remove the event
        success = calendar_service.remove_event(event.event_id, self.test_user_id)
        assert success is True
        
        # Verify event was removed
        events = calendar_service.get_user_events(self.test_user_id)
        assert len(events) == 0
    
    def test_remove_multiple_events(self):
        """Test removing multiple events by IDs."""
        # Add multiple events
        event1 = calendar_service.add_event(
            user_id=self.test_user_id,
            chat_id=self.test_chat_id,
            title="Event 1",
            event_date=date.today() + timedelta(days=1),
            reminder_days=[1],
            is_friend=True
        )
        
        event2 = calendar_service.add_event(
            user_id=self.test_user_id,
            chat_id=self.test_chat_id,
            title="Event 2",
            event_date=date.today() + timedelta(days=2),
            reminder_days=[1],
            is_friend=True
        )
        
        event3 = calendar_service.add_event(
            user_id=self.test_user_id,
            chat_id=self.test_chat_id,
            title="Event 3",
            event_date=date.today() + timedelta(days=3),
            reminder_days=[1],
            is_friend=True
        )
        
        # Remove two events
        removed, failed = calendar_service.remove_events_by_ids(
            [event1.event_id, event2.event_id],
            self.test_user_id
        )
        
        assert removed == 2
        assert failed == 0
        
        # Verify only one event remains
        events = calendar_service.get_user_events(self.test_user_id)
        assert len(events) == 1
        assert events[0].event_id == event3.event_id
    
    def test_cannot_delete_other_users_event(self):
        """Test that users cannot delete other users' events."""
        # Add event for user 1
        event = calendar_service.add_event(
            user_id=self.test_user_id,
            chat_id=self.test_chat_id,
            title="User 1 Event",
            event_date=date.today() + timedelta(days=1),
            reminder_days=[1],
            is_friend=True
        )
        
        # Try to delete as user 2
        other_user_id = "other_user_456"
        success = calendar_service.remove_event(event.event_id, other_user_id)
        
        # Should fail
        assert success is False
        
        # Event should still exist
        events = calendar_service.get_user_events(self.test_user_id)
        assert len(events) == 1


class TestCalendarSessionManager:
    """Test session manager state handling."""
    
    def setup_method(self):
        """Clear sessions before each test."""
        self.test_chat_id = "test_chat_789"
        self.test_user_id = "test_user_789"
        calendar_session_manager.end_session(self.test_chat_id)
    
    def test_add_mode_selection_state(self):
        """Test ADD_MODE_SELECTION state is properly set."""
        calendar_session_manager.start_add_mode_selection(
            self.test_chat_id,
            self.test_user_id,
            is_friend=True
        )
        
        session = calendar_session_manager.get_session(self.test_chat_id)
        assert session is not None
        assert session.state == CalendarState.ADD_MODE_SELECTION
        assert session.pending_is_friend is True
    
    def test_removal_flow_states(self):
        """Test event removal state transitions."""
        # Start removal flow
        events_data = [
            {"event_id": "evt1", "title": "Event 1", "date": "Jan 15"},
            {"event_id": "evt2", "title": "Event 2", "date": "Jan 16"},
        ]
        
        calendar_session_manager.start_removal_flow(
            self.test_chat_id,
            self.test_user_id,
            events_data
        )
        
        session = calendar_session_manager.get_session(self.test_chat_id)
        assert session is not None
        assert session.state == CalendarState.AWAITING_REMOVAL_SELECTION
        assert len(session.events_for_removal) == 2
        
        # Set removal selection
        calendar_session_manager.set_removal_selection(
            self.test_chat_id,
            ["evt1", "evt2"]
        )
        
        session = calendar_session_manager.get_session(self.test_chat_id)
        assert session is not None
        assert session.state == CalendarState.CONFIRMING_REMOVAL
        assert len(session.selected_event_ids) == 2


class TestBulkEventAddition:
    """Test bulk event addition with intelligent mode selection."""
    
    @pytest.mark.asyncio
    async def test_event_like_message_detection(self):
        """Test detection of event-like messages."""
        from src.agents.calendar_agent import CalendarAgent
        
        agent = CalendarAgent()
        
        # Should detect as event-like
        assert agent._looks_like_event_message("Team meeting on Friday")
        assert agent._looks_like_event_message("Deadline tomorrow")
        assert agent._looks_like_event_message("Dear all, workshop next week")
        
        # Should NOT detect as event-like
        assert not agent._looks_like_event_message("Hello")
        assert not agent._looks_like_event_message("How are you?")
        assert not agent._looks_like_event_message("zeus calendar")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
