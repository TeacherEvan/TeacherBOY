"""Tests for LLM Agent live data detection and auto-search integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.llm_agent import _LIVE_DATA_REGEX, LLMAgent


class TestLiveDataDetection:
    """Test the live data pattern detection."""

    def test_location_queries_need_live_data(self):
        """Location-based queries should trigger live search."""
        queries = [
            "where is the best restaurant near me",
            "find restaurants nearby",
            "hotels in Bangkok",
            "cafes in Sukhumvit",
            "what's near Siam Paragon",
            "directions to Terminal 21",
            "how to get to Chatuchak market",
            "where can I find a pharmacy",
            "where can I get coffee",
        ]
        for query in queries:
            assert _LIVE_DATA_REGEX.search(query), f"Should detect: {query}"

    def test_business_queries_need_live_data(self):
        """Business-related queries should trigger live search."""
        queries = [
            "best restaurant for Thai food",
            "recommend a good hotel",
            "nice cafe with wifi",
            "where can I find a pharmacy",
            "hospitals near me",
            "good massage place",
            "best spa in Pattaya",
        ]
        for query in queries:
            assert _LIVE_DATA_REGEX.search(query), f"Should detect: {query}"

    def test_time_sensitive_queries_need_live_data(self):
        """Time-sensitive queries should trigger live search."""
        queries = [
            "is it open now",
            "what are the hours",
            "open today",
            "happening tonight",
            "events this weekend",
            "current price",
            "latest news",
        ]
        for query in queries:
            assert _LIVE_DATA_REGEX.search(query), f"Should detect: {query}"

    def test_price_availability_queries_need_live_data(self):
        """Price and availability queries should trigger live search."""
        queries = [
            "how much does it cost",
            "price of tickets",
            "is it available",
            "can I book a table",
            "make a reservation",
            "what's on the menu",
        ]
        for query in queries:
            assert _LIVE_DATA_REGEX.search(query), f"Should detect: {query}"

    def test_general_queries_dont_need_live_data(self):
        """General knowledge queries should NOT trigger live search."""
        queries = [
            "hello world",
            "what is the meaning of life",
            "explain quantum physics",
            "who is albert einstein",
            "translate this to Thai",
            "tell me a joke",
            "what is your name",
        ]
        for query in queries:
            assert not _LIVE_DATA_REGEX.search(query), f"Should NOT detect: {query}"

    def test_news_weather_queries_need_live_data(self):
        """News and weather queries should trigger live search."""
        queries = [
            "what's the weather today",
            "temperature in Bangkok",
            "will it rain tomorrow",
            "latest news about Thailand",
            "traffic conditions",
        ]
        for query in queries:
            assert _LIVE_DATA_REGEX.search(query), f"Should detect: {query}"


class TestLLMAgentLiveDataMethods:
    """Test LLM Agent live data methods."""

    @pytest.fixture
    def agent(self):
        """Create LLM agent instance."""
        return LLMAgent()

    def test_needs_live_data_method(self, agent):
        """Test _needs_live_data() method."""
        assert agent._needs_live_data("restaurants near me") is True
        assert agent._needs_live_data("hello world") is False
        assert agent._needs_live_data("") is False
        assert agent._needs_live_data(None) is False

    def test_format_search_context_empty(self, agent):
        """Test formatting with empty results."""
        result = agent._format_search_context([], "test query")
        assert result == ""

    def test_format_search_context_with_results(self, agent):
        """Test formatting with actual results."""
        results = [
            {"title": "Best Restaurant", "url": "https://example.com", "description": "Great food"},
            {"title": "Another Place", "url": "https://test.com", "description": "Nice atmosphere"},
        ]
        context = agent._format_search_context(results, "restaurants in Bangkok")

        assert "LIVE WEB SEARCH RESULTS" in context
        assert "restaurants in Bangkok" in context
        assert "Best Restaurant" in context
        assert "https://example.com" in context
        assert "Great food" in context
        assert "Another Place" in context

    @pytest.mark.asyncio
    async def test_auto_search_not_configured(self, agent):
        """Test auto-search when Brave Search is not configured."""
        with patch("src.agents.llm_agent.brave_search_service") as mock_service:
            mock_service.is_configured.return_value = False

            results = await agent._auto_search("test query")

            assert results == []

    @pytest.mark.asyncio
    async def test_auto_search_returns_results(self, agent):
        """Test auto-search returns results when configured."""
        mock_results = [
            {"title": "Result 1", "url": "https://r1.com", "description": "Desc 1"},
            {"title": "Result 2", "url": "https://r2.com", "description": "Desc 2"},
        ]

        with patch("src.agents.llm_agent.brave_search_service") as mock_service:
            mock_service.is_configured.return_value = True
            mock_service.search = AsyncMock(return_value=mock_results)

            results = await agent._auto_search("restaurants near me")

            assert results == mock_results
            mock_service.search.assert_called_once_with("restaurants near me", count=5)


class TestLLMAgentIntegration:
    """Integration tests for LLM agent with live data."""

    @pytest.fixture
    def mock_event(self):
        """Create a mock LINE event."""
        event = MagicMock()
        event.reply_token = "test_token"
        event.source = MagicMock()
        event.source.type = "user"
        event.source.user_id = "test_user_123"
        event.source.group_id = None
        event.source.room_id = None
        return event

    @pytest.fixture
    def mock_line_api(self):
        """Create a mock LINE API."""
        return MagicMock()

    @pytest.mark.asyncio
    async def test_query_triggers_live_search(self, mock_event, mock_line_api):
        """Test that business queries trigger auto-search before LLM."""
        agent = LLMAgent()

        with (
            patch.object(agent, "_auto_search", new_callable=AsyncMock) as mock_search,
            patch.object(agent, "github_service") as mock_github,
            patch.object(agent, "openrouter_service") as mock_openrouter,
            patch("src.agents.llm_agent.settings") as mock_settings,
        ):
            # Configure mocks
            mock_settings.llm_system_prompt = "Test prompt"
            mock_settings.llm_temperature = 0.7
            mock_settings.conversation_memory_enabled = False
            mock_settings.is_zeus_allowed_in_group.return_value = True
            mock_settings.get_llm_provider_priority.return_value = ["github"]

            mock_github.is_configured.return_value = True
            mock_github.chat_completion = AsyncMock(return_value="Here's what I found...")
            mock_openrouter.is_configured.return_value = False

            mock_search.return_value = [{"title": "Result", "url": "https://test.com", "description": "Test"}]

            # Process a query that needs live data
            await agent.handle(mock_event, "Ms. Green restaurants in Bangkok", mock_line_api)

            # Verify auto-search was called
            mock_search.assert_called_once()
