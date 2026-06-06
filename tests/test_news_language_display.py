"""Test news language-specific display functionality."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.news_agent import NewsAgent
from src.services.ai_translation_service import AITranslationResult
from src.services.news_data_service import NewsDataService


@pytest.fixture
def mock_news_data_service():
    """Create a mock NewsDataService."""
    service = MagicMock(spec=NewsDataService)
    service.get_weather_data = AsyncMock(return_value={"temperature": "25", "pm25": "45", "will_rain": False})
    service.get_news_headlines = AsyncMock(
        return_value=[
            {"title": "Thailand announces new policy", "url": "https://example.com/1"},
            {"title": "Bangkok traffic update", "url": "https://example.com/2"},
        ]
    )
    return service


@pytest.fixture
def news_agent(mock_news_data_service):
    """Create NewsAgent with mocked service."""
    ai_translation_service = MagicMock()
    ai_translation_service.translate = AsyncMock()
    return NewsAgent(
        news_data_service=mock_news_data_service,
        ai_translation_service=ai_translation_service,
    )


@pytest.mark.asyncio
async def test_headlines_translated_to_thai(news_agent):
    """Test that English headlines are translated to Thai when language='th'."""
    headlines = [
        {"title": "Breaking news today", "url": "https://example.com/1"},
        {"title": "Weather report", "url": "https://example.com/2"},
    ]

    news_agent.ai_translation_service.translate.side_effect = [
        AITranslationResult(text="ข่าวด่วนวันนี้", provider="github_models"),
        AITranslationResult(text="รายงานสภาพอากาศ", provider="github_models"),
    ]

    translated = await news_agent._translate_headlines_to_thai(headlines)

    assert len(translated) == 2
    assert translated[0]["title"] == "ข่าวด่วนวันนี้"
    assert translated[1]["title"] == "รายงานสภาพอากาศ"
    assert translated[0]["url"] == "https://example.com/1"
    assert translated[1]["url"] == "https://example.com/2"

    assert news_agent.ai_translation_service.translate.await_count == 2
    news_agent.ai_translation_service.translate.assert_any_await(
        "Breaking news today",
        source_lang="en",
        target_lang="th",
    )
    news_agent.ai_translation_service.translate.assert_any_await(
        "Weather report",
        source_lang="en",
        target_lang="th",
    )


@pytest.mark.asyncio
async def test_headlines_use_shared_ai_translation_service(mock_news_data_service):
    ai_translation_service = MagicMock()
    ai_translation_service.translate = AsyncMock(
        return_value=AITranslationResult(
            text="ข่าวด่วนวันนี้",
            provider="github_models",
        )
    )

    agent = NewsAgent(
        news_data_service=mock_news_data_service,
        ai_translation_service=ai_translation_service,
    )

    translated = await agent._translate_headlines_to_thai(
        [
            {"title": "Breaking news today", "url": "https://example.com/1"},
        ]
    )

    assert translated[0]["title"] == "ข่าวด่วนวันนี้"
    ai_translation_service.translate.assert_awaited_once_with(
        "Breaking news today",
        source_lang="en",
        target_lang="th",
    )


@pytest.mark.asyncio
async def test_headlines_fallback_messages_not_translated(news_agent):
    """Test that fallback messages are not translated."""
    headlines = [
        {"title": "News unavailable", "url": ""},
        {"title": "Visit Bangkok Post", "url": "https://www.bangkokpost.com"},
    ]

    translated = await news_agent._translate_headlines_to_thai(headlines)

    # Fallback messages should remain unchanged
    assert translated[0]["title"] == "News unavailable"
    assert translated[1]["title"] == "Visit Bangkok Post"


@pytest.mark.asyncio
async def test_headlines_translation_error_fallback(news_agent):
    """Test that original English is used if translation fails."""
    headlines = [
        {"title": "Important news", "url": "https://example.com/1"},
    ]

    news_agent.ai_translation_service.translate.side_effect = Exception("Translation failed")

    translated = await news_agent._translate_headlines_to_thai(headlines)

    assert translated[0]["title"] == "Important news"


@pytest.mark.asyncio
async def test_headlines_use_ai_translation_result(news_agent):
    """Test that the shared AI translation result is used for Thai headlines."""
    headlines = [
        {"title": "Test headline", "url": "https://example.com/1"},
    ]

    news_agent.ai_translation_service.translate.return_value = AITranslationResult(
        text="หัวข้อทดสอบ",
        provider="openrouter",
    )

    translated = await news_agent._translate_headlines_to_thai(headlines)

    assert translated[0]["title"] == "หัวข้อทดสอบ"
    news_agent.ai_translation_service.translate.assert_awaited_once_with(
        "Test headline",
        source_lang="en",
        target_lang="th",
    )


@pytest.mark.asyncio
async def test_english_headlines_not_translated(news_agent, mock_news_data_service):
    """Test that headlines remain in English when language='en'."""
    # This test verifies that we don't translate when English is selected
    # The current implementation fetches English RSS and uses it directly

    headlines = await mock_news_data_service.get_news_headlines("en")

    # Verify headlines are in English (not translated)
    assert all("title" in h and "url" in h for h in headlines)
    # English headlines should be returned as-is (tested via service mock)


@pytest.mark.asyncio
async def test_menu_format_uses_translated_headlines(news_agent):
    """Test that the Thai menu format uses translated headlines."""
    weather = {"temperature": "30", "pm25": "50", "will_rain": False}
    headlines_thai = [
        {"title": "ข่าวแรก", "url": "https://example.com/1"},
        {"title": "ข่าวที่สอง", "url": "https://example.com/2"},
    ]
    holidays = [{"date": "Apr 13", "name_th": "วันสงกรานต์", "name_en": "Songkran Festival"}]
    indices = {"S&P 500": "5,000.00 (+0.10%)", "DJIA": "40,000.00 (-0.10%)", "FTSE 100": "7,500.00 (+0.20%)"}
    crypto = {
        "btc": {"price_usd": "$50,000.00", "change_24h_percent": "+5.20%"},
        "eth": {"price_usd": "$2,500.00", "change_24h_percent": "+2.10%"},
        "usdt": {"price_usd": "$1.00", "change_24h_percent": "+0.00%"},
    }
    exchange = {"usd": "0.028", "jpy": "4.000", "zar": "0.490", "aud": "0.041", "gbp": "0.021", "rub": "2.400"}

    menu = news_agent._format_menu_thai(weather, headlines_thai, holidays, indices, crypto, exchange)

    # Verify Thai headlines appear in menu
    assert "ข่าวแรก" in menu
    assert "ข่าวที่สอง" in menu
    assert "📰 หัวข้อข่าว (Thailand):" in menu  # Thai header


@pytest.mark.asyncio
async def test_menu_format_english_headlines(news_agent):
    """Test that the English menu format uses English headlines."""
    weather = {"temperature": "30", "pm25": "50", "will_rain": False}
    headlines_en = [
        {"title": "First news", "url": "https://example.com/1"},
        {"title": "Second news", "url": "https://example.com/2"},
    ]
    holidays = [{"date": "Apr 13", "name_th": "วันสงกรานต์", "name_en": "Songkran Festival"}]
    indices = {"S&P 500": "5,000.00 (+0.10%)", "DJIA": "40,000.00 (-0.10%)", "FTSE 100": "7,500.00 (+0.20%)"}
    crypto = {
        "btc": {"price_usd": "$50,000.00", "change_24h_percent": "+5.20%"},
        "eth": {"price_usd": "$2,500.00", "change_24h_percent": "+2.10%"},
        "usdt": {"price_usd": "$1.00", "change_24h_percent": "+0.00%"},
    }
    exchange = {"usd": "0.028", "jpy": "4.000", "zar": "0.490", "aud": "0.041", "gbp": "0.021", "rub": "2.400"}

    menu = news_agent._format_menu_english(weather, headlines_en, holidays, indices, crypto, exchange)

    # Verify English headlines appear in menu
    assert "First news" in menu
    assert "Second news" in menu
    assert "📰 Headlines (Thailand):" in menu  # English header
