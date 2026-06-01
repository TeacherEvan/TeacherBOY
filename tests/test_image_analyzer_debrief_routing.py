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
    event.source.group_id = None
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
    event.source.group_id = None
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
async def test_debrief_image_uses_debrief_prompt_builder(
    mock_trigger_event,
    mock_image_event,
    mock_line_bot_api,
):
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with patch("src.agents.image_analyzer_agent.settings") as mock_settings, \
         patch("src.agents.image_analyzer_agent.github_models_service") as mock_gms, \
         patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session, \
         patch("src.agents.image_analyzer_agent.build_debrief_prompt", return_value="DEBRIEF_PROMPT") as mock_build_debrief, \
         patch("src.agents.image_analyzer_agent.asyncio.to_thread"):
        mock_settings.llm_temperature = 0.2
        mock_settings.profiler_model = "openai/gpt-4o"
        mock_settings.is_calendar_configured.return_value = False
        mock_gms.is_configured.return_value = True
        mock_gms.chat_completion_with_vision = AsyncMock(return_value="debrief analysis")
        mock_session.get_image_and_question.return_value = (
            "data:image/jpeg;base64,abc",
            "What is happening here?",
            "debrief",
        )

        agent._send_analyzing_message = AsyncMock()
        agent._send_error_message = AsyncMock()
        agent._format_response = lambda analysis: analysis
        agent._extract_dates_from_analysis = lambda analysis: []

        await agent._handle_question(
            mock_trigger_event,
            "What is happening here?",
            "group_123",
            "user123",
            mock_line_bot_api,
            MagicMock(),
        )

        mock_build_debrief.assert_called_once()
        assert mock_gms.chat_completion_with_vision.await_count == 1
