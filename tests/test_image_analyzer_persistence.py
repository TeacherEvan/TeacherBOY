# tests/test_image_analyzer_persistence.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.messaging import MessagingApi


@pytest.mark.asyncio
async def test_handle_question_saves_metadata():
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent

    agent = ImageAnalyzerAgent()
    mock_event = MagicMock()
    mock_event.source.user_id = "user_123"
    mock_event.source.group_id = "group_123"
    mock_line_bot_api = MagicMock(spec=MessagingApi)

    with patch("src.agents.image_analyzer_agent.image_analyzer_session_manager") as mock_mgr:
        mock_mgr.get_image_and_question = AsyncMock(return_value=("data:image/jpeg;base64,abc", "test prompt", "standard"))
        mock_mgr.save_image_metadata = AsyncMock(return_value="img_123")
        mock_mgr.clear_session = AsyncMock()

        with patch(
            "src.agents.image_analyzer_agent.chat_completion_with_vision_fallback",
            new=AsyncMock(return_value="analysis result"),
        ):
            with patch("src.agents.image_analyzer_agent.asyncio.to_thread", new=AsyncMock()):
                await agent._handle_question(
                    mock_event, "test prompt", "group_123", "user_123", mock_line_bot_api, MagicMock()
                )

        mock_mgr.save_image_metadata.assert_awaited_once()
        call_kwargs = mock_mgr.save_image_metadata.call_args.kwargs
        assert call_kwargs["prompt"] == "test prompt"
        assert call_kwargs["response"] == "analysis result"
