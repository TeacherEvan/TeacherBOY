"""Focused tests for the ImageAnalyzer analyze entry point."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent, Source, TextMessageContent


@pytest.fixture
def mock_event():
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "test_reply_token"
    event.source = MagicMock(spec=Source)
    event.source.user_id = "user123"
    event.source.group_id = None
    event.source.room_id = None
    message = MagicMock(spec=TextMessageContent)
    message.type = "text"
    message.text = "Ms. Green analyze"
    event.message = message
    return event


@pytest.fixture
def mock_line_bot_api():
    api = MagicMock(spec=MessagingApi)
    api.reply_message = MagicMock()
    api.push_message = MagicMock()
    return api


@pytest.mark.asyncio
async def test_analyze_trigger_is_recognized():
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()
    assert agent._is_trigger("Ms. Green analyze") is True
    assert agent._is_trigger("ms. green analyze") is True


@pytest.mark.asyncio
async def test_analyze_prompt_asks_new_or_last(mock_event, mock_line_bot_api):
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with (
        patch("src.services.gemini_service.gemini_service") as mock_gemini,
        patch("src.services.hermes_service.hermes_service") as mock_hermes,
        patch("src.services.openrouter_service.openrouter_service") as mock_openrouter,
        patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
        patch("src.agents.image_analyzer_agent.image_analyzer_rate_limiter") as mock_rl,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_gemini.is_vision_configured.return_value = True
        mock_hermes.is_vision_configured.return_value = True
        mock_openrouter.is_configured.return_value = True
        mock_privilege.is_admin.return_value = False
        mock_rl.is_allowed.return_value = True
        mock_session.is_waiting_for_analysis_choice = AsyncMock(return_value=False)
        mock_session.is_waiting_for_question = AsyncMock(return_value=False)
        mock_session.is_waiting_for_calendar_confirmation = AsyncMock(return_value=False)
        mock_session.start_analysis_choice = AsyncMock()

        handled = await agent.handle(mock_event, "Ms. Green analyze", mock_line_bot_api)

    assert handled is True
    mock_session.start_analysis_choice.assert_called_once_with("user_user123", "user123")
    mock_line_bot_api.reply_message.assert_called_once()
    request = mock_line_bot_api.reply_message.call_args[0][0]
    assert request.messages[0].text == "New or Last"
    assert [item.action.label for item in request.messages[0].quick_reply.items] == [
        "New",
        "Last",
    ]


@pytest.mark.asyncio
async def test_plain_analyze_keeps_new_or_last_prompt(mock_event, mock_line_bot_api):
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with (
        patch("src.services.gemini_service.gemini_service") as mock_gemini,
        patch("src.services.hermes_service.hermes_service") as mock_hermes,
        patch("src.services.openrouter_service.openrouter_service") as mock_openrouter,
        patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
        patch("src.agents.image_analyzer_agent.image_analyzer_rate_limiter") as mock_rl,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_gemini.is_vision_configured.return_value = True
        mock_hermes.is_vision_configured.return_value = True
        mock_openrouter.is_configured.return_value = True
        mock_privilege.is_admin.return_value = False
        mock_rl.is_allowed.return_value = True
        mock_session.is_waiting_for_analysis_choice = AsyncMock(return_value=False)
        mock_session.is_waiting_for_question = AsyncMock(return_value=False)
        mock_session.is_waiting_for_calendar_confirmation = AsyncMock(return_value=False)
        mock_session.start_analysis_choice = AsyncMock()

        handled = await agent.handle(mock_event, "analyze", mock_line_bot_api)

    assert handled is True
    mock_session.start_analysis_choice.assert_called_once_with("user_user123", "user123")
    mock_line_bot_api.reply_message.assert_called_once()
    request = mock_line_bot_api.reply_message.call_args[0][0]
    assert request.messages[0].text == "New or Last"
    assert [item.action.label for item in request.messages[0].quick_reply.items] == [
        "New",
        "Last",
    ]


@pytest.mark.asyncio
async def test_analysis_choice_last_uses_last_image(mock_event, mock_line_bot_api):
    """Test 'Last' choice uses previously stored image."""
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with (
        patch("src.services.gemini_service.gemini_service") as mock_gemini,
        patch("src.services.hermes_service.hermes_service") as mock_hermes,
        patch("src.services.openrouter_service.openrouter_service") as mock_openrouter,
        patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
        patch("src.agents.image_analyzer_agent.image_analyzer_rate_limiter") as mock_rl,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_gemini.is_vision_configured.return_value = True
        mock_hermes.is_vision_configured.return_value = True
        mock_openrouter.is_configured.return_value = True
        mock_privilege.is_admin.return_value = False
        mock_rl.is_allowed.return_value = True
        mock_session.is_waiting_for_analysis_choice = AsyncMock(return_value=True)
        mock_session.get_image_and_question = AsyncMock(
            return_value=(
                "data:image/jpeg;base64,oldimage",
                "What is this?",
                "analyze",
            )
        )
        mock_session.get_last_image = AsyncMock(return_value="data:image/jpeg;base64,oldimage")
        mock_session.start_session_with_image = AsyncMock()
        mock_session.clear_session = AsyncMock()

        # Set message to "Last" choice
        mock_event.message.text = "Last"

        handled = await agent.handle(mock_event, "Last", mock_line_bot_api)

    assert handled is True
    mock_session.get_last_image.assert_called_once_with("user_user123")
    mock_session.start_session_with_image.assert_called_once()


@pytest.mark.asyncio
async def test_analysis_choice_last_without_previous_image_returns_fallback(mock_event, mock_line_bot_api):
    """Test 'Last' choice without previous image returns fallback message."""
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with (
        patch("src.services.gemini_service.gemini_service") as mock_gemini,
        patch("src.services.hermes_service.hermes_service") as mock_hermes,
        patch("src.services.openrouter_service.openrouter_service") as mock_openrouter,
        patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
        patch("src.agents.image_analyzer_agent.image_analyzer_rate_limiter") as mock_rl,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_gemini.is_vision_configured.return_value = True
        mock_hermes.is_vision_configured.return_value = True
        mock_openrouter.is_configured.return_value = True
        mock_privilege.is_admin.return_value = False
        mock_rl.is_allowed.return_value = True
        mock_session.is_waiting_for_analysis_choice = AsyncMock(return_value=True)
        mock_session.get_image_and_question = AsyncMock(return_value=(None, None, None))
        mock_session.get_last_image = AsyncMock(return_value=None)
        mock_session.clear_session = AsyncMock()

        mock_event.message.text = "Last"

        handled = await agent.handle(mock_event, "Last", mock_line_bot_api)

    assert handled is True
    mock_line_bot_api.reply_message.assert_called_once()
    request = mock_line_bot_api.reply_message.call_args[0][0]
    assert "No previous image found" in request.messages[0].text or "don't have a previous image" in request.messages[0].text