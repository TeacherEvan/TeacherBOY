"""Integration test demonstrating the news feature fixes."""

import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from src.agents.news_agent import NewsAgent
from src.agents.special_news_agent import SpecialNewsAgent
from src.services.news_data_service import NewsDataService
from src.services.special_news_service import SpecialNewsService
from src.services.news_session_manager import news_session_manager


def test_headline_link_fix_demonstration():
    """
    Demonstrates the fix for Issue 1: Headlines with missing URLs now show a warning.
    
    Before: User selects headline #4, receives incomplete response with no link indication
    After: User sees clear warning message when link is unavailable
    """
    print("\n" + "="*80)
    print("DEMONSTRATION: Headline Link Fix (Issue 1)")
    print("="*80)
    
    # Setup
    mock_http_client = AsyncMock()
    news_service = NewsDataService(http_client=mock_http_client, news_api_key=None)
    agent = NewsAgent(news_data_service=news_service)
    
    mock_event = MagicMock()
    mock_event.reply_token = "test_token"
    mock_line_bot_api = MagicMock()
    
    # Test data simulating real Bangkok Post RSS feed that sometimes has missing URLs
    headlines = [
        {"title": "Bangkok expressway murder suspect arrested", "url": "https://bangkokpost.com/article1"},
        {"title": "Thai-Cambodian border talks open", "url": "https://bangkokpost.com/article2"},
        {"title": "Pet owner seeks justice after dog incident", "url": "https://bangkokpost.com/article3"},
        {"title": "Bhumjaithai confirms Anutin as sole PM candidate", "url": ""},  # Missing URL!
        {"title": "Thailand doubts Cambodia truce claim", "url": "https://bangkokpost.com/article5"},
    ]
    
    # Simulate user selecting headline #4 (which has no URL)
    selected_headline = headlines[3]
    
    print(f"\n📰 User selects headline #4:")
    print(f"   Title: {selected_headline['title']}")
    print(f"   URL: {selected_headline['url'] or '(empty)'}")
    
    # Test English response
    print(f"\n🔹 ENGLISH Response (Before fix: would show title only, no link indication)")
    asyncio.run(agent._send_headline_detail(
        mock_event, mock_line_bot_api, selected_headline, "en"
    ))
    en_response = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
    print(f"   After fix:\n   {en_response}")
    assert "Link unavailable" in en_response
    assert "⚠️" in en_response
    
    # Test Thai response
    print(f"\n🔹 THAI Response (Before fix: would show title only, no link indication)")
    asyncio.run(agent._send_headline_detail(
        mock_event, mock_line_bot_api, selected_headline, "th"
    ))
    th_response = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
    print(f"   After fix:\n   {th_response}")
    assert "ลิงก์ไม่พร้อมใช้งาน" in th_response
    assert "⚠️" in th_response
    
    print(f"\n✅ Fix validated: Missing URLs now show clear warning in both languages")
    print("="*80 + "\n")


