"""Test suite for news menu formatting optimizations.

Tests validate:
- PM2.5 health context indicators
- Clean percentage formatting (no redundant parentheses)
- Timestamp display in menus
- N/A context for unavailable data
"""

import pytest
from unittest.mock import AsyncMock
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


class TestPM25Context:
    """Test PM2.5 health context formatting."""

    def test_pm25_good_english(self, news_agent):
        """Test PM2.5 good level in English."""
        result = news_agent._get_pm25_context(25.1, "en")
        assert "µg/m³" in result
        assert "Good 🟢" in result
        assert "25.1" in result

    def test_pm25_good_thai(self, news_agent):
        """Test PM2.5 good level in Thai."""
        result = news_agent._get_pm25_context(45, "th")
        assert "µg/m³" in result
        assert "ดี 🟢" in result

    def test_pm25_moderate_english(self, news_agent):
        """Test PM2.5 moderate level in English."""
        result = news_agent._get_pm25_context(75, "en")
        assert "µg/m³" in result
        assert "Moderate 🟡" in result

    def test_pm25_moderate_thai(self, news_agent):
        """Test PM2.5 moderate level in Thai."""
        result = news_agent._get_pm25_context(95, "th")
        assert "µg/m³" in result
        assert "ปานกลาง 🟡" in result

    def test_pm25_unhealthy_english(self, news_agent):
        """Test PM2.5 unhealthy level in English."""
        result = news_agent._get_pm25_context(150, "en")
        assert "µg/m³" in result
        assert "Unhealthy 🔴" in result

    def test_pm25_unhealthy_thai(self, news_agent):
        """Test PM2.5 unhealthy level in Thai."""
        result = news_agent._get_pm25_context(120, "th")
        assert "µg/m³" in result
        assert "ไม่ดี 🔴" in result

    def test_pm25_na(self, news_agent):
        """Test PM2.5 with N/A value."""
        result = news_agent._get_pm25_context("N/A", "en")
        assert result == "N/A"


class TestPercentageFormatting:
    """Test clean percentage formatting without redundant parentheses."""

    def test_clean_negative_percentage(self, news_agent):
        """Test removing redundant parentheses from negative percentages."""
        result = news_agent._clean_percentage("(-0.05%)")
        assert result == "-0.05%"
        assert not result.startswith("(")
        assert not result.endswith(")")

    def test_clean_positive_percentage(self, news_agent):
        """Test removing redundant parentheses from positive percentages."""
        result = news_agent._clean_percentage("(+1.23%)")
        assert result == "+1.23%"

    def test_clean_na_percentage(self, news_agent):
        """Test N/A percentage stays unchanged."""
        result = news_agent._clean_percentage("N/A")
        assert result == "N/A"

    def test_clean_empty_percentage(self, news_agent):
        """Test empty string stays unchanged."""
        result = news_agent._clean_percentage("")
        assert result == ""

    def test_clean_already_clean_percentage(self, news_agent):
        """Test already clean percentage stays unchanged."""
        result = news_agent._clean_percentage("-2.50%")
        assert result == "-2.50%"


class TestTimestampFormatting:
    """Test timestamp formatting."""

    def test_timestamp_format(self, news_agent):
        """Test timestamp returns HH:MM format."""
        result = news_agent._format_timestamp()
        assert ":" in result
        parts = result.split(":")
        assert len(parts) == 2
        assert parts[0].isdigit() and parts[1].isdigit()
        assert 0 <= int(parts[0]) < 24
        assert 0 <= int(parts[1]) < 60


