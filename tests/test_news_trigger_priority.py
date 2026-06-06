"""Test that news triggers are handled by NewsAgent, not TranslationAgent.

This test addresses the issue where TranslationAgent was intercepting
news trigger keywords ("news", "ข่าว") before NewsAgent could handle them,
causing translation instead of showing the news menu.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.news_agent import NewsAgent
from src.agents.translation_agent import TranslationAgent
from src.services.news_data_service import NewsDataService
from src.services.news_session_manager import news_session_manager
from src.services.session_manager import session_manager


@pytest.fixture
def translation_agent():
    """Create TranslationAgent instance."""
    return TranslationAgent()


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


@pytest.fixture
def mock_event_group():
    """Create mock event for group chat."""
    mock_event = MagicMock()
    mock_event.source = MagicMock()
    mock_event.source.user_id = "test_user_123"
    mock_event.source.group_id = "test_group_456"
    return mock_event


@pytest.fixture
def mock_event_private():
    """Create mock event for private chat."""
    mock_event = MagicMock()
    mock_event.source = MagicMock()
    mock_event.source.user_id = "test_user_789"
    # No group_id or room_id = private chat
    return mock_event


@pytest.mark.asyncio
async def test_translation_agent_skips_news_trigger(translation_agent, mock_event_group):
    """Test that TranslationAgent does NOT handle news trigger keywords."""
    # Clean up any existing session
    chat_id = "group_test_group_456"
    session_manager.end_session(chat_id)

    # Test that TranslationAgent skips "news"
    should_handle = await translation_agent.should_handle(mock_event_group, "news")
    assert not should_handle, "TranslationAgent should NOT handle 'news' trigger"

    # Test that TranslationAgent skips "ข่าว"
    should_handle = await translation_agent.should_handle(mock_event_group, "ข่าว")
    assert not should_handle, "TranslationAgent should NOT handle 'ข่าว' trigger"

    # Thai transliteration: "นิวส์"
    should_handle = await translation_agent.should_handle(mock_event_group, "นิวส์")
    assert not should_handle, "TranslationAgent should NOT handle 'นิวส์' trigger"

    # Test with different casing
    should_handle = await translation_agent.should_handle(mock_event_group, "News")
    assert not should_handle, "TranslationAgent should NOT handle 'News' trigger"

    should_handle = await translation_agent.should_handle(mock_event_group, "NEWS")
    assert not should_handle, "TranslationAgent should NOT handle 'NEWS' trigger"


@pytest.mark.asyncio
async def test_translation_agent_skips_news_even_with_active_session(translation_agent, mock_event_group):
    """Test that TranslationAgent skips news triggers even when translation session is active."""
    chat_id = "group_test_group_456"

    # Start a translation session
    session_manager.start_session(chat_id, "test_user_123")
    assert session_manager.is_session_active(chat_id), "Session should be active"

    try:
        # Even with active session, TranslationAgent should skip news triggers
        should_handle = await translation_agent.should_handle(mock_event_group, "news")
        assert not should_handle, "TranslationAgent should NOT handle 'news' even with active session"

        should_handle = await translation_agent.should_handle(mock_event_group, "ข่าว")
        assert not should_handle, "TranslationAgent should NOT handle 'ข่าว' even with active session"

        should_handle = await translation_agent.should_handle(mock_event_group, "นิวส์")
        assert not should_handle, "TranslationAgent should NOT handle 'นิวส์' even with active session"
    finally:
        # Clean up
        session_manager.end_session(chat_id)


@pytest.mark.asyncio
async def test_translation_agent_auto_handles_thai_text(translation_agent, mock_event_group):
    """Thai text should auto-start translation session (behavior restored Jun 2)."""
    chat_id = "group_test_group_456"
    session_manager.end_session(chat_id)

    # TranslationAgent SHOULD handle plain Thai text (auto-translation enabled).
    should_handle = await translation_agent.should_handle(mock_event_group, "สวัสดี")
    assert should_handle, "TranslationAgent should handle Thai text to auto-start session"

    should_handle = await translation_agent.should_handle(mock_event_group, "ขอบคุณครับ")
    assert should_handle, "TranslationAgent should handle Thai text to auto-start session"


@pytest.mark.asyncio
async def test_news_agent_handles_news_trigger(news_agent, mock_event_group):
    """Test that NewsAgent handles news trigger keywords."""
    chat_id = "group_test_group_456"
    news_session_manager.end_news_flow(chat_id)

    # NewsAgent should handle "news"
    should_handle = await news_agent.should_handle(mock_event_group, "news")
    assert should_handle, "NewsAgent should handle 'news' trigger"

    # NewsAgent should handle "ข่าว"
    should_handle = await news_agent.should_handle(mock_event_group, "ข่าว")
    assert should_handle, "NewsAgent should handle 'ข่าว' trigger"

    # NewsAgent should handle Thai transliteration: "นิวส์"
    should_handle = await news_agent.should_handle(mock_event_group, "นิวส์")
    assert should_handle, "NewsAgent should handle 'นิวส์' trigger"

    # Clean up
    news_session_manager.end_news_flow(chat_id)


@pytest.mark.asyncio
async def test_priority_order_correct():
    """Test that agent priorities are set correctly for proper routing."""
    translation_agent = TranslationAgent()

    mock_http_client = AsyncMock()
    news_data_service = NewsDataService(http_client=mock_http_client, news_api_key=None)
    news_agent = NewsAgent(news_data_service=news_data_service)

    # Verify priorities
    assert translation_agent.get_priority() == 10, "TranslationAgent priority should be 10"
    assert news_agent.get_priority() == 15, "NewsAgent priority should be 15"

    # Lower number = higher priority, so TranslationAgent runs FIRST
    # But it should skip news triggers to let NewsAgent handle them


@pytest.mark.asyncio
async def test_is_news_trigger_method(translation_agent):
    """Test the is_news_trigger() helper method."""
    # Positive cases
    assert translation_agent.is_news_trigger("news")
    assert translation_agent.is_news_trigger("News")
    assert translation_agent.is_news_trigger("NEWS")
    assert translation_agent.is_news_trigger("ข่าว")
    assert translation_agent.is_news_trigger("นิวส์")
    assert translation_agent.is_news_trigger(" news ")
    assert translation_agent.is_news_trigger(" ข่าว ")

    # Allow trailing punctuation
    assert translation_agent.is_news_trigger("news!")
    assert translation_agent.is_news_trigger("ข่าว.")
    assert translation_agent.is_news_trigger("นิวส์!")

    # Negative cases
    assert not translation_agent.is_news_trigger("new")
    assert not translation_agent.is_news_trigger("newspaper")
    assert not translation_agent.is_news_trigger("hello")
    assert not translation_agent.is_news_trigger("สวัสดี")
    assert not translation_agent.is_news_trigger("")


@pytest.mark.asyncio
async def test_news_agent_thai_alias_sets_th_language(news_agent, mock_event_group):
    """Typing Thai 'news' (e.g., นิวส์) should start Thai menu, not English."""
    chat_id = "group_test_group_456"
    news_session_manager.end_news_flow(chat_id)

    mock_line_bot_api = MagicMock()
    mock_event_group.reply_token = "reply_token_123"

    with (
        patch.object(news_agent, "_is_friend", new_callable=AsyncMock, return_value=True),
        patch.object(news_agent, "_send_main_menu", new_callable=AsyncMock) as mock_send_menu,
    ):
        handled = await news_agent.handle(mock_event_group, "นิวส์", mock_line_bot_api)
        assert handled is True
        assert mock_send_menu.call_count == 1
        # args: (event, line_bot_api, language)
        assert mock_send_menu.call_args[0][2] == "th"

    news_session_manager.end_news_flow(chat_id)
