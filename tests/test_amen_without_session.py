"""Test that 'amen' sleep command works without an active session."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from linebot.v3.webhooks import MessageEvent, TextMessageContent, Source
from linebot.v3.messaging import MessagingApi

from src.agents.translation_agent import TranslationAgent
from src.config import Settings
from src.services.session_manager import session_manager


def create_mock_event(text: str, user_id: str = "U_TEST", group_id: str = None):
    """Create a mock LINE message event."""
    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = text
    event.reply_token = "test_reply_token"
    
    # Set up source
    source = MagicMock(spec=Source)
    source.user_id = user_id
    if group_id:
        source.group_id = group_id
    else:
        source.group_id = None
    source.room_id = None
    event.source = source
    
    return event


@pytest.fixture
def translation_agent():
    """Create a TranslationAgent instance for testing."""
    return TranslationAgent()


@pytest.fixture
def mock_line_api():
    """Create a mock LINE API."""
    return MagicMock(spec=MessagingApi)


@pytest.mark.asyncio
async def test_amen_without_active_session(translation_agent, mock_line_api):
    """Test that 'amen' works even without an active translation session."""
    # Clear any existing sessions
    chat_id = "user_U_TEST"
    session_manager.end_session(chat_id)
    session_manager.wake_chat(chat_id)
    
    # Verify no active session
    assert not session_manager.is_session_active(chat_id)
    assert not session_manager.is_sleeping(chat_id)
    
    # Send 'amen' command
    event = create_mock_event("amen", user_id="U_TEST")
    
    # should_handle should return True for sleep command
    should_handle = await translation_agent.should_handle(event, "amen")
    assert should_handle is True, "TranslationAgent should handle 'amen' even without active session"
    
    # Handle the command
    result = await translation_agent.handle(event, "amen", mock_line_api)
    assert result is True, "TranslationAgent should successfully handle 'amen'"
    
    # Verify the chat is now sleeping
    assert session_manager.is_sleeping(chat_id), "Chat should be sleeping after 'amen' command"
    
    # Verify a reply was sent
    assert mock_line_api.reply_message.called, "Should send a reply message"


@pytest.mark.asyncio
async def test_amen_variations_without_session(translation_agent, mock_line_api):
    """Test various 'amen' variations work without an active session."""
    variations = ["amen", "Amen", "AMEN", "amen!", "amen."]
    
    for variation in variations:
        # Clear state
        chat_id = "user_U_TEST"
        session_manager.end_session(chat_id)
        session_manager.wake_chat(chat_id)
        mock_line_api.reset_mock()
        
        # Verify no active session
        assert not session_manager.is_session_active(chat_id)
        
        # Send variation
        event = create_mock_event(variation, user_id="U_TEST")
        
        # should_handle should return True
        should_handle = await translation_agent.should_handle(event, variation)
        assert should_handle is True, f"Should handle '{variation}' without active session"
        
        # Handle the command
        result = await translation_agent.handle(event, variation, mock_line_api)
        assert result is True, f"Should successfully handle '{variation}'"
        
        # Verify sleeping
        assert session_manager.is_sleeping(chat_id), f"Should be sleeping after '{variation}'"


@pytest.mark.asyncio
async def test_amen_with_active_session_still_works(translation_agent, mock_line_api):
    """Test that 'amen' still works when there IS an active session (regression test)."""
    chat_id = "user_U_TEST"
    
    # Clear state and start a session
    session_manager.end_session(chat_id)
    session_manager.wake_chat(chat_id)
    session_manager.start_session(chat_id, "U_TEST")
    
    # Verify session is active
    assert session_manager.is_session_active(chat_id)
    assert not session_manager.is_sleeping(chat_id)
    
    # Send 'amen' command
    event = create_mock_event("amen", user_id="U_TEST")
    
    # should_handle should return True
    should_handle = await translation_agent.should_handle(event, "amen")
    assert should_handle is True, "Should handle 'amen' with active session"
    
    # Handle the command
    result = await translation_agent.handle(event, "amen", mock_line_api)
    assert result is True, "Should successfully handle 'amen' with active session"
    
    # Verify sleeping
    assert session_manager.is_sleeping(chat_id), "Should be sleeping after 'amen'"
    
    # Verify reply was sent
    assert mock_line_api.reply_message.called, "Should send a reply message"
