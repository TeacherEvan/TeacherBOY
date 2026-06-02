"""Tests for the interactive menu feature."""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from linebot.v3.webhooks import MessageEvent
from src.agents.llm_agent import LLMAgent


class TestZeusMenu:
    """Test the interactive menu when user says just 'Ms. Green'."""

    @pytest.fixture
    def agent(self):
        """Create LLMAgent instance."""
        return LLMAgent()

    @pytest.mark.asyncio
    async def test_standalone_ms_green_triggers_menu(self, agent):
        """Test that saying just 'Ms. Green' triggers the interactive menu."""
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123456"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "reply_token"

        should_handle = await agent.should_handle(event, "Ms. Green")
        assert should_handle is True

        assert await agent.should_handle(event, "ms. green") is True
        assert await agent.should_handle(event, "MS. GREEN") is True
        assert await agent.should_handle(event, "  ms green  ") is True
        assert await agent.should_handle(event, "Zeus") is False

    @pytest.mark.asyncio
    async def test_ms_green_with_query_does_not_trigger_menu(self, agent):
        """Test that 'Ms. Green <query>' doesn't trigger menu (goes to LLM)."""
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123456"

        # Mock LLM configuration
        with patch.object(agent, '_is_any_llm_configured', return_value=True):
            # These should be handled but NOT as menu commands
            assert await agent.should_handle(event, "Ms. Green what is the weather") is True
            assert await agent.should_handle(event, "Ms. Green search something") is False  # Reserved for SearchAgent

    @pytest.mark.asyncio
    async def test_menu_shows_all_features(self, agent):
        """Test that menu includes all expected features."""
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123456"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "reply_token"

        line_api = AsyncMock()
        
        # Handle menu command
        result = await agent.handle(event, "Ms. Green", line_api)
        assert result is True

        # Verify reply_message was called with menu
        line_api.reply_message.assert_called_once()
        call_args = line_api.reply_message.call_args
        
        # Extract message from call
        request = call_args[0][0]
        message = request.messages[0]
        
        # Verify message content includes features
        assert "Ms. Green Command Center" in message.text
        assert "Scrape" in message.text
        assert "Add Event" in message.text
        assert "Analyze Image" in message.text
        assert "Profile Image" in message.text
        assert "News" in message.text
        assert "Search" in message.text
        assert "Translate" in message.text
        assert "DR. Hanibal" in message.text
        
        # Verify QuickReply buttons exist
        assert message.quick_reply is not None
        assert len(message.quick_reply.items) >= 10  # At least 10 buttons (including DR. Hanibal)

    @pytest.mark.asyncio
    async def test_menu_includes_admin_for_admins(self, agent):
        """Test that admin users see admin option in menu."""
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U_ADMIN"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "reply_token"

        line_api = AsyncMock()
        
        # Mock admin check
        with patch('src.agents.llm_agent.privilege_service.is_admin', return_value=True):
            result = await agent.handle(event, "Ms. Green", line_api)
            assert result is True

            # Verify admin button exists
            call_args = line_api.reply_message.call_args
            request = call_args[0][0]
            message = request.messages[0]
            
            # Check for admin in text and buttons
            assert "Admin" in message.text
            admin_buttons = [item for item in message.quick_reply.items if "Admin" in item.action.label]
            assert len(admin_buttons) > 0

    @pytest.mark.asyncio
    async def test_menu_hides_admin_for_regular_users(self, agent):
        """Test that regular users don't see admin option."""
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U_REGULAR"
        event.source.group_id = None
        event.source.room_id = None
        event.reply_token = "reply_token"

        line_api = AsyncMock()
        
        # Mock non-admin check
        with patch('src.agents.llm_agent.privilege_service.is_admin', return_value=False):
            result = await agent.handle(event, "Ms. Green", line_api)
            assert result is True

            # Verify no admin button
            call_args = line_api.reply_message.call_args
            request = call_args[0][0]
            message = request.messages[0]
            
            # Admin should not be in QuickReply buttons
            admin_buttons = [item for item in message.quick_reply.items if "Admin" in item.action.label]
            assert len(admin_buttons) == 0
