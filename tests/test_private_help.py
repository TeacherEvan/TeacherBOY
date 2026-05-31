import pytest
from unittest.mock import Mock, patch

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi

from src.agents.translation_agent import TranslationAgent
from src.services.privilege_service import privilege_service


@pytest.fixture
def line_bot_api():
    api = Mock(spec=MessagingApi)
    api.reply_message = Mock()
    return api


def _make_private_event(user_id: str = "UUSER"):
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.user_id = user_id
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "reply_token"
    return event


@pytest.mark.asyncio
async def test_private_help_non_admin_shows_user_commands(line_bot_api):
    # Reset privilege_service cache before test
    privilege_service._reset_for_testing()
    
    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["UADMIN"]
        mock_settings.get_moderator_user_ids.return_value = []
        agent = TranslationAgent()

    event = _make_private_event("UUSER")
    assert await agent.should_handle(event, "help") is True

    ok = await agent.handle(event, "help", line_bot_api)
    assert ok is True

    msg_text = line_bot_api.reply_message.call_args[0][0].messages[0].text
    assert "User commands" in msg_text
    assert "Admin commands" not in msg_text
    assert "Ms. Green" in msg_text
    assert "Zeus" not in msg_text
    
    # Reset after test
    privilege_service._reset_for_testing()


@pytest.mark.asyncio
async def test_private_help_admin_includes_admin_commands(line_bot_api):
    # Reset privilege_service cache before test
    privilege_service._reset_for_testing()
    
    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["UADMIN"]
        mock_settings.get_moderator_user_ids.return_value = []
        agent = TranslationAgent()

        event = _make_private_event("UADMIN")
        assert await agent.should_handle(event, "help") is True

        ok = await agent.handle(event, "help", line_bot_api)
        assert ok is True

        msg_text = line_bot_api.reply_message.call_args[0][0].messages[0].text
        assert "User commands" in msg_text
        assert "Admin commands" in msg_text
        assert "Ms. Green" in msg_text
        assert "Zeus" not in msg_text
    
    # Reset after test
    privilege_service._reset_for_testing()


@pytest.mark.asyncio
async def test_translation_agent_wake_command_uses_ms_green(line_bot_api):
    privilege_service._reset_for_testing()

    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["UADMIN"]
        mock_settings.get_moderator_user_ids.return_value = []
        agent = TranslationAgent()

    event = _make_private_event("UUSER")

    assert await agent.should_handle(event, "Ms. Green") is True
    assert await agent.should_handle(event, "Zeus") is False

    privilege_service._reset_for_testing()
