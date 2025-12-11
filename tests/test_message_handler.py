"""Tests for message handler."""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from linebot.models import TextSendMessage


class TestMessageHandler:
    """Test cases for message handler."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock LINE message event."""
        event = MagicMock()
        event.message.text = "Hello"
        event.reply_token = "test_token"
        return event

    @pytest.fixture
    def mock_line_bot_api(self):
        """Create a mock LINE Bot API."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_handle_text_message_success(self, mock_event, mock_line_bot_api):
        """Test successful message handling."""
        from src.handlers.message_handler import handle_text_message

        with patch("src.handlers.message_handler.translation_service") as mock_service:
            mock_service.auto_translate = AsyncMock(return_value=("สวัสดี", "en"))

            await handle_text_message(mock_event, mock_line_bot_api)

            mock_service.auto_translate.assert_called_once_with("Hello")
            mock_line_bot_api.reply_message.assert_called_once()

            # Check that reply message contains translation
            args = mock_line_bot_api.reply_message.call_args
            assert args[0][0] == "test_token"
            assert "สวัสดี" in args[0][1].text

    @pytest.mark.asyncio
    async def test_handle_text_message_translation_failure(self, mock_event, mock_line_bot_api):
        """Test message handling when translation fails."""
        from src.handlers.message_handler import handle_text_message

        with patch("src.handlers.message_handler.translation_service") as mock_service:
            mock_service.auto_translate = AsyncMock(return_value=(None, None))

            await handle_text_message(mock_event, mock_line_bot_api)

            # Check that error message is sent
            args = mock_line_bot_api.reply_message.call_args
            assert "Sorry" in args[0][1].text or "couldn't" in args[0][1].text

    def test_handle_text_message_sync(self, mock_event, mock_line_bot_api):
        """Test synchronous wrapper for message handler."""
        from src.handlers.message_handler import handle_text_message_sync

        with patch("src.handlers.message_handler.translation_service") as mock_service:
            mock_service.auto_translate = AsyncMock(return_value=("Test", "en"))

            handle_text_message_sync(mock_event, mock_line_bot_api)

            mock_line_bot_api.reply_message.assert_called_once()
