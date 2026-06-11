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
async def test_debrief_image_uses_debrief_extraction_service(
    mock_trigger_event,
    mock_image_event,
    mock_line_bot_api,
):
    """Test that debrief mode uses DebriefExtractionService and DebriefFormatter."""
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent
    from src.services.debrief_extraction_service import DailyDebriefSchema, PeriodDebriefSchema

    agent = ImageAnalyzerAgent()

    # Create a mock daily debrief schema
    mock_debrief = DailyDebriefSchema(
        date="2026-01-15",
        day_name="Thursday",
        periods=[
            PeriodDebriefSchema(
                period="Period 1",
                subject="Science",
                teacher="Teacher Evan",
                lesson="Photosynthesis",
                topics_covered=["plants", "light"],
                comprehension_level="high",
                key_phrases_learned=["photosynthesis", "chlorophyll"],
                suggested_review=["review plant cells"],
                observations="Students engaged well",
            )
        ],
        general_observations="Good day overall",
        confidence_score=0.9,
        notes=None,
    )

    # Create a mock to_thread that actually executes the function
    async def mock_to_thread(func, *args, **kwargs):
        return await func(*args, **kwargs) if hasattr(func, "__await__") else func(*args, **kwargs)

    with (
        patch("src.agents.image_analyzer_agent._debrief_extraction_service") as mock_debrief_service,
        patch("src.agents.image_analyzer_agent.DebriefFormatter") as mock_formatter,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch("src.agents.image_analyzer_agent.asyncio.to_thread", new=mock_to_thread),
        patch("src.agents.image_analyzer_agent.datetime") as mock_datetime,
    ):
        mock_datetime.now.return_value.strftime.return_value = "2026-01-15"
        mock_session.get_image_and_question = AsyncMock(return_value=(
            "data:image/jpeg;base64,abc",
            "What is happening here?",
            "debrief",
        ))
        mock_session.clear_session = AsyncMock()
        mock_debrief_service.extract_from_image = AsyncMock(return_value=mock_debrief)
        mock_formatter.format_daily_debrief.return_value = "FORMATTED DEBRIEF"

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

        # Verify DebriefExtractionService was called
        mock_debrief_service.extract_from_image.assert_awaited_once_with(
            image_url_or_base64="data:image/jpeg;base64,abc",
            chat_id="group_123",
            date_str="2026-01-15",
            model="openai/gpt-4o",
        )
        # Verify DebriefFormatter was called
        mock_formatter.format_daily_debrief.assert_called_once_with(mock_debrief)
        # Verify push_message was called with formatted debrief
        mock_line_bot_api.push_message.assert_called_once()
