"""Focused tests for ImageAnalyzerAgent debrief routing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, Source, TextMessageContent


@pytest.fixture
def mock_trigger_event():
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "test_reply_token"
    event.source = MagicMock(spec=Source)
    event.source.user_id = "user123"
    event.source.group_id = "group_123"
    event.source.room_id = None
    message = MagicMock(spec=TextMessageContent)
    message.type = "text"
    message.text = "assistantbot debrief this"
    event.message = message
    return event


@pytest.fixture
def mock_image_event():
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "test_reply_token"
    event.source = MagicMock(spec=Source)
    event.source.user_id = "user123"
    event.source.group_id = "group_123"
    event.source.room_id = None
    message = MagicMock(spec=ImageMessageContent)
    message.type = "image"
    message.id = "img-123"
    event.message = message
    return event


@pytest.fixture
def mock_line_bot_api():
    api = MagicMock(spec=MessagingApi)
    api.reply_message = MagicMock()
    api.push_message = MagicMock()
    return api


@pytest.mark.asyncio
async def test_debrief_trigger_is_recognized(mock_trigger_event):
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()
    assert agent._is_trigger("assistantbot debrief this") is True
    assert agent._is_trigger("Ms. Green debrief this") is True


@pytest.mark.asyncio
@pytest.mark.asyncio
async def test_debrief_image_uses_direct_creative_vision_generation(
    mock_trigger_event,
    mock_image_event,
    mock_line_bot_api,
):
    """Test that debrief mode uses direct creative vision call and bypasses DebriefExtractionService."""
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    # Create a mock to_thread that actually executes the function
    async def mock_to_thread(func, *args, **kwargs):
        return await func(*args, **kwargs) if hasattr(func, "__await__") else func(*args, **kwargs)

    with (
        patch("src.agents.image_analyzer_agent.chat_completion_with_vision_fallback") as mock_fallback,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch("src.agents.image_analyzer_agent.asyncio.to_thread", new=mock_to_thread),
    ):
        mock_session.get_image_and_question = AsyncMock(
            return_value=(
                "data:image/jpeg;base64,abc",
                "What is happening here?",
                "debrief",
            )
        )
        mock_session.clear_session = AsyncMock()
        mock_fallback.return_value = "Date 23/06\nat 08h48: I cooked steak\nat 09h45: Steak was done..."

        agent._send_analyzing_message = AsyncMock()
        agent._send_error_message = AsyncMock()

        await agent._handle_question(
            mock_trigger_event,
            "What is happening here?",
            "group_123",
            "user123",
            mock_line_bot_api,
            MagicMock(),
        )

        # Verify chat_completion_with_vision_fallback was called
        mock_fallback.assert_called_once()
        call_args = mock_fallback.call_args[1]
        assert "messages" in call_args
        messages = call_args["messages"]
        assert "expert creative journal writer" in messages[1]["content"][0]["text"]
        # Verify push_message was called with formatted debrief
        mock_line_bot_api.push_message.assert_called_once()
