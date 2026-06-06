from unittest.mock import Mock, patch

import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

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
async def test_private_help_non_admin_is_routed_to_help_agent(line_bot_api):
    # Reset privilege_service cache before test
    privilege_service._reset_for_testing()

    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["UADMIN"]
        mock_settings.get_moderator_user_ids.return_value = []
        agent = TranslationAgent()

    event = _make_private_event("UUSER")
    assert await agent.should_handle(event, "help") is False

    # Reset after test
    privilege_service._reset_for_testing()


@pytest.mark.asyncio
async def test_private_help_admin_is_routed_to_help_agent(line_bot_api):
    # Reset privilege_service cache before test
    privilege_service._reset_for_testing()

    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["UADMIN"]
        mock_settings.get_moderator_user_ids.return_value = []
        agent = TranslationAgent()

    event = _make_private_event("UADMIN")
    assert await agent.should_handle(event, "help") is False

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
