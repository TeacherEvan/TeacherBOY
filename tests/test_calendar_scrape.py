"""
Tests for Zeus Scrape and Zeus Add calendar features.

Tests cover:
1. MessageBufferService - message storage and retrieval
2. DateExtractionService - AI-powered date extraction with fallback
3. CalendarSessionManager - scrape and inline add flow states
4. CalendarAgent - trigger parsing and flow handling
"""

import pytest
from datetime import date, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

# Import services
from src.services.message_buffer_service import (
    MessageBufferService,
    BufferedMessage,
    ChatBuffer,
)
from src.services.date_extraction_service import (
    DateExtractionService,
    ExtractedEvent,
)
from src.services.calendar_session_manager import (
    CalendarSessionManager,
    CalendarSession,
    CalendarState,
)
from src.agents.calendar_agent import CalendarAgent

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


# ============================================================================
# MessageBufferService Tests
# ============================================================================

class TestMessageBufferService:
    """Tests for MessageBufferService."""
    
    def setup_method(self):
        """Create fresh service for each test."""
        self.service = MessageBufferService()
    
    def test_store_message(self):
        """Test storing a single message."""
        self.service.store_message("chat1", "Hello world", "user1")
        
        messages = self.service.get_recent_messages("chat1", limit=10)
        assert len(messages) == 1
        assert messages[0].text == "Hello world"
        assert messages[0].user_id == "user1"
    
    def test_store_multiple_messages(self):
        """Test storing multiple messages."""
        self.service.store_message("chat1", "Message 1", "user1")
        self.service.store_message("chat1", "Message 2", "user2")
        self.service.store_message("chat1", "Message 3", "user1")
        
        messages = self.service.get_recent_messages("chat1", limit=10)
        assert len(messages) == 3
        
        # Verify order (newest last)
        assert messages[0].text == "Message 1"
        assert messages[2].text == "Message 3"
    
    def test_buffer_limit(self):
        """Test that buffer respects maxlen (default: 200 for Hannibal Profile)."""
        for i in range(250):
            self.service.store_message("chat1", f"Message {i}", "user1")
        
        messages = self.service.get_recent_messages("chat1", limit=300)
        assert len(messages) == 200  # Buffer maxlen (increased for Hannibal Profile)
        
        # Verify oldest messages were dropped
        assert "Message 49" not in [m.text for m in messages]
        assert messages[-1].text == "Message 249"
    
    def test_separate_chats(self):
        """Test that different chats have separate buffers."""
        self.service.store_message("chat1", "Chat 1 message", "user1")
        self.service.store_message("chat2", "Chat 2 message", "user2")
        
        chat1_messages = self.service.get_recent_messages("chat1", limit=10)
        chat2_messages = self.service.get_recent_messages("chat2", limit=10)
        
        assert len(chat1_messages) == 1
        assert len(chat2_messages) == 1
        assert chat1_messages[0].text == "Chat 1 message"
        assert chat2_messages[0].text == "Chat 2 message"
    
    def test_get_message_texts(self):
        """Test get_message_texts convenience method."""
        self.service.store_message("chat1", "Hello", "user1")
        self.service.store_message("chat1", "World", "user1")
        
        texts = self.service.get_message_texts("chat1", limit=10)
        assert texts == ["Hello", "World"]
    
    def test_empty_chat(self):
        """Test getting messages from non-existent chat."""
        messages = self.service.get_recent_messages("nonexistent", limit=10)
        assert messages == []
        
        texts = self.service.get_message_texts("nonexistent", limit=10)
        assert texts == []
    
    def test_limit_parameter(self):
        """Test that limit parameter works."""
        for i in range(10):
            self.service.store_message("chat1", f"Message {i}", "user1")
        
        messages = self.service.get_recent_messages("chat1", limit=5)
        assert len(messages) == 5
        
        # Should get most recent 5
        assert messages[-1].text == "Message 9"


# ============================================================================
# DateExtractionService Tests
# ============================================================================

