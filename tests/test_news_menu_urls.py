"""Tests for news menu URL display inline."""

from unittest.mock import AsyncMock

import pytest

from src.agents.news_agent import NewsAgent
from src.services.news_data_service import NewsDataService


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


class TestNewsMenuURLDisplay:
    """Test that main menu displays URLs inline."""

    def test_format_menu_thai_shows_urls_inline(self, news_agent):
        """Test that Thai menu shows URLs inline below each headline."""
        weather = {"temperature": "30", "pm25": "45", "will_rain": False}
        headlines = [
            {"title": "ข่าวที่ 1", "url": "https://example.com/1"},
            {"title": "ข่าวที่ 2", "url": "https://example.com/2"},
            {"title": "ข่าวที่ 3", "url": ""},  # Missing URL
        ]
        holidays = [{"date": "Dec 25", "name_th": "วันคริสต์มาส", "name_en": "Christmas"}]
        indices = {"S&P 500": "4500", "DJIA": "35000", "FTSE 100": "7500"}
        crypto = {
            "btc": {"price_usd": "$42,000", "change_24h_percent": "+2.5%"},
            "eth": {"price_usd": "$2,200", "change_24h_percent": "+1.8%"},
            "usdt": {"price_usd": "$1.00", "change_24h_percent": "+0.01%"},
        }
        exchange = {"usd": "0.027", "jpy": "4.00", "zar": "0.49", "aud": "0.041", "gbp": "0.021", "rub": "2.40"}

        result = news_agent._format_menu_thai(weather, headlines, holidays, indices, crypto, exchange)

        # Verify headlines are numbered
        assert "1. ข่าวที่ 1" in result
        assert "2. ข่าวที่ 2" in result
        assert "3. ข่าวที่ 3" in result

        # Verify URLs are shown inline with link emoji
        assert "🔗 https://example.com/1" in result
        assert "🔗 https://example.com/2" in result

        # Verify missing URL shows warning in Thai
        assert "⚠️ ลิงก์ไม่พร้อมใช้งาน" in result

    def test_format_menu_english_shows_urls_inline(self, news_agent):
        """Test that English menu shows URLs inline below each headline."""
        weather = {"temperature": "30", "pm25": "45", "will_rain": True}
        headlines = [
            {"title": "Breaking news 1", "url": "https://example.com/breaking1"},
            {"title": "Breaking news 2", "url": "https://example.com/breaking2"},
            {"title": "Breaking news 3", "url": ""},  # Missing URL
        ]
        holidays = [{"date": "Dec 25", "name_th": "วันคริสต์มาส", "name_en": "Christmas"}]
        indices = {"S&P 500": "4500", "DJIA": "35000", "FTSE 100": "7500"}
        crypto = {
            "btc": {"price_usd": "$42,000", "change_24h_percent": "+2.5%"},
            "eth": {"price_usd": "$2,200", "change_24h_percent": "+1.8%"},
            "usdt": {"price_usd": "$1.00", "change_24h_percent": "+0.01%"},
        }
        exchange = {"usd": "0.027", "jpy": "4.00", "zar": "0.49", "aud": "0.041", "gbp": "0.021", "rub": "2.40"}

        result = news_agent._format_menu_english(weather, headlines, holidays, indices, crypto, exchange)

        # Verify headlines are numbered
        assert "1. Breaking news 1" in result
        assert "2. Breaking news 2" in result
        assert "3. Breaking news 3" in result

        # Verify URLs are shown inline with link emoji
        assert "🔗 https://example.com/breaking1" in result
        assert "🔗 https://example.com/breaking2" in result

        # Verify missing URL shows warning in English
        assert "⚠️ Link unavailable" in result

    def test_menu_with_all_headlines_having_urls(self, news_agent):
        """Test menu when all headlines have valid URLs."""
        weather = {"temperature": "28", "pm25": "35", "will_rain": None}
        headlines = [{"title": f"News {i}", "url": f"https://example.com/news{i}"} for i in range(1, 6)]
        holidays = []
        indices = {"S&P 500": "N/A", "DJIA": "N/A", "FTSE 100": "N/A"}
        crypto = {
            "btc": {"price_usd": "N/A", "change_24h_percent": "N/A"},
            "eth": {"price_usd": "N/A", "change_24h_percent": "N/A"},
            "usdt": {"price_usd": "N/A", "change_24h_percent": "N/A"},
        }
        exchange = {"usd": "N/A", "jpy": "N/A", "zar": "N/A", "aud": "N/A", "gbp": "N/A", "rub": "N/A"}

        result = news_agent._format_menu_english(weather, headlines, holidays, indices, crypto, exchange)

        # All 5 headlines should show with URLs, no warnings
        for i in range(1, 6):
            assert f"{i}. News {i}" in result
            assert f"🔗 https://example.com/news{i}" in result

        # No warnings should appear
        assert result.count("⚠️") == 0

    def test_menu_with_no_headlines_having_urls(self, news_agent):
        """Test menu when no headlines have URLs."""
        weather = {"temperature": "32", "pm25": "60", "will_rain": False}
        headlines = [
            {"title": "Headline 1", "url": ""},
            {"title": "Headline 2", "url": ""},
        ]
        holidays = []
        indices = {"S&P 500": "4500", "DJIA": "35000", "FTSE 100": "7500"}
        crypto = {
            "btc": {"price_usd": "$42,000", "change_24h_percent": "+2.5%"},
            "eth": {"price_usd": "$2,200", "change_24h_percent": "+1.8%"},
            "usdt": {"price_usd": "$1.00", "change_24h_percent": "+0.01%"},
        }
        exchange = {"usd": "0.027", "jpy": "4.00", "zar": "0.49", "aud": "0.041", "gbp": "0.021", "rub": "2.40"}

        result = news_agent._format_menu_english(weather, headlines, holidays, indices, crypto, exchange)

        # Both headlines should show warnings
        assert result.count("⚠️ Link unavailable") == 2
        assert "1. Headline 1" in result
        assert "2. Headline 2" in result
