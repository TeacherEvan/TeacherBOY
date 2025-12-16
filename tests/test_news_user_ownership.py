"""Test user-specific news interaction and shutdown phrase support."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import MessagingApi

from src.agents.news_agent import NewsAgent, news_rate_limiter_friend
from src.services.news_data_service import NewsDataService
from src.services.news_session_manager import news_session_manager


@pytest.fixture
def mock_news_data_service():
    """Create a mock NewsDataService."""
    service = MagicMock(spec=NewsDataService)
    service.get_weather_data = AsyncMock(return_value={
        "temperature": 28,
        "pm25": 45,
        "will_rain": False
    })
    service.get_news_headlines = AsyncMock(return_value=[
        {"title": "Test Headline 1", "url": "http://example.com/1"},
        {"title": "Test Headline 2", "url": "http://example.com/2"}
    ])
    return service


@pytest.fixture
def news_agent(mock_news_data_service):
    """Create a NewsAgent instance with mocked service."""
    return NewsAgent(news_data_service=mock_news_data_service)


@pytest.fixture
def mock_line_api():
    """Create a mock LINE Messaging API."""
    api = MagicMock(spec=MessagingApi)
    api.reply_message = MagicMock()
    
    # Mock get_profile for friend verification
    mock_profile = MagicMock()
    mock_profile.user_id = "U1234567890"
    api.get_profile = MagicMock(return_value=mock_profile)
    
    return api


def create_mock_event(text: str, user_id: str = "U1234567890", group_id: str = "G1234567890"):
    """Create a mock LINE message event."""
    event = MagicMock(spec=MessageEvent)
    event.reply_token = "test_reply_token"
    
    # Create message
    message = MagicMock(spec=TextMessageContent)
    message.text = text
    event.message = message
    
    # Create source
    source = MagicMock()
    source.user_id = user_id
    source.group_id = group_id
    source.type = "group"
    event.source = source
    
    return event


@pytest.mark.asyncio
async def test_only_session_owner_can_interact(news_agent, mock_line_api):
    """Test that only the user who started the news session can interact with it."""
    # Clear any existing sessions
    news_session_manager._news_sessions.clear()
    
    # User1 starts news flow
    event1 = create_mock_event("news", user_id="U_USER1", group_id="G_TEST")
    
    # Handle trigger
    result = await news_agent.handle(event1, "news", mock_line_api)
    assert result is True
    
    # Verify session started with user1
    session = news_session_manager.get_session_state("group_G_TEST")
    assert session is not None
    assert session["user_id"] == "U_USER1"
    
    # User2 tries to select menu option
    event2 = create_mock_event("1", user_id="U_USER2", group_id="G_TEST")
    
    # This should be silently ignored
    result = await news_agent.handle(event2, "1", mock_line_api)
    assert result is True  # Handled but ignored
    
    # Session should still be in main_menu (not advanced)
    session = news_session_manager.get_session_state("group_G_TEST")
    assert session["step"] == "main_menu"
    
    # User1 can still interact
    event3 = create_mock_event("1", user_id="U_USER1", group_id="G_TEST")
    result = await news_agent.handle(event3, "1", mock_line_api)
    assert result is True
    
    # Cleanup
    news_session_manager.end_news_flow("group_G_TEST")


@pytest.mark.asyncio
async def test_shutdown_phrase_ends_news_session(news_agent, mock_line_api):
    """Test that 'thank you teacherboy' ends the news session immediately."""
    # Clear any existing sessions and rate limiter
    news_session_manager._news_sessions.clear()
    news_rate_limiter_friend.reset_chat("group_G_TEST")
    
    # Start news flow
    event1 = create_mock_event("news", user_id="U_USER1", group_id="G_TEST")
    result = await news_agent.handle(event1, "news", mock_line_api)
    assert result is True
    
    # Verify session exists
    session = news_session_manager.get_session_state("group_G_TEST")
    assert session is not None
    
    # Send shutdown phrase
    event2 = create_mock_event("thank you teacherboy", user_id="U_USER1", group_id="G_TEST")
    result = await news_agent.handle(event2, "thank you teacherboy", mock_line_api)
    assert result is True
    
    # Session should be ended
    session = news_session_manager.get_session_state("group_G_TEST")
    assert session is None
    
    # Verify goodbye message was sent
    assert mock_line_api.reply_message.called


@pytest.mark.asyncio
async def test_shutdown_phrase_variations(news_agent, mock_line_api):
    """Test various shutdown phrase variations."""
    shutdown_phrases = [
        "thank you teacherboy",
        "thanks teacherboy",
        "thank you teacherboi",
        "thx teacherboy",
        "ty teacherboy",
        "ขอบคุณ teacherboy",
        "ขอบใจ teacherboy",
        "Thank You TeacherBoy!",  # Case insensitive and with punctuation
    ]
    
    for phrase in shutdown_phrases:
        # Clear sessions and rate limiter
        news_session_manager._news_sessions.clear()
        news_rate_limiter_friend.reset_chat("group_G_TEST")
        
        # Start news flow
        event1 = create_mock_event("news", user_id="U_USER1", group_id="G_TEST")
        await news_agent.handle(event1, "news", mock_line_api)
        
        # Verify session exists
        session = news_session_manager.get_session_state("group_G_TEST")
        assert session is not None, f"Session should exist before shutdown: {phrase}"
        
        # Send shutdown phrase
        event2 = create_mock_event(phrase, user_id="U_USER1", group_id="G_TEST")
        result = await news_agent.handle(event2, phrase, mock_line_api)
        assert result is True, f"Should handle shutdown phrase: {phrase}"
        
        # Session should be ended
        session = news_session_manager.get_session_state("group_G_TEST")
        assert session is None, f"Session should end with phrase: {phrase}"


@pytest.mark.asyncio
async def test_shutdown_during_menu_interaction(news_agent, mock_line_api):
    """Test that shutdown works even in the middle of menu interaction."""
    # Clear any existing sessions and rate limiter
    news_session_manager._news_sessions.clear()
    news_rate_limiter_friend.reset_chat("group_G_TEST")
    
    # Start news flow and advance to menu
    event1 = create_mock_event("news", user_id="U_USER1", group_id="G_TEST")
    await news_agent.handle(event1, "news", mock_line_api)
    
    # User is at main_menu
    session = news_session_manager.get_session_state("group_G_TEST")
    assert session["step"] == "main_menu"
    
    # User can shut down from menu
    event2 = create_mock_event("thank you teacherboy", user_id="U_USER1", group_id="G_TEST")
    result = await news_agent.handle(event2, "thank you teacherboy", mock_line_api)
    assert result is True
    
    # Session ended
    session = news_session_manager.get_session_state("group_G_TEST")
    assert session is None


@pytest.mark.asyncio
async def test_session_owner_check_method(news_agent):
    """Test the is_session_owner method in news_session_manager."""
    # Clear sessions
    news_session_manager._news_sessions.clear()
    
    chat_id = "group_G_TEST"
    
    # No session - anyone can start
    assert news_session_manager.is_session_owner(chat_id, "U_USER1") is True
    assert news_session_manager.is_session_owner(chat_id, "U_USER2") is True
    
    # Create session with user1
    news_session_manager.start_news_flow(chat_id, "U_USER1")
    
    # User1 is owner
    assert news_session_manager.is_session_owner(chat_id, "U_USER1") is True
    
    # User2 is not owner
    assert news_session_manager.is_session_owner(chat_id, "U_USER2") is False
    
    # Cleanup
    news_session_manager.end_news_flow(chat_id)


@pytest.mark.asyncio
async def test_shutdown_phrase_detection_method(news_agent):
    """Test the _is_shutdown_phrase method."""
    assert news_agent._is_shutdown_phrase("thank you teacherboy") is True
    assert news_agent._is_shutdown_phrase("thanks teacherboy") is True
    assert news_agent._is_shutdown_phrase("thx teacherboy") is True
    assert news_agent._is_shutdown_phrase("Thank You TeacherBoy!") is True
    assert news_agent._is_shutdown_phrase("ขอบคุณ teacherboy") is True
    
    # Should not match
    assert news_agent._is_shutdown_phrase("teacherboy") is False
    assert news_agent._is_shutdown_phrase("hello teacherboy") is False
    assert news_agent._is_shutdown_phrase("thank you") is False
    assert news_agent._is_shutdown_phrase("news") is False
