# tests/integration/test_mod_mode_integration.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.agents.mod_mode_agent import ModModeAgent
from src.agents.agent_router import AgentRouter


@pytest.mark.asyncio
async def test_mod_mode_agent_registration():
    """Test that ModModeAgent can be registered with AgentRouter."""
    # Create a fresh AgentRouter for testing
    router = AgentRouter()
    
    # Create mock services
    mock_mod_mode = AsyncMock()
    mock_ban_list = AsyncMock()
    mock_warning = AsyncMock()
    mock_detector = AsyncMock()
    mock_audit = AsyncMock()
    mock_dashboard = AsyncMock()
    
    # Create ModModeAgent with mock services
    mod_agent = ModModeAgent(
        mod_mode_service=mock_mod_mode,
        ban_list_service=mock_ban_list,
        warning_service=mock_warning,
        harmful_detector=mock_detector,
        audit_log=mock_audit,
        dashboard_builder=mock_dashboard,
    )
    
    # Register the agent
    router.register_agent(mod_agent)
    
    # Verify registration
    agents = router.list_agents()
    mod_agent_info = next((a for a in agents if a["name"] == "ModModeAgent"), None)
    assert mod_agent_info is not None
    assert mod_agent_info["priority"] == 4
    assert "Moderator Mode" in mod_agent_info["description"]


@pytest.mark.asyncio
async def test_mod_mode_agent_should_handle_logic():
    """Test ModModeAgent should_handle logic with mocked services."""
    from unittest.mock import MagicMock
    from linebot.v3.webhooks import MessageEvent, TextMessageContent
    
    def _make_async_mock(return_value):
        mock = AsyncMock()
        mock.return_value = return_value
        return mock
    
    mock_mod_mode = AsyncMock()
    mock_mod_mode.is_mod_mode_active = _make_async_mock(False)
    
    mock_ban_list = AsyncMock()
    mock_warning = AsyncMock()
    mock_detector = AsyncMock()
    mock_audit = AsyncMock()
    mock_dashboard = AsyncMock()
    
    agent = ModModeAgent(
        mod_mode_service=mock_mod_mode,
        ban_list_service=mock_ban_list,
        warning_service=mock_warning,
        harmful_detector=mock_detector,
        audit_log=mock_audit,
        dashboard_builder=mock_dashboard,
    )
    
    # Test: non-mod group returns False
    def _make_event(text: str, group_id: str = "C123", user_id: str = "U999"):
        source = MagicMock()
        source.type = "group"
        source.group_id = group_id
        source.user_id = user_id
        msg = MagicMock(spec=TextMessageContent)
        msg.text = text
        event = MagicMock(spec=MessageEvent)
        event.message = msg
        event.source = source
        event.reply_token = "test_token"
        return event
    
    event = _make_event("hello")
    result = await agent.should_handle(event, "hello")
    assert result is False  # Mod mode not active
    
    # Test: activation command should return True for admin
    mock_mod_mode.is_mod_mode_active = _make_async_mock(False)
    event = _make_event("activate mod mode", user_id="U456")
    with patch("src.services.privilege_service.privilege_service.is_admin", return_value=True):
        result = await agent.should_handle(event, "activate mod mode")
        assert result is True