class TestDateExtractionService:
    """Tests for DateExtractionService."""
    
    def setup_method(self):
        """Create fresh service for each test."""
        self.service = DateExtractionService()
    
    def test_fallback_extraction_tomorrow(self):
        """Test fallback extraction of 'tomorrow'."""
        messages = ["Meeting tomorrow at 10am"]
        today = date.today()
        
        events = self.service._fallback_extraction(messages, today)
        
        assert len(events) == 1
        assert events[0].event_date == today + timedelta(days=1)
        # Title contains the content around 'tomorrow' (the regex captures context)
        assert "tomorrow" in events[0].source_text.lower()
        assert events[0].confidence == "low"
    
    def test_fallback_extraction_next_week(self):
        """Test fallback extraction of 'next week'."""
        messages = ["Project deadline next week"]
        today = date.today()
        
        events = self.service._fallback_extraction(messages, today)
        
        assert len(events) == 1
        assert events[0].event_date == today + timedelta(days=7)
        # Title is extracted from context, source_text has original
        assert "next week" in events[0].source_text.lower()
    
    def test_fallback_extraction_slash_date(self):
        """Test fallback extraction of DD/MM/YYYY format."""
        messages = ["Event on 15/06/2025"]
        today = date(2025, 1, 1)
        
        events = self.service._fallback_extraction(messages, today)
        
        assert len(events) == 1
        assert events[0].event_date == date(2025, 6, 15)
    
    def test_fallback_extraction_named_month(self):
        """Test fallback extraction of 'DD/MM/YYYY' format (named months handled by AI)."""
        # Note: Named months like "January 15" are handled by AI extraction, not fallback
        # The fallback only handles DD/MM/YYYY, YYYY-MM-DD, tomorrow, next week
        messages = ["Event on 15/01/2025"]
        today = date(2025, 1, 1)
        
        events = self.service._fallback_extraction(messages, today)
        
        assert len(events) == 1
        assert events[0].event_date.month == 1
        assert events[0].event_date.day == 15
    
    def test_fallback_extraction_past_date_skipped(self):
        """Test that past dates are skipped."""
        messages = ["Event on 01/01/2020"]
        today = date(2025, 1, 1)
        
        events = self.service._fallback_extraction(messages, today)
        
        assert len(events) == 0
    
    def test_fallback_extraction_no_dates(self):
        """Test extraction with no dates."""
        messages = ["Just a regular message", "Nothing to see here"]
        today = date.today()
        
        events = self.service._fallback_extraction(messages, today)
        
        assert len(events) == 0
    
    def test_deduplicate_events(self):
        """Test deduplication of similar events."""
        events = [
            ExtractedEvent(
                event_date=date(2025, 6, 15),
                title="Meeting",
                description="",
                source_text="Meeting on June 15",
                confidence="high"
            ),
            ExtractedEvent(
                event_date=date(2025, 6, 15),
                title="Meeting",  # Same date and title
                description="Different desc",
                source_text="Different source",
                confidence="low"
            ),
            ExtractedEvent(
                event_date=date(2025, 6, 16),  # Different date
                title="Meeting",
                description="",
                source_text="",
                confidence="medium"
            ),
        ]
        
        deduped = self.service._deduplicate_events(events)
        
        assert len(deduped) == 2  # Same date+title merged
        # Should keep higher confidence one
        assert deduped[0].confidence == "high"


# ============================================================================
# CalendarSessionManager Scrape Flow Tests
# ============================================================================

