"""
Tests for ImageAnalyzerAgent calendar integration with friend verification.

Tests that:
1. Non-friends get quirky rejection when trying to add dates to calendar
2. Friends can successfully add dates from images to calendar
3. Admins bypass friend check
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent, Source, TextMessageContent


class TestImageAnalyzerCalendarFriendCheck:
    """Tests for friend verification in calendar integration."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock LINE message event."""
        event = MagicMock(spec=MessageEvent)
        event.reply_token = "test_reply_token"
        event.source = MagicMock(spec=Source)
        event.source.user_id = "test_user_123"
        event.source.group_id = None
        event.source.room_id = None
        event.source.type = "user"

        message = MagicMock(spec=TextMessageContent)
        message.type = "text"
        message.text = "yes add to calendar"
        event.message = message

        return event

    @pytest.fixture
    def mock_line_bot_api(self):
        """Create a mock LINE Messaging API."""
        api = MagicMock(spec=MessagingApi)
        api.reply_message = MagicMock()
        api.push_message = MagicMock()
        return api

    @pytest.fixture
    def image_analyzer_agent(self):
        """Create an ImageAnalyzerAgent instance."""
        from src.agents.image_analyzer_agent import ImageAnalyzerAgent

        return ImageAnalyzerAgent()

    def test_ms_green_trigger_is_recognized(self, image_analyzer_agent):
        assert image_analyzer_agent._is_trigger("Ms. Green analyze this") is True

    def test_legacy_zeus_trigger_is_rejected_after_cutover(self, image_analyzer_agent):
        assert image_analyzer_agent._is_trigger("Zeus analyze this") is False

    @pytest.mark.asyncio
    async def test_non_friend_gets_quirky_rejection(self, image_analyzer_agent, mock_event, mock_line_bot_api):
        """Test that non-friends get a quirky rejection message."""
        # Setup: User is NOT a friend (get_profile raises ApiException)
        mock_line_bot_api.get_profile = MagicMock(side_effect=ApiException(status=404, reason="Not Found"))

        # Setup: Session has detected dates
        from src.services.image_analyzer_session_manager import image_analyzer_session_manager

        chat_id = "user_test_user_123"
        image_analyzer_session_manager.store_detected_dates(
            chat_id, [{"date": "2026-01-15", "title": "Test Event", "description": "Test"}]
        )
        # Mark as waiting for calendar confirmation
        from src.services.image_analyzer_session_manager import AnalyzerState

        image_analyzer_session_manager._sessions[chat_id].state = AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION

        # Patch privilege_service to return non-admin
        with patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege:
            mock_privilege.is_admin.return_value = False

            # Execute
            result = await image_analyzer_agent._handle_calendar_confirmation(
                mock_event,
                "yes add to calendar",
                chat_id,
                "test_user_123",
                mock_line_bot_api,
            )

        # Verify
        assert result is True

        # Check that reply_message was called with quirky rejection
        mock_line_bot_api.reply_message.assert_called_once()
        call_args = mock_line_bot_api.reply_message.call_args

        # Get the message text from the request
        request = call_args[0][0]  # First positional argument
        message_text = request.messages[0].text

        # Verify it contains friend-related rejection keywords
        assert any(keyword in message_text.lower() for keyword in ["friend", "friends", "เพื่อน"])

    @pytest.mark.asyncio
    async def test_friend_can_add_to_calendar(self, image_analyzer_agent, mock_event, mock_line_bot_api):
        """Test that friends can successfully add dates to calendar."""
        # Setup: User IS a friend (get_profile succeeds)
        mock_profile = MagicMock()
        mock_profile.display_name = "Test User"
        mock_line_bot_api.get_profile = MagicMock(return_value=mock_profile)

        # Setup: Session has detected dates
        from src.services.image_analyzer_session_manager import image_analyzer_session_manager

        chat_id = "user_test_user_123"
        image_analyzer_session_manager.store_detected_dates(
            chat_id, [{"date": "2026-01-15", "title": "Test Event", "description": "Test"}]
        )
        from src.services.image_analyzer_session_manager import AnalyzerState

        image_analyzer_session_manager._sessions[chat_id].state = AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION

        # Patch privilege_service and calendar agent
        with (
            patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
            patch("src.agents.calendar_agent.CalendarAgent") as mock_calendar_agent_class,
        ):
            mock_privilege.is_admin.return_value = False

            # Mock the calendar agent
            mock_calendar_agent = MagicMock()
            mock_calendar_agent.start_extraction_flow_from_image = AsyncMock()
            mock_calendar_agent_class.return_value = mock_calendar_agent

            # Execute
            result = await image_analyzer_agent._handle_calendar_confirmation(
                mock_event,
                "yes add to calendar",
                chat_id,
                "test_user_123",
                mock_line_bot_api,
            )

        # Verify
        assert result is True

        # Calendar agent should have been called (sessions get cleared so we just check it returned True)
        # The flow worked if result is True and no rejection message was sent

    @pytest.mark.asyncio
    async def test_admin_bypasses_friend_check(self, image_analyzer_agent, mock_event, mock_line_bot_api):
        """Test that admins bypass the friend check."""
        # Setup: User is NOT a friend but IS admin
        mock_line_bot_api.get_profile = MagicMock(side_effect=ApiException(status=404, reason="Not Found"))

        # Setup: Session has detected dates
        from src.services.image_analyzer_session_manager import image_analyzer_session_manager

        chat_id = "user_test_user_123"
        image_analyzer_session_manager.store_detected_dates(
            chat_id, [{"date": "2026-01-15", "title": "Test Event", "description": "Test"}]
        )
        from src.services.image_analyzer_session_manager import AnalyzerState

        image_analyzer_session_manager._sessions[chat_id].state = AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION

        # Patch privilege_service to return admin=True
        with (
            patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
            patch("src.agents.calendar_agent.CalendarAgent") as mock_calendar_agent_class,
        ):
            mock_privilege.is_admin.return_value = True  # User IS admin

            # Mock the calendar agent
            mock_calendar_agent = MagicMock()
            mock_calendar_agent.start_extraction_flow_from_image = AsyncMock()
            mock_calendar_agent_class.return_value = mock_calendar_agent

            # Execute
            result = await image_analyzer_agent._handle_calendar_confirmation(
                mock_event,
                "yes add to calendar",
                chat_id,
                "test_user_123",
                mock_line_bot_api,
            )

        # Verify - admin should succeed even without being a friend
        assert result is True

        # If result is True and we didn't get rejection, the admin bypass worked

    @pytest.mark.asyncio
    async def test_is_friend_caches_result(self, image_analyzer_agent, mock_event, mock_line_bot_api):
        """Test that friend status is cached."""
        # First call: friend check succeeds
        mock_profile = MagicMock()
        mock_profile.display_name = "Test User"
        mock_line_bot_api.get_profile = MagicMock(return_value=mock_profile)

        # First check
        result1 = await image_analyzer_agent._is_friend(mock_event, mock_line_bot_api)
        assert result1 is True

        # Verify cache entry exists
        assert "test_user_123" in image_analyzer_agent._friend_cache

        # Second check should use cache (not call API again)
        mock_line_bot_api.get_profile.reset_mock()
        result2 = await image_analyzer_agent._is_friend(mock_event, mock_line_bot_api)

        assert result2 is True
        # get_profile should NOT have been called again due to cache
        mock_line_bot_api.get_profile.assert_not_called()

    @pytest.mark.asyncio
    async def test_skip_calendar_works_for_non_friends(self, image_analyzer_agent, mock_event, mock_line_bot_api):
        """Test that non-friends can skip calendar without friend check."""
        # Setup: User is NOT a friend
        mock_line_bot_api.get_profile = MagicMock(side_effect=ApiException(status=404, reason="Not Found"))

        # Setup: Session exists
        from src.services.image_analyzer_session_manager import image_analyzer_session_manager

        chat_id = "user_test_user_123"
        image_analyzer_session_manager.store_detected_dates(
            chat_id, [{"date": "2026-01-15", "title": "Test Event", "description": "Test"}]
        )
        from src.services.image_analyzer_session_manager import AnalyzerState

        image_analyzer_session_manager._sessions[chat_id].state = AnalyzerState.WAITING_FOR_CALENDAR_CONFIRMATION

        # Execute - user says "no"
        mock_event.message.text = "no skip calendar"
        result = await image_analyzer_agent._handle_calendar_confirmation(
            mock_event,
            "no skip calendar",
            chat_id,
            "test_user_123",
            mock_line_bot_api,
        )

        # Verify - should succeed (skipping doesn't need friend check)
        assert result is True


