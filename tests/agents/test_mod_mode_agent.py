import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from src.agents.mod_mode_agent import ModModeAgent


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
    return ModModeAgent()


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


@pytest.mark.asyncio
async def test_should_handle_mod_group(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = True
    mock_services["mod_mode"].is_user_allowed.return_value = True
    event = event_factory("hello", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True


@pytest.mark.asyncio
async def test_should_handle_non_mod_group(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = False
    event = event_factory("hello", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is False


@pytest.mark.asyncio
async def test_should_handle_private_chat_false(agent, mock_services, event_factory):
    event = event_factory("hello", group_id="U123", source_type="user")
    result = await agent.should_handle(event, "hello")
    assert result is False


@pytest.mark.asyncio
async def test_should_handle_banned_user(agent, mock_services, event_factory):
    mock_services["mod_mode"].is_mod_mode_active.return_value = True
    mock_services["ban_list"].is_banned.return_value = True
    event = event_factory("hello", user_id="U999", group_id="C123")
    result = await agent.should_handle(event, "hello")
    assert result is True


@pytest.mark.asyncio
async def test_get_priority(agent):
    assert agent.get_priority() == 4