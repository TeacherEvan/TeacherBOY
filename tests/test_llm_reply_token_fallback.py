"""Test LLM agent's message sending using push_message.

This test verifies that the LLM agent reliably sends messages using push_message,
which is robust for async processing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from linebot.v3.webhooks import MessageEvent, TextMessageContent, Source
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging.exceptions import ApiException

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
    event.message.text = "Zeus what is the weather?"
    
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

    # Mock successful response from GitHub Models
    with patch.object(llm_agent.github_service, 'chat_completion', return_value="The weather is sunny!"):
        with patch.object(llm_agent.github_service, 'is_configured', return_value=True):
            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                # Mock successful push_message call
                mock_to_thread.return_value = None

                # Call the agent with proper Zeus command
                result = await llm_agent.handle(mock_event, "Zeus what is the weather?", mock_line_api)

                # Verify it was handled successfully
                assert result is True

                # Verify push_message was called
                assert mock_to_thread.call_count == 1


@pytest.mark.asyncio
async def test_push_message_handles_errors(llm_agent, mock_event, mock_line_api):
    """Test that push message errors are handled gracefully."""

    mock_line_api.push_message = MagicMock()

    # Mock successful GitHub Models response
    with patch.object(llm_agent.github_service, 'chat_completion', return_value="Hello!"):
        with patch.object(llm_agent.github_service, 'is_configured', return_value=True):
            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                # Mock push_message to raise exception
                mock_to_thread.side_effect = Exception("Push failed")

                # Should handle gracefully (log error but not crash)
                result = await llm_agent.handle(mock_event, "Zeus hello", mock_line_api)
                assert result is True


@pytest.mark.asyncio
async def test_push_message_called_once(llm_agent, mock_event, mock_line_api):
    """Test that only push_message is called for sending responses."""

    mock_line_api.push_message = MagicMock()

    with patch.object(llm_agent.github_service, 'chat_completion', return_value="Response!"):
        with patch.object(llm_agent.github_service, 'is_configured', return_value=True):
            with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                # Mock successful push_message call
                mock_to_thread.return_value = None

                result = await llm_agent.handle(mock_event, "Zeus test", mock_line_api)
                assert result is True

                # Should only call push_message
                assert mock_to_thread.call_count == 1


@pytest.mark.asyncio
async def test_error_message_sent_via_push(llm_agent, mock_event, mock_line_api):
    """Test that error messages are sent via push_message."""

    mock_line_api.push_message = MagicMock()

    # Mock LLM failure
    with patch.object(llm_agent.github_service, 'chat_completion', return_value=None):
        with patch.object(llm_agent.github_service, 'is_configured', return_value=True):
            with patch.object(llm_agent.github_service, 'get_last_error', return_value=(500, "Server error", "gpt-4o")):
                with patch('asyncio.to_thread', new_callable=AsyncMock) as mock_to_thread:
                    # Mock successful push for error message
                    mock_to_thread.return_value = None

                    # Should handle gracefully
                    result = await llm_agent.handle(mock_event, "Zeus test", mock_line_api)
                    assert result is True

                    # Should call push_message for error message
                    assert mock_to_thread.call_count == 1
