"""Tests for moderator direct news access feature."""

import pytest
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from src.agents.news_agent import NewsAgent
from src.services.news_data_service import NewsDataService
from src.services.news_session_manager import news_session_manager
from src.services.privilege_service import privilege_service
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi
from linebot.v3.messaging.exceptions import ApiException


@pytest.fixture
def mock_http_client():
    """Create a mock HTTP client."""
    return AsyncMock()


@pytest.fixture
def news_data_service(mock_http_client):
    """Create NewsDataService instance."""
    return NewsDataService(http_client=mock_http_client, news_api_key=None)


@pytest.fixture
def mock_settings_with_moderators():
    """Mock settings with moderator configuration."""
    # Reset privilege_service cache before each test
    privilege_service._reset_for_testing()
    
    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["U_admin_123"]
        mock_settings.get_moderator_user_ids.return_value = ["U_mod_456", "U_mod_789"]
        yield mock_settings
    
    # Reset after test
    privilege_service._reset_for_testing()


@pytest.fixture
def news_agent_with_moderators(news_data_service, mock_settings_with_moderators):
    """Create NewsAgent instance with moderator configuration."""
    return NewsAgent(news_data_service=news_data_service)


@pytest.fixture
def mock_event():
    """Create a mock message event."""
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.user_id = "U_regular_user"
    event.source.group_id = None  # Private chat by default
    event.source.room_id = None
    event.reply_token = "test_reply_token"
    return event


@pytest.fixture
def mock_line_bot_api():
    """Create a mock LINE Bot API."""
    api = Mock(spec=MessagingApi)
    api.reply_message = Mock()
    api.get_profile = Mock(side_effect=Exception("Not a friend"))  # Default: not a friend
    return api


@pytest.fixture
def mock_news_data():
    """Standard mock news data for testing."""
    return {
        "weather": {"temperature": "30", "pm25": "50", "will_rain": False},
        "headlines": [{"title": "Test Headline", "url": "https://example.com/news1"}],
        "holidays": [{"date": "2024-12-31", "name_en": "New Year", "name_th": "ปีใหม่"}],
        "indices": {"S&P 500": "4500", "DJIA": "35000", "FTSE 100": "7500"},
        "crypto": {
            "btc": {"price_usd": "$50000", "change_24h_percent": "+2%"},
            "eth": {"price_usd": "$3000", "change_24h_percent": "+1%"},
            "usdt": {"price_usd": "$1.00", "change_24h_percent": "0%"}
        },
        "exchange": {
            "usd": "0.029", "jpy": "4.2", "zar": "0.5",
            "aud": "0.043", "gbp": "0.023", "rub": "2.7"
        }
    }


@pytest.fixture(autouse=True)
def cleanup_sessions():
    """Automatically cleanup news sessions after each test."""
    yield
    # Cleanup common test chat IDs
    for chat_id in ["group_G_test_group", "user_U_mod_456", "user_U_regular_user"]:
        news_session_manager.end_news_flow(chat_id)


class TestModeratorAuthentication:
    """Test moderator authentication and privilege checks."""

    def test_is_moderator_authorized(self, news_agent_with_moderators):
        """Test that authorized moderators are recognized."""
        assert privilege_service.is_moderator("U_mod_456") is True
        assert privilege_service.is_moderator("U_mod_789") is True

    def test_is_moderator_unauthorized(self, news_agent_with_moderators):
        """Test that non-moderators are not recognized."""
        assert privilege_service.is_moderator("U_regular_user") is False
        assert privilege_service.is_moderator("U_unknown") is False

    def test_is_privileged_user_admin(self, news_agent_with_moderators):
        """Test that admins are recognized as privileged users."""
        assert privilege_service.is_privileged("U_admin_123") is True

    def test_is_privileged_user_moderator(self, news_agent_with_moderators):
        """Test that moderators are recognized as privileged users."""
        assert privilege_service.is_privileged("U_mod_456") is True
        assert privilege_service.is_privileged("U_mod_789") is True

    def test_is_privileged_user_regular(self, news_agent_with_moderators):
        """Test that regular users are not recognized as privileged."""
        assert privilege_service.is_privileged("U_regular_user") is False