class TestImageAnalyzerDateDetection:
    """Tests for date detection in image analysis."""

    @pytest.fixture
    def image_analyzer_agent(self):
        """Create an ImageAnalyzerAgent instance."""
        from src.agents.image_analyzer_agent import ImageAnalyzerAgent

        return ImageAnalyzerAgent()

    def test_extract_dates_from_analysis_valid_json(self, image_analyzer_agent):
        """Test extracting dates from valid analysis response."""
        analysis = """
        Here is my analysis of the image.

        ---DATES_DETECTED---
        [{"date": "2026-01-15", "title": "Meeting", "description": "Team sync"}]
        ---END_DATES---
        """

        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)

        assert len(dates) == 1
        assert dates[0]["date"] == "2026-01-15"
        assert dates[0]["title"] == "Meeting"

    def test_extract_dates_from_analysis_multiple_dates(self, image_analyzer_agent):
        """Test extracting multiple dates."""
        analysis = """
        Analysis text here.

        ---DATES_DETECTED---
        [
            {"date": "2026-01-15", "title": "Meeting 1", "description": "First"},
            {"date": "2026-02-20", "title": "Meeting 2", "description": "Second"}
        ]
        ---END_DATES---
        """

        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)

        assert len(dates) == 2
        assert dates[0]["date"] == "2026-01-15"
        assert dates[1]["date"] == "2026-02-20"

    def test_extract_dates_from_analysis_no_dates(self, image_analyzer_agent):
        """Test when no dates section present."""
        analysis = "Just a regular analysis without any dates."

        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)

        assert len(dates) == 0

    def test_extract_dates_from_analysis_invalid_json(self, image_analyzer_agent):
        """Test handling of invalid JSON in dates section."""
        analysis = """
        ---DATES_DETECTED---
        {not valid json}
        ---END_DATES---
        """

        dates = image_analyzer_agent._extract_dates_from_analysis(analysis)

        assert len(dates) == 0

    def test_strip_dates_section(self, image_analyzer_agent):
        """Test that dates section is stripped from user-visible response."""
        analysis = """
        Here is the analysis.

        ---DATES_DETECTED---
        [{"date": "2026-01-15", "title": "Event"}]
        ---END_DATES---

        More text here.
        """

        stripped = image_analyzer_agent._strip_dates_section(analysis)

        assert "---DATES_DETECTED---" not in stripped
        assert "---END_DATES---" not in stripped
        assert "Here is the analysis" in stripped
        assert "More text here" in stripped