class TestCalendarSessionManagerScrape:
    """Tests for CalendarSessionManager scrape flow methods."""
    
    def setup_method(self):
        """Create fresh manager for each test."""
        self.manager = CalendarSessionManager()
    
    def test_start_scrape_flow(self):
        """Test starting a scrape flow."""
        messages = ["Message 1", "Message 2"]
        self.manager.start_scrape_flow("chat1", "user1", messages, is_friend=True)
        
        session = self.manager.get_session("chat1")
        assert session is not None
        assert session.state == CalendarState.SCRAPE_PROCESSING
        assert session.scraped_source_messages == messages
        assert session.pending_is_friend is True
    
    def test_set_scraped_events(self):
        """Test setting scraped events."""
        self.manager.start_scrape_flow("chat1", "user1", [], is_friend=False)
        
        events = [
            {"date": date(2025, 6, 15), "title": "Event 1"},
            {"date": date(2025, 6, 16), "title": "Event 2"},
        ]
        self.manager.set_scraped_events("chat1", events)
        
        session = self.manager.get_session("chat1")
        assert session.state == CalendarState.SCRAPE_REVIEWING
        assert len(session.scraped_events) == 2
        assert session.current_scrape_index == 0
    
    def test_get_current_scraped_event(self):
        """Test getting current scraped event."""
        self.manager.start_scrape_flow("chat1", "user1", [], is_friend=True)
        
        events = [
            {"date": date(2025, 6, 15), "title": "Event 1"},
            {"date": date(2025, 6, 16), "title": "Event 2"},
        ]
        self.manager.set_scraped_events("chat1", events)
        
        current = self.manager.get_current_scraped_event("chat1")
        assert current["title"] == "Event 1"
    
    def test_accept_scraped_event(self):
        """Test accepting a scraped event."""
        self.manager.start_scrape_flow("chat1", "user1", [], is_friend=True)
        events = [{"date": date(2025, 6, 15), "title": "Event 1"}]
        self.manager.set_scraped_events("chat1", events)
        
        self.manager.accept_scraped_event("chat1")
        
        session = self.manager.get_session("chat1")
        assert session.state == CalendarState.SCRAPE_REMINDER_DAYS
    
    def test_skip_scraped_event(self):
        """Test skipping a scraped event."""
        self.manager.start_scrape_flow("chat1", "user1", [], is_friend=True)
        events = [
            {"date": date(2025, 6, 15), "title": "Event 1"},
            {"date": date(2025, 6, 16), "title": "Event 2"},
        ]
        self.manager.set_scraped_events("chat1", events)
        
        has_more = self.manager.skip_scraped_event("chat1")
        
        assert has_more is True
        session = self.manager.get_session("chat1")
        assert session.current_scrape_index == 1
    
    def test_skip_last_scraped_event(self):
        """Test skipping the last scraped event."""
        self.manager.start_scrape_flow("chat1", "user1", [], is_friend=True)
        events = [{"date": date(2025, 6, 15), "title": "Event 1"}]
        self.manager.set_scraped_events("chat1", events)
        
        has_more = self.manager.skip_scraped_event("chat1")
        
        assert has_more is False
    
    def test_get_scrape_progress(self):
        """Test getting scrape progress."""
        self.manager.start_scrape_flow("chat1", "user1", [], is_friend=True)
        events = [
            {"date": date(2025, 6, 15), "title": "Event 1"},
            {"date": date(2025, 6, 16), "title": "Event 2"},
            {"date": date(2025, 6, 17), "title": "Event 3"},
        ]
        self.manager.set_scraped_events("chat1", events)
        
        current, total = self.manager.get_scrape_progress("chat1")
        assert current == 1  # 1-indexed
        assert total == 3
        
        self.manager.skip_scraped_event("chat1")
        current, total = self.manager.get_scrape_progress("chat1")
        assert current == 2


# ============================================================================
# CalendarSessionManager Inline Add Flow Tests
# ============================================================================

class TestCalendarSessionManagerInlineAdd:
    """Tests for CalendarSessionManager inline add flow methods."""
    
    def setup_method(self):
        """Create fresh manager for each test."""
        self.manager = CalendarSessionManager()
    
    def test_start_inline_add_flow(self):
        """Test starting inline add flow."""
        event_date = date(2025, 6, 15)
        self.manager.start_inline_add_flow(
            chat_id="chat1",
            user_id="user1",
            event_date=event_date,
            title="Test Event",
            description="Test description",
            is_friend=True
        )
        
        session = self.manager.get_session("chat1")
        assert session is not None
        assert session.state == CalendarState.INLINE_ADD_REMINDER_DAYS
        assert session.inline_event_data["date"] == event_date
        assert session.inline_event_data["title"] == "Test Event"
    
    def test_set_inline_reminder_days(self):
        """Test setting reminder days for inline add."""
        self.manager.start_inline_add_flow(
            chat_id="chat1",
            user_id="user1",
            event_date=date(2025, 6, 15),
            title="Test Event",
            description="",
            is_friend=False
        )
        
        event_data = self.manager.set_inline_reminder_days("chat1", [7, 3, 0])
        
        assert event_data is not None
        assert event_data["title"] == "Test Event"
        assert event_data["reminder_days"] == [7, 3, 0]
        
        session = self.manager.get_session("chat1")
        assert session.state == CalendarState.INLINE_ADD_CONFIRMING
    
    def test_get_inline_event_data(self):
        """Test getting inline event data."""
        self.manager.start_inline_add_flow(
            chat_id="chat1",
            user_id="user1",
            event_date=date(2025, 6, 15),
            title="Test Event",
            description="Test desc",
            is_friend=True
        )
        
        data = self.manager.get_inline_event_data("chat1")
        
        assert data is not None
        assert data["title"] == "Test Event"
        assert data["description"] == "Test desc"


