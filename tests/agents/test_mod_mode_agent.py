from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.agents.mod_mode_agent import ModModeAgent


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_services():
    with (
        patch("src.agents.mod_mode_agent.ModModeService") as mm,
        patch("src.agents.mod_mode_agent.BanListService") as bl,
        patch("src.agents.mod_mode_agent.WarningService") as ws,
        patch("src.agents.mod_mode_agent.HarmfulContentDetector") as hc,
        patch("src.agents.mod_mode_agent.ModAuditLog") as al,
        patch("src.agents.mod_mode_agent.ModDashboardBuilder") as db,
    ):
        yield {
            "mod_mode": mm.return_value,
            "ban_list": bl.return_value,
            "warning": ws.return_value,
            "detector": hc.return_value,
            "audit": al.return_value,
            "dashboard": db.return_value,
        }


@pytest.fixture
def agent(mock_services):
    return ModModeAgent(
        mod_mode_service=mock_services["mod_mode"],
        ban_list_service=mock_services["ban_list"],
        warning_service=mock_services["warning"],
        harmful_detector=mock_services["detector"],
        audit_log=mock_services["audit"],
        dashboard_builder=mock_services["dashboard"],
    )


@pytest.fixture
def event_factory():
    def _make(text: str, user_id: str = "U999", group_id: str = "C123", source_type: str = "group"):
        source = MagicMock()
        source.type = source_type
        source.user_id = user_id
        if source_type == "group":
            source.group_id = group_id
        elif source_type == "room":
            source.room_id = group_id
        msg = MagicMock(spec=TextMessageContent)
        msg.text = text
        event = MagicMock(spec=MessageEvent)
        event.message = msg
        event.source = source
        event.reply_token = "test_token"
        return event

    return _make


