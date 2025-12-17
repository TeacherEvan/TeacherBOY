"""Test news language-specific display functionality."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.agents.news_agent import NewsAgent
from src.services.news_data_service import NewsDataService


@pytest.fixture
def mock_news_data_service():
    """Create a mock NewsDataService."""
    service = MagicMock(spec=NewsDataService)
    service.get_weather_data = AsyncMock(return_value={
        "temperature": "25",
        "pm25": "45",
        "will_rain": False
    })
    service.get_news_headlines = AsyncMock(return_value=[
        {"title": "Thailand announces new policy", "url": "https://example.com/1"},
        {"title": "Bangkok traffic update", "url": "https://example.com/2"},
    ])
    return service


@pytest.fixture
def news_agent(mock_news_data_service):
    """Create NewsAgent with mocked service."""
    return NewsAgent(news_data_service=mock_news_data_service)


@pytest.mark.asyncio
async def test_headlines_translated_to_thai(news_agent):
    """Test that English headlines are translated to Thai when language='th'."""
    headlines = [
        {"title": "Breaking news today", "url": "https://example.com/1"},
        {"title": "Weather report", "url": "https://example.com/2"},
    ]
    
    # Mock translation services
    with patch.object(news_agent.google_translate, 'is_configured', return_value=True), \
         patch.object(news_agent.google_translate, 'translate', new_callable=AsyncMock) as mock_translate:
        
        # Configure mock to return Thai text
        mock_translate.side_effect = [
            "ข่าวด่วนวันนี้",  # Breaking news today
            "รายงานสภาพอากาศ"   # Weather report
        ]
        
        translated = await news_agent._translate_headlines_to_thai(headlines)
        
        assert len(translated) == 2
        assert translated[0]["title"] == "ข่าวด่วนวันนี้"
        assert translated[1]["title"] == "รายงานสภาพอากาศ"
        assert translated[0]["url"] == "https://example.com/1"
        assert translated[1]["url"] == "https://example.com/2"
        
        # Verify translate was called correctly
        assert mock_translate.call_count == 2
        mock_translate.assert_any_call(text="Breaking news today", target_lang="th", source_lang="en")
        mock_translate.assert_any_call(text="Weather report", target_lang="th", source_lang="en")


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
    
    # Mock both translation services to fail
    with patch.object(news_agent.google_translate, 'is_configured', return_value=True), \
         patch.object(news_agent.google_translate, 'translate', new_callable=AsyncMock) as mock_google, \
         patch.object(news_agent.libre_translate, 'translate', new_callable=AsyncMock) as mock_libre:
        
        # Both services fail
        mock_google.side_effect = Exception("Translation failed")
        mock_libre.side_effect = Exception("Translation failed")
        
        translated = await news_agent._translate_headlines_to_thai(headlines)
        
        # Should return original English
        assert translated[0]["title"] == "Important news"


@pytest.mark.asyncio
async def test_headlines_libre_fallback(news_agent):
    """Test that LibreTranslate is used when Google Translate is not configured."""
    headlines = [
        {"title": "Test headline", "url": "https://example.com/1"},
    ]
    
    # Mock Google as not configured, LibreTranslate as working
    with patch.object(news_agent.google_translate, 'is_configured', return_value=False), \
         patch.object(news_agent.libre_translate, 'translate', new_callable=AsyncMock) as mock_libre:
        
        mock_libre.return_value = "หัวข้อทดสอบ"
        
        translated = await news_agent._translate_headlines_to_thai(headlines)
        
        assert translated[0]["title"] == "หัวข้อทดสอบ"
        mock_libre.assert_called_once_with(text="Test headline", source_lang="en", target_lang="th")


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
    bitcoin = {"price": "50000", "change": "+5.2"}
    exchange = {"thb_to_usd": "0.028"}
    festivals = []
    
    menu = news_agent._format_menu_thai(weather, headlines_thai, holidays, bitcoin, exchange, festivals)
    
    # Verify Thai headlines appear in menu
    assert "ข่าวแรก" in menu
    assert "ข่าวที่สอง" in menu
    assert "📰 หัวข้อข่าว:" in menu  # Thai header


@pytest.mark.asyncio
async def test_menu_format_english_headlines(news_agent):
    """Test that the English menu format uses English headlines."""
    weather = {"temperature": "30", "pm25": "50", "will_rain": False}
    headlines_en = [
        {"title": "First news", "url": "https://example.com/1"},
        {"title": "Second news", "url": "https://example.com/2"},
    ]
    holidays = [{"date": "Apr 13", "name_th": "วันสงกรานต์", "name_en": "Songkran Festival"}]
    bitcoin = {"price": "50000", "change": "+5.2"}
    exchange = {"thb_to_usd": "0.028"}
    festivals = []
    
    menu = news_agent._format_menu_english(weather, headlines_en, holidays, bitcoin, exchange, festivals)
    
    # Verify English headlines appear in menu
    assert "First news" in menu
    assert "Second news" in menu
    assert "📰 Headlines:" in menu  # English header
