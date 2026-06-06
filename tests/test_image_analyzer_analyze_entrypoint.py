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
    message.text = "Zeus analyze"
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
        patch("src.agents.image_analyzer_agent.github_models_service") as mock_gms,
        patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
        patch("src.agents.image_analyzer_agent.image_analyzer_rate_limiter") as mock_rl,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_gms.is_configured.return_value = True
        mock_privilege.is_admin.return_value = False
        mock_rl.is_allowed.return_value = True
        mock_session.start_analysis_choice = MagicMock()

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
        patch("src.agents.image_analyzer_agent.github_models_service") as mock_gms,
        patch("src.agents.image_analyzer_agent.privilege_service") as mock_privilege,
        patch("src.agents.image_analyzer_agent.image_analyzer_rate_limiter") as mock_rl,
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_gms.is_configured.return_value = True
        mock_privilege.is_admin.return_value = False
        mock_rl.is_allowed.return_value = True
        mock_session.start_analysis_choice = MagicMock()

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
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with (
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_session.get_last_image.return_value = "data:image/jpeg;base64,abc"

        handled = await agent._handle_analysis_choice(
            mock_event,
            "last",
            "user_user123",
            "user123",
            mock_line_bot_api,
        )

    assert handled is True
    mock_session.start_session_with_image.assert_called_once_with(
        "user_user123",
        "user123",
        image_data="data:image/jpeg;base64,abc",
        analysis_mode="standard",
    )
    mock_line_bot_api.reply_message.assert_called_once()
    request = mock_line_bot_api.reply_message.call_args[0][0]
    assert "last image" in request.messages[0].text.lower()


@pytest.mark.asyncio
async def test_analysis_choice_last_without_previous_image_returns_fallback(
    mock_event,
    mock_line_bot_api,
):
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()

    with (
        patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_session,
        patch(
            "src.agents.image_analyzer_agent.asyncio.to_thread",
            new=AsyncMock(side_effect=lambda func, *args, **kwargs: func(*args, **kwargs)),
        ),
    ):
        mock_session.get_last_image.return_value = None

        handled = await agent._handle_analysis_choice(
            mock_event,
            "last",
            "user_user123",
            "user123",
            mock_line_bot_api,
        )

    assert handled is True
    mock_session.clear_session.assert_called_once_with("user_user123")
    request = mock_line_bot_api.reply_message.call_args[0][0]
    assert "previous image" in request.messages[0].text.lower()