# ============================================================================
# CalendarAgent Trigger Parsing Tests
# ============================================================================

class TestCalendarAgentTriggers:
    """Tests for CalendarAgent trigger parsing."""
    
    def setup_method(self):
        """Create agent for tests."""
        self.agent = CalendarAgent()
    
    def test_parse_inline_add_simple(self):
        """Test parsing simple 'zeus add tomorrow meeting' format."""
        result = self.agent._parse_inline_add("zeus add tomorrow team meeting")
        
        assert result is not None
        assert result["date"] == date.today() + timedelta(days=1)
        assert "team meeting" in result["title"].lower()
    
    def test_parse_inline_add_in_days(self):
        """Test parsing 'zeus add in 7 days event'."""
        result = self.agent._parse_inline_add("zeus add in 7 days project deadline")
        
        assert result is not None
        assert result["date"] == date.today() + timedelta(days=7)
    
    def test_parse_inline_add_next_week_not_supported(self):
        """Test that 'next week' without day number is not supported in inline add.
        
        Note: 'next week' is ambiguous for exact date inline adds.
        Use 'in 7 days' instead.
        """
        result = self.agent._parse_inline_add("zeus add next week project deadline")
        
        # 'next week' is not in the relative_dates dictionary
        # This is expected behavior - use "in 7 days" for a week from now
        assert result is None
    
    def test_parse_inline_add_named_date(self):
        """Test parsing 'zeus add January 15 conference'."""
        result = self.agent._parse_inline_add("zeus add January 15 annual conference")
        
        assert result is not None
        assert result["date"].month == 1
        assert result["date"].day == 15
    
    def test_parse_inline_add_slash_date(self):
        """Test parsing 'zeus add 15/06/2025 event'."""
        result = self.agent._parse_inline_add("zeus add 15/06/2025 summer party")
        
        assert result is not None
        assert result["date"] == date(2025, 6, 15)
        assert "summer party" in result["title"].lower()
    
    def test_parse_inline_add_iso_date(self):
        """Test parsing 'zeus add 2025-06-15 event'."""
        result = self.agent._parse_inline_add("zeus add 2025-06-15 concert")
        
        assert result is not None
        assert result["date"] == date(2025, 6, 15)
    
    def test_parse_inline_add_no_date(self):
        """Test that invalid format returns None."""
        result = self.agent._parse_inline_add("zeus add meeting")
        
        assert result is None
    
    def test_parse_inline_add_not_zeus_add(self):
        """Test that non-zeus-add commands return None."""
        result = self.agent._parse_inline_add("zeus calendar")
        assert result is None
        
        result = self.agent._parse_inline_add("hello world")
        assert result is None
    
    def test_scrape_trigger_detection(self):
        """Test that scrape triggers are detected."""
        from src.agents.calendar_agent import TRIGGERS_SCRAPE
        
        assert "zeus scrape" in TRIGGERS_SCRAPE
        assert "zeus scan" in TRIGGERS_SCRAPE


# ============================================================================
# Integration Tests (with mocks)
# ============================================================================

class TestCalendarAgentIntegration:
    """Integration tests for calendar agent flows."""
    
    @pytest.fixture
    def mock_event(self):
        """Create mock LINE event."""
        event = MagicMock()
        event.source.user_id = "test_user"
        event.source.group_id = "test_group"
        event.reply_token = "test_token"
        event.message.text = "zeus scrape"
        return event
    
    @pytest.fixture
    def mock_line_api(self):
        """Create mock LINE API."""
        return MagicMock()
    
    @pytest.mark.asyncio
    async def test_should_handle_scrape_trigger(self, mock_event):
        """Test that agent handles scrape trigger."""
        agent = CalendarAgent()
        
        result = await agent.should_handle(mock_event, "zeus scrape")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_should_handle_inline_add(self, mock_event):
        """Test that agent handles inline add trigger."""
        agent = CalendarAgent()
        
        result = await agent.should_handle(mock_event, "zeus add tomorrow test event")
        assert result is True
    
    @pytest.mark.asyncio
    async def test_should_not_handle_regular_text(self, mock_event):
        """Test that agent doesn't handle regular text."""
        agent = CalendarAgent()
        
        result = await agent.should_handle(mock_event, "hello world")
        assert result is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