@pytest.fixture(autouse=True)
def _setup_default_mocks(mock_services):
    """Setup default async mocks for all services to avoid repetitive setup in each test."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    mock_services["mod_mode"].get_mod_mode_info = _make_async_mock(None)
    mock_services["ban_list"].is_banned = _make_async_mock(False)
    mock_services["warning"].warn_user = _make_async_mock({"count": 1, "should_ban": False, "reason": ""})
    mock_services["detector"].detect = _make_async_mock({"is_harmful": False, "matched_keywords": [], "method": "none"})
    mock_services["audit"].log_kick = _make_async_mock(None)
    mock_services["audit"].log_warn = _make_async_mock(None)
    mock_services["audit"].log_ban = _make_async_mock(None)
    mock_services["audit"].log_mode_change = _make_async_mock(None)
    yield


@pytest.mark.asyncio
async def test_should_handle_mod_group(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    event = event_factory("hello", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True


@pytest.mark.asyncio
async def test_should_handle_non_mod_group(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    event = event_factory("hello", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is False


@pytest.mark.asyncio
async def test_should_handle_private_chat_false(agent, mock_services, event_factory):
    event = event_factory("hello", group_id="U123", source_type="user")
    result = await agent.should_handle(event, "hello")
    assert result is False


@pytest.mark.asyncio
async def test_should_handle_activation_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    event = event_factory("activate mod mode", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "activate mod mode")
        assert result is True


@pytest.mark.asyncio
async def test_should_handle_banned_user(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["ban_list"].is_banned = _make_async_mock(True)
    event = event_factory("hello", user_id="U999", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True


@pytest.mark.asyncio
async def test_should_handle_special_mode_blocks_non_allowed(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(False)
    mock_services["ban_list"].is_banned = _make_async_mock(False)
    event = event_factory("hello", user_id="U999", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True


@pytest.mark.asyncio
async def test_get_priority(agent):
    assert agent.get_priority() == 4


@pytest.mark.asyncio
async def test_handle_activates_mod_mode(agent, mock_services, event_factory):
    mock_services["mod_mode"].activate_mod_mode = _make_async_mock({"mode": "all", "isActive": True})
    mock_services["audit"].log_mode_change = _make_async_mock(None)
    event = event_factory("activate mod mode", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_reply", new_callable=AsyncMock):
            result = await agent.handle(event, "activate mod mode", MagicMock())
            assert result is True
            mock_services["mod_mode"].activate_mod_mode.assert_called_once()


@pytest.mark.asyncio
async def test_handle_modmode_all_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].activate_mod_mode = _make_async_mock({"mode": "all", "isActive": True})
    mock_services["audit"].log_mode_change = _make_async_mock(None)
    event = event_factory("/modmode all", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_reply", new_callable=AsyncMock):
            result = await agent.handle(event, "/modmode all", MagicMock())
            assert result is True
            mock_services["mod_mode"].activate_mod_mode.assert_called_with("C123", "U456", "all")


@pytest.mark.asyncio
async def test_handle_modmode_off_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].deactivate_mod_mode = _make_async_mock(True)
    mock_services["audit"].log_mode_change = _make_async_mock(None)
    event = event_factory("/modmode off", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_reply", new_callable=AsyncMock):
            result = await agent.handle(event, "/modmode off", MagicMock())
            assert result is True
            mock_services["mod_mode"].deactivate_mod_mode.assert_called_with("C123")


@pytest.mark.asyncio
async def test_handle_kick_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["audit"].log_kick = _make_async_mock(None)
    event = event_factory("/modmode kick @U123", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_kick_user", new_callable=AsyncMock) as mock_kick:
            mock_kick.return_value = True
            result = await agent.handle(event, "/modmode kick @U123", MagicMock())

    assert result is True
    mock_kick.assert_called_once()
    args, kwargs = mock_kick.call_args
    assert args[0] == "C123"
    assert args[1] == "U123"
    assert args[3] == "Kicked via /modmode kick"
    mock_services["audit"].log_kick.assert_called_once()


@pytest.mark.asyncio
async def test_handle_warn_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["warning"].warn_user = _make_async_mock({"count": 1, "should_ban": False, "reason": "Test reason"})
    mock_services["audit"].log_warn = _make_async_mock(None)
    event = event_factory("/modmode warn @U123 spam", user_id="U456", group_id="C123")

    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.handle(event, "/modmode warn @U123 spam", MagicMock())

    assert result is True
    mock_services["warning"].warn_user.assert_called_once_with("C123", "U123", "U456", "spam")
    mock_services["audit"].log_warn.assert_called_once()


@pytest.mark.asyncio
async def test_handle_ban_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["ban_list"].ban_user = _make_async_mock({"groupId": "C123", "userId": "U123"})
    mock_services["audit"].log_ban = _make_async_mock(None)
    mock_services["audit"].log_kick = _make_async_mock(None)
    event = event_factory("/modmode ban @U123 repeated spam", user_id="U456", group_id="C123")

    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        with patch.object(agent, "_kick_user", new_callable=AsyncMock) as mock_kick:
            mock_kick.return_value = True
            result = await agent.handle(event, "/modmode ban @U123 repeated spam", MagicMock())

    assert result is True
    mock_services["ban_list"].ban_user.assert_called_once_with("C123", "U123", "U456", "repeated spam")
    mock_kick.assert_called_once()
    mock_services["audit"].log_ban.assert_called_once()
    mock_services["audit"].log_kick.assert_called_once()


@pytest.mark.asyncio
async def test_handle_unban_command(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(True)
    mock_services["ban_list"].unban_user = _make_async_mock(True)
    mock_services["audit"].log_mode_change = _make_async_mock(None)
    event = event_factory("/modmode unban @U123", user_id="U456", group_id="C123")

    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.handle(event, "/modmode unban @U123", MagicMock())

    assert result is True
    mock_services["ban_list"].unban_user.assert_called_once_with("C123", "U123")
    mock_services["audit"].log_mode_change.assert_called_once()


@pytest.mark.asyncio
async def test_should_handle_modmode_special_command_activates_mod_mode(agent, mock_services, event_factory):
    """Test that /modmode special is handled even when mod mode is not active (it activates mod mode)."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    event = event_factory("/modmode special @U123", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "/modmode special @U123")
        assert result is True


