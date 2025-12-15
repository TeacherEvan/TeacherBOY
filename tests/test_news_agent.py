"""Basic smoke tests for NewsAgent functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock
from src.agents.news_agent import NewsAgent
from src.services.news_data_service import NewsDataService
from src.services.news_session_manager import news_session_manager


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    return AsyncMock()


@pytest.fixture
def news_data_service(mock_http_client):
    """Create NewsDataService instance."""
    return NewsDataService(http_client=mock_http_client, news_api_key=None)


@pytest.fixture
def news_agent(news_data_service):
    """Create NewsAgent instance."""
    return NewsAgent(news_data_service=news_data_service)


@pytest.mark.asyncio
async def test_news_agent_initialization(news_agent):
    """Test that NewsAgent initializes correctly."""
    assert news_agent.name == "NewsAgent"
    assert news_agent.get_priority() == 15
    assert news_agent.is_enabled()


@pytest.mark.asyncio
async def test_news_trigger_detection(news_agent):
    """Test news trigger word detection."""
    # Create mock event
    mock_event = MagicMock()
    mock_event.source = MagicMock()
    mock_event.source.user_id = "test_user"
    
    # Test trigger words
    assert await news_agent.should_handle(mock_event, "news")
    assert await news_agent.should_handle(mock_event, "News")
    assert await news_agent.should_handle(mock_event, "ข่าว")
    
    # Test non-trigger words
    assert not await news_agent.should_handle(mock_event, "hello")
    assert not await news_agent.should_handle(mock_event, "translate")


@pytest.mark.asyncio
async def test_line_system_message_ignored(news_agent):
    """Test that LINE system messages are ignored."""
    mock_event = MagicMock()
    mock_event.source = MagicMock()
    mock_event.source.user_id = "test_user"
    
    # LINE system messages should be ignored
    assert not await news_agent.should_handle(mock_event, "[System]")
    assert not await news_agent.should_handle(mock_event, "[Name]")


def test_session_manager_initialization():
    """Test that session manager initializes correctly."""
    chat_id = "user_test123"
    
    # Clean up any existing session
    news_session_manager.end_news_flow(chat_id)
    
    # Should not be in flow initially
    assert not news_session_manager.is_in_news_flow(chat_id)
    
    # Start news flow
    news_session_manager.start_news_flow(chat_id)
    assert news_session_manager.is_in_news_flow(chat_id)
    
    # Get session state
    session = news_session_manager.get_session_state(chat_id)
    assert session is not None
    assert session["step"] == "language_selection"
    assert session["language"] is None
    
    # Clean up
    news_session_manager.end_news_flow(chat_id)
    assert not news_session_manager.is_in_news_flow(chat_id)


def test_session_language_selection():
    """Test language selection in session."""
    chat_id = "user_test456"
    
    # Clean up
    news_session_manager.end_news_flow(chat_id)
    
    # Start and select language
    news_session_manager.start_news_flow(chat_id)
    news_session_manager.set_language(chat_id, "th")
    
    session = news_session_manager.get_session_state(chat_id)
    assert session["language"] == "th"
    assert session["step"] == "main_menu"
    
    # Clean up
    news_session_manager.end_news_flow(chat_id)