class TestModeratorPrivateChat:
    """Test moderator access in private chats."""

    @pytest.mark.asyncio
    async def test_moderator_gets_menu_in_private_chat(
        self, news_agent_with_moderators, mock_event, mock_line_bot_api, mock_news_data
    ):
        """Test that moderators get full news menu in private chat."""
        # Set as moderator and private chat
        mock_event.source.user_id = "U_mod_456"
        mock_event.source.group_id = None
        mock_event.source.room_id = None
        
        # Mock news data
        with patch.object(
            news_agent_with_moderators.news_service, "get_weather_data", new_callable=AsyncMock, return_value=mock_news_data["weather"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_news_headlines", new_callable=AsyncMock, return_value=mock_news_data["headlines"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_thai_holidays", new_callable=AsyncMock, return_value=mock_news_data["holidays"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_market_indices", new_callable=AsyncMock, return_value=mock_news_data["indices"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_crypto_prices", new_callable=AsyncMock, return_value=mock_news_data["crypto"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_exchange_rates", new_callable=AsyncMock, return_value=mock_news_data["exchange"]
        ) as mock_exchange:
            
            # Handle news trigger
            result = await news_agent_with_moderators.handle(
                mock_event, "news", mock_line_bot_api
            )
            
            assert result is True
            # Verify API was called to send menu (not translation)
            assert mock_line_bot_api.reply_message.called
            # Verify exchange data was fetched (indicates menu was shown)
            assert mock_exchange.called

    @pytest.mark.asyncio
    async def test_regular_user_gets_translation_in_private_chat(
        self, news_agent_with_moderators, mock_event, mock_line_bot_api
    ):
        """Test that regular users get translation only in private chat."""
        # Set as regular user and private chat
        mock_event.source.user_id = "U_regular_user"
        mock_event.source.group_id = None
        mock_event.source.room_id = None
        
        # Handle news trigger
        result = await news_agent_with_moderators.handle(
            mock_event, "news", mock_line_bot_api
        )
        
        assert result is True
        # Verify API was called
        assert mock_line_bot_api.reply_message.called
        # Check that the response is translation (news → ข่าว)
        call_args = mock_line_bot_api.reply_message.call_args
        messages = call_args[0][0].messages
        assert len(messages) == 1
        assert "ข่าว" in messages[0].text


class TestModeratorRateLimiting:
    """Test that moderators bypass rate limits."""

    @pytest.mark.asyncio
    async def test_moderator_bypasses_rate_limit(
        self, news_agent_with_moderators, mock_event, mock_line_bot_api, mock_news_data
    ):
        """Test that moderators bypass rate limits in groups."""
        # Set as moderator in group chat
        mock_event.source.user_id = "U_mod_456"
        mock_event.source.group_id = "G_test_group"
        mock_event.source.room_id = None
        
        # Mock as friend
        mock_line_bot_api.get_profile = Mock()
        
        # Mock news data
        with patch.object(
            news_agent_with_moderators.news_service, "get_weather_data", new_callable=AsyncMock, return_value=mock_news_data["weather"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_news_headlines", new_callable=AsyncMock, return_value=mock_news_data["headlines"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_thai_holidays", new_callable=AsyncMock, return_value=mock_news_data["holidays"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_market_indices", new_callable=AsyncMock, return_value=mock_news_data["indices"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_crypto_prices", new_callable=AsyncMock, return_value=mock_news_data["crypto"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_exchange_rates", new_callable=AsyncMock, return_value=mock_news_data["exchange"]
        ):
            
            # Request news multiple times (should not be rate limited)
            chat_id = "group_G_test_group"
            
            # First request
            result1 = await news_agent_with_moderators.handle(
                mock_event, "news", mock_line_bot_api
            )
            assert result1 is True
            
            # Clean session for second request
            news_session_manager.end_news_flow(chat_id)
            
            # Second request immediately (should not be rate limited)
            result2 = await news_agent_with_moderators.handle(
                mock_event, "news", mock_line_bot_api
            )
            assert result2 is True
            
            # Verify both requests went through successfully
            assert mock_line_bot_api.reply_message.call_count >= 2


class TestModeratorInGroups:
    """Test moderator access in group chats."""

    @pytest.mark.asyncio
    async def test_moderator_gets_menu_in_group(
        self, news_agent_with_moderators, mock_event, mock_line_bot_api, mock_news_data
    ):
        """Test that moderators get full news menu in groups."""
        # Set as moderator in group chat
        mock_event.source.user_id = "U_mod_456"
        mock_event.source.group_id = "G_test_group"
        mock_event.source.room_id = None
        
        # Mock news data
        with patch.object(
            news_agent_with_moderators.news_service, "get_weather_data", new_callable=AsyncMock, return_value=mock_news_data["weather"]
        ) as mock_weather, patch.object(
            news_agent_with_moderators.news_service, "get_news_headlines", new_callable=AsyncMock, return_value=mock_news_data["headlines"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_thai_holidays", new_callable=AsyncMock, return_value=mock_news_data["holidays"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_market_indices", new_callable=AsyncMock, return_value=mock_news_data["indices"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_crypto_prices", new_callable=AsyncMock, return_value=mock_news_data["crypto"]
        ), patch.object(
            news_agent_with_moderators.news_service, "get_exchange_rates", new_callable=AsyncMock, return_value=mock_news_data["exchange"]
        ), patch.object(
            news_agent_with_moderators, "_translate_headlines_to_thai", new_callable=AsyncMock, return_value=mock_news_data["headlines"]
        ):
            
            # Handle news trigger
            result = await news_agent_with_moderators.handle(
                mock_event, "news", mock_line_bot_api
            )
            
            assert result is True
            # Verify weather data was fetched (indicates menu was shown)
            assert mock_weather.called
            assert mock_line_bot_api.reply_message.called

    @pytest.mark.asyncio
    async def test_non_friend_gets_translation_in_group(
        self, news_agent_with_moderators, mock_event, mock_line_bot_api
    ):
        """Test that non-friends get translation only in groups."""
        # Set as regular user (non-friend) in group chat
        mock_event.source.user_id = "U_regular_user"
        mock_event.source.group_id = "G_test_group"
        mock_event.source.room_id = None
        
        # Mock as non-friend (get_profile raises exception)
        mock_line_bot_api.get_profile = Mock(side_effect=ApiException(status=400, reason="Not a friend"))
        
        # Handle news trigger
        result = await news_agent_with_moderators.handle(
            mock_event, "news", mock_line_bot_api
        )
        
        assert result is True
        # Verify API was called
        assert mock_line_bot_api.reply_message.called
        # Check that the response is translation (news → ข่าว)
        call_args = mock_line_bot_api.reply_message.call_args
        messages = call_args[0][0].messages
        assert len(messages) == 1
        assert "ข่าว" in messages[0].text
