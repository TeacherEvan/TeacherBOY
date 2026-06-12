import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from src.agents.mod_mode_agent import ModModeAgent


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_services():
    with patch("src.agents.mod_mode_agent.ModModeService") as mm, \
         patch("src.agents.mod_mode_agent.BanListService") as bl, \
         patch("src.agents.mod_mode_agent.WarningService") as ws, \
         patch("src.agents.mod_mode_agent.HarmfulContentDetector") as hc, \
         patch("src.agents.mod_mode_agent.ModAuditLog") as al, \
         patch("src.agents.mod_mode_agent.ModDashboardBuilder") as db:
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
        with patch.object(agent, "_reply", new_callable=AsyncMock) as mock_reply:
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