def test_special_news_unavailable_fix_demonstration():
    """
    Demonstrates the fix for Issue 2: Tourism data showing "(unavailable)".
    
    Before: When RSS fetch fails, shows "1. (unavailable)" for all 5 items
    After: Skips unavailable items, shows only real data or helpful message
    """
    print("\n" + "="*80)
    print("DEMONSTRATION: Special News Unavailable Items Fix (Issue 2)")
    print("="*80)
    
    # Setup
    mock_http_client = AsyncMock()
    special_service = SpecialNewsService(http_client=mock_http_client)
    agent = SpecialNewsAgent(news_service=special_service)
    
    # Scenario 1: All items unavailable (RSS fetch failed)
    print("\n📋 Scenario 1: All tourism items unavailable (RSS fetch failed)")
    print("   Before fix: Would show '1. (unavailable)' x5")
    
    all_unavailable = [
        {"title": "(unavailable)", "url": ""},
        {"title": "(unavailable)", "url": ""},
        {"title": "(unavailable)", "url": ""},
        {"title": "(unavailable)", "url": ""},
        {"title": "(unavailable)", "url": ""},
    ]
    
    result = agent._format_section("🧳 **Thailand Tourism**", all_unavailable)
    print(f"   After fix:\n{result}\n")
    assert "(unavailable)" not in result
    assert "No news available at this moment" in result
    
    # Scenario 2: Partial data (some items failed, some succeeded)
    print("\n📋 Scenario 2: Partial data (some items loaded, some failed)")
    print("   Before fix: Would show mix of real headlines and '(unavailable)'")
    
    partial_data = [
        {"title": "Thailand welcomes record tourists in 2024", "url": "https://tat.com/article1"},
        {"title": "(unavailable)", "url": ""},
        {"title": "Phuket launches new eco-tourism initiative", "url": "https://tat.com/article2"},
        {"title": "(unavailable)", "url": ""},
        {"title": "", "url": ""},
    ]
    
    result = agent._format_section("🧳 **Thailand Tourism**", partial_data)
    print(f"   After fix:\n{result}\n")
    assert "(unavailable)" not in result
    assert "Thailand welcomes record tourists" in result
    assert "Phuket launches new eco-tourism" in result
    
    # Scenario 3: Item with missing URL
    print("\n📋 Scenario 3: Item with missing URL")
    print("   Before fix: Would show item with no indication of missing link")
    
    missing_url = [
        {"title": "New tourism campaign announced", "url": ""},
        {"title": "Beach restoration project complete", "url": "https://tat.com/article"},
    ]
    
    result = agent._format_section("🧳 **Thailand Tourism**", missing_url)
    print(f"   After fix:\n{result}\n")
    # First item should have warning emoji (no URL), second should be markdown link
    assert "⚠️" in result, "Missing URL should show warning emoji"
    assert "[Beach restoration project complete]" in result, "Item with URL should be markdown link"
    
    print(f"✅ Fix validated: Unavailable items handled gracefully with user-friendly messages")
    print("="*80 + "\n")


def test_improved_error_messages_demonstration():
    """
    Demonstrates improved error messages with troubleshooting hints.
    
    Before: Generic error "Unable to fetch news at this moment"
    After: Detailed error with specific troubleshooting steps
    """
    print("\n" + "="*80)
    print("DEMONSTRATION: Improved Error Messages")
    print("="*80)
    
    mock_http_client = AsyncMock()
    special_service = SpecialNewsService(http_client=mock_http_client)
    agent = SpecialNewsAgent(news_service=special_service)
    
    mock_event = MagicMock()
    mock_event.source = MagicMock()
    mock_event.source.user_id = "test_user"
    mock_event.source.group_id = None  # Private chat
    mock_event.source.room_id = None
    mock_event.reply_token = "test_token"
    
    mock_line_bot_api = MagicMock()
    mock_line_bot_api.get_profile = MagicMock(return_value={"userId": "test_user"})
    
    # Mock all feeds to fail
    agent._service.fetch_rss_items = AsyncMock(return_value=[])
    
    print("\n📋 When all RSS feeds fail:")
    print("   Before fix: Generic 'Unable to fetch news' message")
    
    asyncio.run(agent.handle(mock_event, "/special news", mock_line_bot_api))
    
    error_msg = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
    print(f"   After fix:\n{error_msg}\n")
    
    assert "Network connectivity" in error_msg or "RSS feed" in error_msg
    assert "⚠️" in error_msg
    assert "🔄" in error_msg
    
    print(f"✅ Fix validated: Error messages now include helpful troubleshooting information")
    print("="*80 + "\n")


if __name__ == "__main__":
    print("\n" + "🔧 NEWS FEATURE FIXES - INTEGRATION TEST DEMONSTRATION 🔧".center(80))
    test_headline_link_fix_demonstration()
    test_special_news_unavailable_fix_demonstration()
    test_improved_error_messages_demonstration()
    print("✅ ALL DEMONSTRATIONS COMPLETED SUCCESSFULLY\n")
