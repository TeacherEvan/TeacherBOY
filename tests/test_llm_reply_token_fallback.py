"""Test LLM agent's message sending using push_message.

This test verifies that the LLM agent reliably sends messages using push_message,
which is robust for async processing.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent, Source, TextMessageContent

from src.agents.llm_agent import LLMAgent


@pytest.fixture
def llm_agent():
    """Create LLM agent instance."""
    return LLMAgent()


@pytest.fixture
def mock_event():
    """Create mock LINE message event."""
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "valid_token_123"
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "Ms. Green what is the weather?"

    # Mock source
    source = MagicMock(spec=Source)
    source.type = "user"
    source.user_id = "U123456789"
    source.group_id = None
    source.room_id = None
    event.source = source

    return event


@pytest.fixture
def mock_line_api():
    """Create mock LINE API."""
    return MagicMock(spec=MessagingApi)


@pytest.mark.asyncio
async def test_push_message_success(llm_agent, mock_event, mock_line_api):
    """Test that messages are sent successfully using push_message."""

    mock_line_api.push_message = MagicMock()

    # Mock successful response from fallback chain
    with patch("src.agents.llm_agent.openrouter_service") as mock_openrouter:
        mock_openrouter.is_configured.return_value = True
        mock_openrouter.chat_completion = AsyncMock(return_value="The weather is sunny!")
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Mock successful push_message call
            mock_to_thread.return_value = None

            result = await llm_agent.handle(mock_event, "Ms. Green what is the weather?", mock_line_api)

            # Verify it was handled successfully
            assert result is True

            # Verify push_message was called
            assert mock_to_thread.call_count == 1


@pytest.mark.asyncio
async def test_push_message_handles_errors(llm_agent, mock_event, mock_line_api):
    """Test that push message errors are handled gracefully."""

    mock_line_api.push_message = MagicMock()

    # Mock successful LLM response
    with patch("src.agents.llm_agent.openrouter_service") as mock_openrouter:
        mock_openrouter.is_configured.return_value = True
        mock_openrouter.chat_completion = AsyncMock(return_value="Hello!")
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Mock push_message to raise exception
            mock_to_thread.side_effect = Exception("Push failed")

            # Should handle gracefully (log error but not crash)
            result = await llm_agent.handle(mock_event, "Ms. Green hello", mock_line_api)
            assert result is True


@pytest.mark.asyncio
async def test_push_message_called_once(llm_agent, mock_event, mock_line_api):
    """Test that only push_message is called for sending responses."""

    mock_line_api.push_message = MagicMock()

    with patch("src.agents.llm_agent.openrouter_service") as mock_openrouter:
        mock_openrouter.is_configured.return_value = True
        mock_openrouter.chat_completion = AsyncMock(return_value="Response!")
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Mock successful push_message call
            mock_to_thread.return_value = None

            result = await llm_agent.handle(mock_event, "Ms. Green test", mock_line_api)
            assert result is True

            # Should only call push_message
            assert mock_to_thread.call_count == 1


@pytest.mark.asyncio
async def test_error_message_sent_via_push(llm_agent, mock_event, mock_line_api):
    """Test that error messages are sent via push_message."""

    mock_line_api.push_message = MagicMock()

    # Mock LLM failure
    with patch("src.agents.llm_agent.openrouter_service") as mock_openrouter:
        mock_openrouter.is_configured.return_value = True
        mock_openrouter.chat_completion = AsyncMock(return_value=None)
        mock_openrouter.get_last_error = MagicMock(return_value=(500, "Server error", "openrouter"))
        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            # Mock successful push for error message
            mock_to_thread.return_value = None

            # Should handle gracefully
            result = await llm_agent.handle(mock_event, "Ms. Green test", mock_line_api)
            assert result is True

            # Should call push_message for error message
            assert mock_to_thread.call_count == 1