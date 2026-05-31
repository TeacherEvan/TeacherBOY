from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

from src.agents.translation_agent import TranslationAgent
from src.services.ai_translation_service import AITranslationResult


@pytest.fixture
def line_bot_api():
    api = Mock(spec=MessagingApi)
    api.reply_message = Mock()
    return api


@pytest.fixture
def translation_service():
    service = Mock()
    service.translate = AsyncMock(
        return_value=AITranslationResult(
            text="translated output",
            provider="github_models",
        )
    )
    return service


def _make_private_event(user_id: str = "UUSER"):
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.user_id = user_id
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "reply_token"
    return event


class _FakeSessionManager:
    def __init__(self, *, sleeping: bool, active: bool):
        self.sleeping = sleeping
        self.active = active
        self.started_sessions = []
        self.sleep_calls = []

    def is_sleeping(self, chat_id: str) -> bool:
        return self.sleeping

    def wake_chat(self, chat_id: str):
        self.sleeping = False

    def sleep_chat(self, chat_id: str, hours: int):
        self.sleeping = True
        self.sleep_calls.append((chat_id, hours))

    def is_session_active(self, chat_id: str) -> bool:
        return self.active

    def start_session(self, chat_id: str, user_id: str):
        self.active = True
        self.started_sessions.append((chat_id, user_id))

    def is_duplicate_message(self, chat_id: str, text: str) -> bool:
        return False


def _make_identity_service(*aliases: str):
    normalized_aliases = [alias.lower().strip() for alias in aliases]
    profile = SimpleNamespace(aliases=normalized_aliases)

    def split_command_prefix(text: str):
        cleaned = " ".join((text or "").strip().split())
        lowered = cleaned.lower()
        for alias in sorted(normalized_aliases, key=len, reverse=True):
            if lowered == alias:
                return alias, ""
            if lowered.startswith(f"{alias} "):
                return alias, cleaned[len(alias):].lstrip()
        return None, cleaned

    service = Mock()
    service.get_profile.return_value = profile
    service.split_command_prefix.side_effect = split_command_prefix
    return service


async def _run_inline(func, *args, **kwargs):
    return func(*args, **kwargs)


@pytest.mark.asyncio
async def test_admin_thai_message_wakes_sleeping_chat_and_starts_session(
    line_bot_api, translation_service
):
    agent = TranslationAgent(ai_translation_service=translation_service)
    event = _make_private_event("UADMIN")
    session = _FakeSessionManager(sleeping=True, active=False)
    identity_service = _make_identity_service("ms. green", "ms green")

    with (
        patch("src.agents.translation_agent.session_manager", session),
        patch("src.agents.translation_agent.get_bot_identity_service", return_value=identity_service),
        patch("src.agents.translation_agent.privilege_service.is_admin", return_value=True),
        patch("src.agents.translation_agent.rate_limiter.is_allowed", return_value=True),
        patch("src.agents.translation_agent.asyncio.to_thread", new=_run_inline),
    ):
        assert await agent.should_handle(event, "สวัสดีค่ะ") is True

        result = await agent.handle(event, "สวัสดีค่ะ", line_bot_api)

    assert result is True
    assert session.is_sleeping("user_UADMIN") is False
    assert session.is_session_active("user_UADMIN") is True
    assert session.started_sessions == [("user_UADMIN", "UADMIN")]
    translation_service.translate.assert_awaited_once_with(
        "สวัสดีค่ะ",
        source_lang="th",
        target_lang="en",
    )


@pytest.mark.asyncio
async def test_non_privileged_alias_stop_falls_through_to_translation(
    line_bot_api, translation_service
):
    agent = TranslationAgent(ai_translation_service=translation_service)
    event = _make_private_event("UUSER")
    session = _FakeSessionManager(sleeping=False, active=False)
    identity_service = _make_identity_service("ms. green", "ms green")

    with (
        patch("src.agents.translation_agent.session_manager", session),
        patch("src.agents.translation_agent.get_bot_identity_service", return_value=identity_service),
        patch("src.agents.translation_agent.privilege_service.is_admin", return_value=False),
        patch("src.agents.translation_agent.privilege_service.is_privileged", return_value=False),
        patch("src.agents.translation_agent.rate_limiter.is_allowed", return_value=True),
        patch("src.services.news_session_manager.news_session_manager.is_in_news_flow", return_value=False),
        patch("src.agents.translation_agent.asyncio.to_thread", new=_run_inline),
    ):
        assert await agent.should_handle(event, "ms green stop") is True

        result = await agent.handle(event, "ms green stop", line_bot_api)

    assert result is True
    assert session.sleep_calls == []
    translation_service.translate.assert_awaited_once_with(
        "ms green stop",
        source_lang="en",
        target_lang="th",
    )

    call_args = line_bot_api.reply_message.call_args
    assert call_args[0][0].messages[0].text == "translated output"


@pytest.mark.asyncio
async def test_non_privileged_alias_stop_does_not_bypass_sleeping_chat(
    line_bot_api, translation_service
):
    agent = TranslationAgent(ai_translation_service=translation_service)
    event = _make_private_event("UUSER")
    session = _FakeSessionManager(sleeping=True, active=False)
    identity_service = _make_identity_service("ms. green", "ms green")

    with (
        patch("src.agents.translation_agent.session_manager", session),
        patch("src.agents.translation_agent.get_bot_identity_service", return_value=identity_service),
        patch("src.agents.translation_agent.privilege_service.is_admin", return_value=False),
        patch("src.agents.translation_agent.privilege_service.is_privileged", return_value=False),
        patch("src.services.news_session_manager.news_session_manager.is_in_news_flow", return_value=False),
    ):
        assert await agent.should_handle(event, "ms green stop") is False

    translation_service.translate.assert_not_awaited()
    line_bot_api.reply_message.assert_not_called()


def test_sleep_command_matches_all_identity_aliases():
    agent = TranslationAgent()
    identity_service = _make_identity_service("ms. green", "ms green")

    with patch(
        "src.agents.translation_agent.get_bot_identity_service",
        return_value=identity_service,
    ):
        assert agent.is_sleep_command("ms. green stop") is True
        assert agent.is_sleep_command("ms green stop") is True
        assert agent.is_sleep_command("thank you ms. green") is True
        assert agent.is_sleep_command("good night ms green") is True