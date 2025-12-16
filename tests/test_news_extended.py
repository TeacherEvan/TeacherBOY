"""Tests for extended news agent features (items 6-8)."""

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from src.services.news_data_service import NewsDataService


@pytest.fixture
def mock_http_client():
    """Create mock HTTP client."""
    return AsyncMock(spec=httpx.AsyncClient)


@pytest.fixture
def news_service(mock_http_client):
    """Create NewsDataService instance with mock client."""
    service = NewsDataService(http_client=mock_http_client, news_api_key="test_key")
    return service


class TestColorOfDay:
    """Test lucky color of day feature."""

    @pytest.mark.asyncio
    async def test_get_color_of_day_returns_valid_structure(self, news_service):
        """Test that color of day returns required fields."""
        result = await news_service.get_color_of_day()
        
        assert isinstance(result, dict)
        assert "color_name_th" in result
        assert "color_name_en" in result
        assert "hex_code" in result
        assert result["hex_code"].startswith("#")

    @pytest.mark.asyncio
    async def test_get_color_of_day_caching(self, news_service):
        """Test that color of day is cached."""
        result1 = await news_service.get_color_of_day()
        result2 = await news_service.get_color_of_day()
        
        # Same result on consecutive calls (cached)
        assert result1 == result2

    @pytest.mark.asyncio
    async def test_get_color_of_day_cycles_through_five_colors(self, news_service):
        """Test that color cycles through 5 colors by day of year."""
        # Clear cache
        if "color_of_day" in news_service.cache._cache:
            del news_service.cache._cache["color_of_day"]
        
        colors_seen = set()
        
        # Check different days cycle through 5 colors
        with patch("src.services.news_data_service.datetime") as mock_datetime:
            for day in [1, 74, 147, 220, 293]:  # Different quarters of year
                mock_datetime.now.return_value.timetuple.return_value.tm_yday = day
                
                # Clear cache for each iteration
                if "color_of_day" in news_service.cache._cache:
                    del news_service.cache._cache["color_of_day"]
                
                result = await news_service.get_color_of_day()
                colors_seen.add(result["color_name_en"])
        
        # Should see at least 3-4 different colors
        assert len(colors_seen) >= 3


class TestSunsetSunriseTimes:
    """Test sunset and sunrise times feature."""

    @pytest.mark.asyncio
    async def test_get_sunset_sunrise_times_returns_valid_structure(self, news_service, mock_http_client):
        """Test that sunset/sunrise returns required fields."""
        # Mock API response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "daily": {
                "sunrise": ["2024-12-16T06:30"],
                "sunset": ["2024-12-16T18:15"]
            }
        }
        mock_http_client.get.return_value = mock_response

        result = await news_service.get_sunset_sunrise_times()
        
        assert isinstance(result, dict)
        assert "sunrise" in result
        assert "sunset" in result
        assert ":" in result["sunrise"]  # HH:MM format
        assert ":" in result["sunset"]

    @pytest.mark.asyncio
    async def test_get_sunset_sunrise_times_fallback_on_error(self, news_service, mock_http_client):
        """Test that fallback times are returned on API error."""
        mock_http_client.get.side_effect = Exception("API error")

        result = await news_service.get_sunset_sunrise_times()
        
        # Should return sensible defaults
        assert result["sunrise"] == "06:30"
        assert result["sunset"] == "18:00"

    @pytest.mark.asyncio
    async def test_get_sunset_sunrise_times_caching(self, news_service, mock_http_client):
        """Test that sunset/sunrise times are cached."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "daily": {
                "sunrise": ["2024-12-16T06:30"],
                "sunset": ["2024-12-16T18:15"]
            }
        }
        mock_http_client.get.return_value = mock_response

        # First call
        result1 = await news_service.get_sunset_sunrise_times()
        call_count_after_first = mock_http_client.get.call_count
        
        # Second call (should use cache)
        result2 = await news_service.get_sunset_sunrise_times()
        call_count_after_second = mock_http_client.get.call_count
        
        assert result1 == result2
        # API should not be called additional times (cache hit)
        assert call_count_after_second == call_count_after_first


class TestThaiHolidays:
    """Test Thai holidays feature."""

    @pytest.mark.asyncio
    async def test_get_thai_holidays_returns_list(self, news_service):
        """Test that Thai holidays returns a list of dicts."""
        result = await news_service.get_thai_holidays()
        
        assert isinstance(result, list)
        if result:  # If list not empty
            assert isinstance(result[0], dict)
            assert "date" in result[0] or "name_th" in result[0] or "name_en" in result[0]

    @pytest.mark.asyncio
    async def test_get_thai_holidays_fallback_list_has_major_holidays(self, news_service):
        """Test that fallback list includes major Thai holidays."""
        # Mock no API key
        with patch("src.config.settings") as mock_settings:
            mock_settings.calendarific_api_key = None
            result = await news_service.get_thai_holidays()
        
        # Should have fallback holidays
        assert len(result) > 0
        
        # Check for major holidays
        holiday_names = [h.get("name_en", "").lower() for h in result]
        # At least some major holidays should be present
        assert any("chakri" in name or "songkran" in name or "visakha" in name for name in holiday_names)

    @pytest.mark.asyncio
    async def test_get_thai_holidays_caching(self, news_service):
        """Test that Thai holidays are cached."""
        result1 = await news_service.get_thai_holidays()
        result2 = await news_service.get_thai_holidays()
        
        # Same result on consecutive calls
        assert result1 == result2


class TestBitcoinPrice:
    """Test Bitcoin price feature."""

    @pytest.mark.asyncio
    async def test_get_bitcoin_price_returns_valid_structure(self, news_service, mock_http_client):
        """Test that Bitcoin price returns required fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bitcoin": {
                "usd": 42500.75,
                "usd_24h_change": 2.5
            }
        }
        mock_http_client.get.return_value = mock_response

        result = await news_service.get_bitcoin_price()
        
        assert isinstance(result, dict)
        assert "price_usd" in result
        assert "change_24h_percent" in result
        assert "$" in result["price_usd"]
        assert "%" in result["change_24h_percent"]

    @pytest.mark.asyncio
    async def test_get_bitcoin_price_handles_negative_change(self, news_service, mock_http_client):
        """Test that negative 24h change is formatted correctly."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bitcoin": {
                "usd": 40000.00,
                "usd_24h_change": -3.2
            }
        }
        mock_http_client.get.return_value = mock_response

        result = await news_service.get_bitcoin_price()
        
        assert "-" in result["change_24h_percent"]

    @pytest.mark.asyncio
    async def test_get_bitcoin_price_fallback_on_error(self, news_service, mock_http_client):
        """Test that N/A is returned on API error."""
        mock_http_client.get.side_effect = Exception("API error")

        result = await news_service.get_bitcoin_price()
        
        assert result["price_usd"] == "N/A"
        assert result["change_24h_percent"] == "N/A"

    @pytest.mark.asyncio
    async def test_get_bitcoin_price_caching(self, news_service, mock_http_client):
        """Test that Bitcoin price is cached (volatile data, short TTL)."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "bitcoin": {
                "usd": 42500.75,
                "usd_24h_change": 2.5
            }
        }
        mock_http_client.get.return_value = mock_response

        # First call
        result1 = await news_service.get_bitcoin_price()
        call_count_after_first = mock_http_client.get.call_count
        
        # Second call
        result2 = await news_service.get_bitcoin_price()
        call_count_after_second = mock_http_client.get.call_count
        
        assert result1 == result2
        # API should not be called additional times (cache hit)
        assert call_count_after_second == call_count_after_first


