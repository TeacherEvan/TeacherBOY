"""Tests for message handler."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock


class TestMessageHandler:
    """Test cases for message handler."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock LINE message event with Thai text."""
        event = MagicMock()
        event.message.text = "สวัสดี"  # Thai text to trigger translation
        event.reply_token = "test_token"
        event.source.type = "user"
        event.source.user_id = "test_user_123"
        return event

    @pytest.fixture
    def mock_line_bot_api(self):
        """Create a mock LINE Bot API."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_handle_text_message_success(self, mock_event, mock_line_bot_api):
        """Test successful message handling with session management."""
        from src.handlers.message_handler import handle_text_message

        with patch(
            "src.handlers.message_handler.session_manager"
        ) as mock_session, patch(
            "src.handlers.message_handler.ai_translation_service"
        ) as mock_ai_translation_service, patch(
            "asyncio.to_thread"
        ) as mock_to_thread:
            # Setup mocks
            mock_session.is_session_active.return_value = True
            mock_ai_translation_service.translate = AsyncMock(
                return_value=MagicMock(text="Hello")
            )
            mock_to_thread.return_value = None  # Mock the reply_message call

            await handle_text_message(mock_event, mock_line_bot_api)

            mock_ai_translation_service.translate.assert_awaited_once_with(
                "สวัสดี",
                source_lang="th",
                target_lang="en",
            )

            # Verify session message count was incremented
            mock_session.increment_message_count.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_text_message_translation_failure(
        self, mock_event, mock_line_bot_api
    ):
        """Test message handling when translation fails."""
        from src.handlers.message_handler import handle_text_message

        with patch(
            "src.handlers.message_handler.session_manager"
        ) as mock_session, patch(
            "src.handlers.message_handler.ai_translation_service"
        ) as mock_ai_translation_service, patch(
            "asyncio.to_thread"
        ) as mock_to_thread:
            # Setup mocks - translation fails
            mock_session.is_session_active.return_value = True
            mock_ai_translation_service.translate = AsyncMock(return_value=None)
            mock_to_thread.return_value = None

            await handle_text_message(mock_event, mock_line_bot_api)

            # Verify error handling - asyncio.to_thread should be called with error message
            assert mock_to_thread.called

    @pytest.mark.asyncio
    async def test_handle_text_message_auto_start_session(
        self, mock_event, mock_line_bot_api
    ):
        """Test that Thai text auto-starts a translation session."""
        from src.handlers.message_handler import handle_text_message

        with patch(
            "src.handlers.message_handler.session_manager"
        ) as mock_session, patch(
            "src.handlers.message_handler.ai_translation_service"
        ) as mock_ai_translation_service, patch(
            "asyncio.to_thread"
        ) as mock_to_thread:
            # Setup mocks - session not active initially
            mock_session.is_session_active.side_effect = [
                False,
                True,
            ]  # First check False, second True
            mock_ai_translation_service.translate = AsyncMock(
                return_value=MagicMock(text="Hello")
            )
            mock_to_thread.return_value = None

            await handle_text_message(mock_event, mock_line_bot_api)

            # Verify session was auto-started
            mock_session.start_session.assert_called_once_with(
                "test_user_123", "test_user_123"
            )