@pytest.mark.asyncio
async def test_should_handle_modmode_all_command_activates_mod_mode(agent, mock_services, event_factory):
    """Test that /modmode all is handled even when mod mode is not active (it activates mod mode)."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    event = event_factory("/modmode all", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "/modmode all")
        assert result is True


@pytest.mark.asyncio
async def test_should_handle_modmode_dashboard_requires_active_mod_mode(agent, mock_services, event_factory):
    """Test that /modmode dashboard is NOT handled when mod mode is not active (doesn't activate mod mode)."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    event = event_factory("/modmode dashboard", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "/modmode dashboard")
        assert result is False


@pytest.mark.asyncio
async def test_should_handle_modmode_off_requires_active_mod_mode(agent, mock_services, event_factory):
    """Test that /modmode off is NOT handled when mod mode is not active."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    event = event_factory("/modmode off", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "/modmode off")
        assert result is False


@pytest.mark.asyncio
async def test_should_handle_modmode_all_with_trailing_punctuation(agent, mock_services, event_factory):
    """Test that /modmode all... (with trailing punctuation) is handled."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    event = event_factory("/modmode all...", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "/modmode all...")
        assert result is True


@pytest.mark.asyncio
async def test_should_handle_modmode_special_with_trailing_punctuation(agent, mock_services, event_factory):
    """Test that /modmode special... (with trailing punctuation) is handled."""
    mock_services["mod_mode"].is_mod_mode_active = _make_async_mock(False)
    mock_services["mod_mode"].is_user_allowed = _make_async_mock(True)
    event = event_factory("/modmode special @U123...", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "/modmode special @U123...")
        assert result is True


@pytest.fixture
def agent_none_services():
    return ModModeAgent(
        mod_mode_service=None,
        ban_list_service=None,
        warning_service=None,
        harmful_detector=None,
        audit_log=None,
        dashboard_builder=MagicMock(),
    )


@pytest.mark.asyncio
async def test_should_handle_commands_when_services_are_none(agent_none_services, event_factory):
    # Activation command should still be handled (to show the service unavailable error message)
    event1 = event_factory("activate mod mode", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        assert await agent_none_services.should_handle(event1, "activate mod mode") is True

    # Any /modmode command should be handled if admin
    event2 = event_factory("/modmode dashboard", user_id="U456", group_id="C123")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        assert await agent_none_services.should_handle(event2, "/modmode dashboard") is True


@pytest.mark.asyncio
async def test_handle_commands_when_services_are_none(agent_none_services, event_factory):
    event = event_factory("/modmode dashboard", user_id="U456", group_id="C123")
    line_bot_api = MagicMock()
    with patch.object(agent_none_services, "_reply", new_callable=AsyncMock) as mock_reply:
        with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
            result = await agent_none_services.handle(event, "/modmode dashboard", line_bot_api)
            assert result is True
            mock_reply.assert_called_once()
            args, _ = mock_reply.call_args
            assert "unavailable" in args[1].lower() or "not configured" in args[1].lower()


@pytest.mark.asyncio
async def test_warn_user_handles_none_audit(event_factory):
    mock_warnings = AsyncMock()
    mock_warnings.warn_user.return_value = {"count": 1, "should_ban": False, "reason": "spam"}
    agent_no_audit = ModModeAgent(
        mod_mode_service=AsyncMock(),
        ban_list_service=AsyncMock(),
        warning_service=mock_warnings,
        harmful_detector=AsyncMock(),
        audit_log=None,
        dashboard_builder=MagicMock(),
    )
    event = event_factory("hello", user_id="U999", group_id="C123")
    with patch.object(agent_no_audit, "_reply", new_callable=AsyncMock) as mock_reply:
        res = await agent_no_audit._warn_user(event, "C123", "U999", MagicMock(), "spam")
        assert res is True
        mock_reply.assert_called_once()