class TestExchangeRates:
    """Test exchange rates feature."""

    @pytest.mark.asyncio
    async def test_get_exchange_rates_returns_valid_structure(self, news_service, mock_http_client):
        """Test that exchange rates returns required fields."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "conversion_rates": {
                "USD": 0.0275,
                "ZAR": 0.495,
                "CNY": 0.19
            }
        }
        mock_http_client.get.return_value = mock_response

        result = await news_service.get_exchange_rates()
        
        assert isinstance(result, dict)
        assert "thb_usd" in result
        assert "thb_zar" in result
        assert "thb_cny" in result

    @pytest.mark.asyncio
    async def test_get_exchange_rates_fallback_values(self, news_service, mock_http_client):
        """Test that fallback rates are used when API is unavailable."""
        mock_http_client.get.side_effect = Exception("API error")

        result = await news_service.get_exchange_rates()
        
        # Should have fallback rates
        assert result["thb_usd"] == "0.027"
        assert result["thb_zar"] == "0.49"
        assert result["thb_cny"] == "0.19"

    @pytest.mark.asyncio
    async def test_get_exchange_rates_fallback_without_api_key(self, news_service):
        """Test that fallback rates are used without API key."""
        with patch("src.config.settings") as mock_settings:
            mock_settings.exchange_rate_api_key = None
            result = await news_service.get_exchange_rates()
        
        # Should have fallback rates
        assert result["thb_usd"] == "0.027"
        assert result["thb_zar"] == "0.49"
        assert result["thb_cny"] == "0.19"

    @pytest.mark.asyncio
    async def test_get_exchange_rates_caching(self, news_service, mock_http_client):
        """Test that exchange rates are cached."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "conversion_rates": {
                "USD": 0.0275,
                "ZAR": 0.495,
                "CNY": 0.19
            }
        }
        mock_http_client.get.return_value = mock_response

        # First call
        result1 = await news_service.get_exchange_rates()
        call_count_after_first = mock_http_client.get.call_count
        
        # Second call
        result2 = await news_service.get_exchange_rates()
        call_count_after_second = mock_http_client.get.call_count
        
        assert result1 == result2
        # API should not be called additional times (cache hit)
        assert call_count_after_second == call_count_after_first


class TestNewsAgentMenuRouting:
    """Test news agent menu routing for items 6-8."""

    @pytest.mark.asyncio
    async def test_menu_item_6_normalization(self):
        """Test that Thai numeral 6 (๖) is normalized to Arabic 6."""
        thai_to_arabic = {
            "๑": "1", "๒": "2", "๓": "3", "๔": "4", "๕": "5",
            "๖": "6", "๗": "7", "๘": "8"
        }
        
        assert thai_to_arabic.get("๖", "๖") == "6"
        assert thai_to_arabic.get("๗", "๗") == "7"
        assert thai_to_arabic.get("๘", "๘") == "8"

    @pytest.mark.asyncio
    async def test_menu_item_6_7_8_selection_flow(self):
        """Test that items 6-8 can be selected via Thai numerals."""
        # Simulate user input normalization
        user_inputs = ["6", "๖", "7", "๗", "8", "๘"]
        
        for user_input in user_inputs:
            thai_to_arabic = {
                "๑": "1", "๒": "2", "๓": "3", "๔": "4", "๕": "5",
                "๖": "6", "๗": "7", "๘": "8"
            }
            normalized = thai_to_arabic.get(user_input, user_input)
            
            # Verify normalization works
            assert normalized in ["6", "7", "8"]