class TestMenuFormatting:
    """Test complete menu formatting with optimizations."""

    def test_thai_menu_has_timestamp(self, news_agent):
        """Test Thai menu includes timestamp."""
        weather = {"temperature": 24.1, "pm25": 25.1, "will_rain": False}
        headlines = [{"title": "Test headline", "url": "http://test.com"}]
        holidays = [{"date": "Dec 31", "name_th": "วันขึ้นปีใหม่", "name_en": "New Year's Eve"}]
        indices = {"S&P 500": "6,774.76 (-0.05%)", "DJIA": "47,951.85 (-0.31%)", "FTSE 100": "N/A"}
        crypto = {
            "btc": {"price_usd": "$85,174.00", "change_24h_percent": "(-0.95%)"},
            "eth": {"price_usd": "$2,819.22", "change_24h_percent": "(-0.24%)"},
            "usdt": {"price_usd": "$1.00", "change_24h_percent": "(-0.03%)"}
        }
        exchange = {"usd": "0.032", "jpy": "4.952", "zar": "0.533", "aud": "0.048", "gbp": "0.024", "rub": "2.541"}

        result = news_agent._format_menu_thai(weather, headlines, holidays, indices, crypto, exchange)
        
        assert "อัปเดต:" in result
        assert "µg/m³" in result
        assert "ดี 🟢" in result
        # Check clean percentage formatting (no double negative)
        assert "-0.95%" in result
        assert "(-0.95%)" not in result

    def test_english_menu_has_timestamp(self, news_agent):
        """Test English menu includes timestamp."""
        weather = {"temperature": 24.1, "pm25": 25.1, "will_rain": False}
        headlines = [{"title": "Test headline", "url": "http://test.com"}]
        holidays = [{"date": "Dec 31", "name_th": "วันขึ้นปีใหม่", "name_en": "New Year's Eve"}]
        indices = {"S&P 500": "6,774.76 (-0.05%)", "DJIA": "47,951.85 (-0.31%)", "FTSE 100": "N/A"}
        crypto = {
            "btc": {"price_usd": "$85,174.00", "change_24h_percent": "(-0.95%)"},
            "eth": {"price_usd": "$2,819.22", "change_24h_percent": "(-0.24%)"},
            "usdt": {"price_usd": "$1.00", "change_24h_percent": "(-0.03%)"}
        }
        exchange = {"usd": "0.032", "jpy": "4.952", "zar": "0.533", "aud": "0.048", "gbp": "0.024", "rub": "2.541"}

        result = news_agent._format_menu_english(weather, headlines, holidays, indices, crypto, exchange)
        
        assert "Updated:" in result
        assert "µg/m³" in result
        assert "Good 🟢" in result
        # Check clean percentage formatting
        assert "-0.95%" in result
        assert "(-0.95%)" not in result

    def test_menu_ftse_na_context(self, news_agent):
        """Test FTSE N/A displays with context."""
        weather = {"temperature": 24.1, "pm25": 25.1, "will_rain": False}
        headlines = []
        holidays = []
        indices = {"S&P 500": "6,774.76", "DJIA": "47,951.85", "FTSE 100": "N/A"}
        crypto = {"btc": {}, "eth": {}, "usdt": {}}
        exchange = {}

        result = news_agent._format_menu_english(weather, headlines, holidays, indices, crypto, exchange)
        
        assert "N/A (closed)" in result

    def test_menu_pm25_moderate(self, news_agent):
        """Test moderate PM2.5 level displays with yellow indicator."""
        weather = {"temperature": 28.0, "pm25": 85, "will_rain": False}
        headlines = []
        holidays = []
        indices = {}
        crypto = {"btc": {}, "eth": {}, "usdt": {}}
        exchange = {}

        result = news_agent._format_menu_english(weather, headlines, holidays, indices, crypto, exchange)
        
        assert "Moderate 🟡" in result
        assert "85 µg/m³" in result

    def test_menu_pm25_unhealthy(self, news_agent):
        """Test unhealthy PM2.5 level displays with red indicator."""
        weather = {"temperature": 30.0, "pm25": 125, "will_rain": True}
        headlines = []
        holidays = []
        indices = {}
        crypto = {"btc": {}, "eth": {}, "usdt": {}}
        exchange = {}

        result = news_agent._format_menu_thai(weather, headlines, holidays, indices, crypto, exchange)
        
        assert "ไม่ดี 🔴" in result
        assert "125 µg/m³" in result
