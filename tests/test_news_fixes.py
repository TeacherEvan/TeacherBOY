"""Tests for news feature fixes: headline links and RSS error handling."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.news_agent import NewsAgent
from src.agents.special_news_agent import SpecialNewsAgent
from src.services.news_data_service import NewsDataService
from src.services.special_news_service import SpecialNewsService
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


@pytest.fixture
def special_news_service(mock_http_client):
    """Create SpecialNewsService instance."""
    return SpecialNewsService(http_client=mock_http_client)


@pytest.fixture
def special_news_agent(special_news_service):
    """Create SpecialNewsAgent instance."""
    return SpecialNewsAgent(news_service=special_news_service)


@pytest.fixture
def mock_event():
    """Create a mock MessageEvent."""
    event = MagicMock()
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"
    event.reply_token = "reply_token_123"
    return event


@pytest.fixture
def mock_line_bot_api():
    """Create a mock MessagingApi."""
    api = MagicMock()
    api.reply_message = MagicMock()
    api.get_profile = MagicMock(return_value={"userId": "test_user"})
    return api


class TestHeadlineLinkFixes:
    """Test fixes for headline link issues."""

    @pytest.mark.asyncio
    async def test_headline_with_url_shows_link(self, news_agent, mock_event, mock_line_bot_api):
        """Test that headlines with URLs show the link correctly."""
        # Setup session with headline data
        chat_id = "group_test_group"
        news_session_manager.start_news_flow(chat_id, "test_user")
        news_session_manager.set_language(chat_id, "en")
        news_session_manager.set_cached_data(chat_id, {
            "headlines": [
                {"title": "Test headline with link", "url": "https://example.com/article1"},
                {"title": "Another headline", "url": "https://example.com/article2"},
            ]
        })

        # Simulate user selecting headline #1
        await news_agent._send_headline_detail(
            mock_event, 
            mock_line_bot_api,
            {"title": "Test headline with link", "url": "https://example.com/article1"},
            "en"
        )

        # Verify reply was sent with correct content
        assert mock_line_bot_api.reply_message.called
        reply_msg = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
        assert "Test headline with link" in reply_msg
        assert "https://example.com/article1" in reply_msg
        assert "Read more:" in reply_msg

        # Cleanup
        news_session_manager.end_news_flow(chat_id)

    @pytest.mark.asyncio
    async def test_headline_without_url_shows_warning(self, news_agent, mock_event, mock_line_bot_api):
        """Test that headlines without URLs show a warning message."""
        # Setup session
        chat_id = "group_test_group"
        news_session_manager.start_news_flow(chat_id, "test_user")
        news_session_manager.set_language(chat_id, "en")

        # Simulate headline without URL
        await news_agent._send_headline_detail(
            mock_event,
            mock_line_bot_api,
            {"title": "Headline without link", "url": ""},
            "en"
        )

        # Verify reply contains warning
        assert mock_line_bot_api.reply_message.called
        reply_msg = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
        assert "Headline without link" in reply_msg
        assert "Link unavailable" in reply_msg
        assert "⚠️" in reply_msg

        # Cleanup
        news_session_manager.end_news_flow(chat_id)

    @pytest.mark.asyncio
    async def test_headline_thai_without_url_shows_thai_warning(self, news_agent, mock_event, mock_line_bot_api):
        """Test Thai language warning for missing URLs."""
        chat_id = "group_test_group"
        news_session_manager.start_news_flow(chat_id, "test_user")
        news_session_manager.set_language(chat_id, "th")

        # Simulate headline without URL in Thai
        await news_agent._send_headline_detail(
            mock_event,
            mock_line_bot_api,
            {"title": "ข่าวทดสอบ", "url": ""},
            "th"
        )

        # Verify Thai warning
        assert mock_line_bot_api.reply_message.called
        reply_msg = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
        assert "ข่าวทดสอบ" in reply_msg
        assert "ลิงก์ไม่พร้อมใช้งาน" in reply_msg

        # Cleanup
        news_session_manager.end_news_flow(chat_id)


class TestSpecialNewsRSSFixes:
    """Test fixes for special news RSS fetching."""

    @pytest.mark.asyncio
    async def test_format_section_skips_unavailable_items(self, special_news_agent):
        """Test that _format_section skips unavailable items completely."""
        items = [
            {"title": "Real headline 1", "url": "https://example.com/1"},
            {"title": "(unavailable)", "url": ""},
            {"title": "Real headline 2", "url": "https://example.com/2"},
            {"title": "(unavailable)", "url": ""},
            {"title": "", "url": ""},
        ]

        result = special_news_agent._format_section("🧳 **Test Section**", items)
        
        # Should only show real headlines, skip unavailable
        assert "Real headline 1" in result
        assert "Real headline 2" in result
        assert "(unavailable)" not in result
        assert result.count("https://example.com/") == 2

    @pytest.mark.asyncio
    async def test_format_section_shows_warning_for_missing_urls(self, special_news_agent):
        """Test that items with missing URLs show warning emoji."""
        items = [
            {"title": "Headline without URL", "url": ""},
            {"title": "Headline with URL", "url": "https://example.com/1"},
        ]

        result = special_news_agent._format_section("🧳 **Test Section**", items)
        
        # First item should have warning emoji, second should not
        lines = result.split("\n")
        # Find the headline lines
        headline_lines = [l for l in lines if l.strip() and not l.startswith("🧳") and not l.startswith("_")]
        
        # Should have both headlines
        assert len(headline_lines) == 2
        # First one has warning emoji
        assert "⚠️" in headline_lines[0]
        # Second one is a markdown link
        assert "[Headline with URL]" in headline_lines[1]

    @pytest.mark.asyncio
    async def test_format_section_all_unavailable_shows_message(self, special_news_agent):
        """Test message shown when all items are unavailable."""
        items = [
            {"title": "(unavailable)", "url": ""},
            {"title": "", "url": ""},
            {"title": "(unavailable)", "url": ""},
        ]

        result = special_news_agent._format_section("🧳 **Test Section**", items)
        
        # Should show "No news available" message
        assert "No news available at this moment" in result
        assert "(unavailable)" not in result

    @pytest.mark.asyncio
    async def test_increased_timeout_and_retries(self, special_news_service):
        """Test that RSS fetch uses increased timeout and retries."""
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <item>
                    <title>Test Article</title>
                    <link>https://example.com/test</link>
                </item>
            </channel>
        </rss>"""
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/rss+xml"}
        
        special_news_service._client.get = AsyncMock(return_value=mock_response)
        
        result = await special_news_service.fetch_rss_items("https://example.com/feed.xml")
        
        # Verify timeout is 15 seconds (increased from 10)
        call_kwargs = special_news_service._client.get.call_args[1]
        assert call_kwargs["timeout"] == 15.0
        
        # Verify we got the result
        assert len(result) == 1
        assert result[0]["title"] == "Test Article"

    @pytest.mark.asyncio
    async def test_rss_fetch_handles_empty_feed(self, special_news_service):
        """Test that empty RSS feeds are handled gracefully."""
        mock_response = MagicMock()
        mock_response.text = """<?xml version="1.0"?>
        <rss version="2.0">
            <channel>
                <title>Empty Feed</title>
            </channel>
        </rss>"""
        mock_response.status_code = 200
        mock_response.headers = {"content-type": "application/rss+xml"}
        
        special_news_service._client.get = AsyncMock(return_value=mock_response)
        
        result = await special_news_service.fetch_rss_items("https://example.com/empty.xml")
        
        # Should return empty list, not crash
        assert result == []

    @pytest.mark.asyncio
    async def test_error_message_includes_troubleshooting(self, special_news_agent, mock_event, mock_line_bot_api):
        """Test that error messages include troubleshooting hints."""
        # Mock all feeds to return empty
        special_news_agent._service.fetch_rss_items = AsyncMock(return_value=[])
        
        # Private chat event
        mock_event.source.group_id = None
        mock_event.source.room_id = None
        
        # Make user a friend
        mock_line_bot_api.get_profile = MagicMock(return_value={"userId": "test_user"})
        
        result = await special_news_agent.handle(mock_event, "/special news", mock_line_bot_api)
        
        # Verify error message was sent
        assert result is True
        assert mock_line_bot_api.reply_message.called
        
        reply_msg = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
        # Should include troubleshooting hints
        assert "Network connectivity" in reply_msg or "RSS feed" in reply_msg or "server downtime" in reply_msg


class TestRSSParsingLogging:
    """Test enhanced logging in RSS parsing."""

    @pytest.mark.asyncio
    async def test_news_data_service_logs_missing_urls(self, news_data_service):
        """Test that NewsDataService logs warnings for missing URLs."""
        with patch('feedparser.parse') as mock_parse:
            # Mock feedparser to return entries with missing URLs
            mock_feed = MagicMock()
            mock_entry1 = MagicMock()
            mock_entry1.title = "Article with URL"
            mock_entry1.link = "https://example.com/1"
            
            mock_entry2 = MagicMock()
            mock_entry2.title = "Article without URL"
            mock_entry2.link = ""
            
            mock_feed.entries = [mock_entry1, mock_entry2]
            mock_parse.return_value = mock_feed
            
            with patch('src.services.news_data_service.logger') as mock_logger:
                result = news_data_service._parse_rss_feed("https://example.com/feed")
                
                # Should log warning for missing URL
                warning_calls = [call for call in mock_logger.warning.call_args_list 
                               if "has no URL" in str(call)]
                assert len(warning_calls) > 0
                
                # Should still return both articles
                assert len(result) == 2
