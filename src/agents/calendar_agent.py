"""
Calendar Agent - Modular architecture with lazy-loaded flow handlers.

This refactored version delegates all calendar functionality to independent
flow modules for better maintainability and performance.

Supports:
- Adding events with reminders (AddFlow, InlineAddFlow)
- Viewing user's events (ViewFlow)
- Removing events (RemoveFlow)
- Scraping dates from messages (ScrapeFlow)

Triggers:
- "zeus calendar" / "zeus my calendar" / "my events" -> View events
- "zeus add event" / "zeus remind me" -> Interactive add flow
- "zeus add [date] [title]" -> Inline add
- "zeus remove event" / "zeus delete event" -> Remove events
- "zeus scrape" / "zeus scan" -> Message scraping
"""

import asyncio
import logging
import re
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi

from .base_agent import BaseAgent
from .calendar import (
    get_view_flow,
    get_remove_flow,
    get_inline_add_flow,
    get_add_flow,
    get_scrape_flow,
    DateParser,
)
from src.services.calendar_session_manager import calendar_session_manager, CalendarState
from src.services.message_buffer_service import message_buffer_service
from src.config import settings
from src.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

# Trigger patterns
TRIGGERS_VIEW = [
    "zeus calendar",
    "zeus my calendar",
    "my events",
    "my reminders",
    "zeus events",
    "zeus reminders",
]

TRIGGERS_ADD = [
    "zeus add event",
    "zeus remind me",
    "zeus calendar add",
    "zeus new event",
    "add reminder",
    "add event",
]

TRIGGERS_REMOVE = [
    "zeus remove event",
    "zeus delete event",
    "zeus remove reminder",
    "zeus delete reminder",
    "remove event",
    "delete event",
]

TRIGGERS_SCRAPE = [
    "zeus scrape",
    "zeus scan",
    "zeus scan messages",
]

TRIGGERS_DISCRETE_SCRAPE = [
    "zeus scrape discretely",
    "zeus scrape discreetly",
    "zeus scan discretely",
    "zeus scan discreetly",
]

# Cancel keywords
CANCEL_KEYWORDS = ["cancel", "nevermind", "never mind", "ยกเลิก", "exit", "quit"]


class CalendarAgent(BaseAgent):
    """
    Calendar agent with modular flow architecture.
    
    This agent acts as a dispatcher, routing calendar operations to
    specialized flow handlers that are lazily instantiated on demand.
    """

    def __init__(self, calendar_service: Optional[Any] = None):
        """
        Initialize CalendarAgent with lazy-loaded flows.

        Args:
            calendar_service: CalendarService instance (injected from main.py)
        """
        super().__init__(
            name="CalendarAgent",
            description="Calendar events and reminders management (modular)",
        )
        self._calendar_service = calendar_service
        
        # Flow instances (lazy-loaded via getter properties)
        self._view_flow = None
        self._remove_flow = None
        self._inline_add_flow = None
        self._add_flow = None
        self._scrape_flow = None
        
        # Date parser utility
        self._date_parser = DateParser()

    def set_calendar_service(self, service: Any) -> None:
        """Set the calendar service (for delayed injection)."""
        self._calendar_service = service

    def get_priority(self) -> int:
        """
        Calendar agent priority.
        
        Priority 6: After admin (5), before profiler (7) and search (8).
        """
        return 6

    # =========================================================================
    # Lazy Flow Getters (Singleton Pattern)
    # =========================================================================

    @property
    def view_flow(self):
        """Lazy-load ViewFlow instance."""
        if self._view_flow is None:
            self._view_flow = get_view_flow(self._calendar_service)
        return self._view_flow

    @property
    def remove_flow(self):
        """Lazy-load RemoveFlow instance."""
        if self._remove_flow is None:
            self._remove_flow = get_remove_flow(self._calendar_service)
        return self._remove_flow

    @property
    def inline_add_flow(self):
        """Lazy-load InlineAddFlow instance."""
        if self._inline_add_flow is None:
            self._inline_add_flow = get_inline_add_flow(self._calendar_service)
        return self._inline_add_flow

    @property
    def add_flow(self):
        """Lazy-load AddFlow instance."""
        if self._add_flow is None:
            flow = get_add_flow()
            flow._calendar_service = self._calendar_service
            self._add_flow = flow
        return self._add_flow

    @property
    def scrape_flow(self):
        """Lazy-load ScrapeFlow instance."""
        if self._scrape_flow is None:
            flow = get_scrape_flow()
            flow._calendar_service = self._calendar_service
            self._scrape_flow = flow
        return self._scrape_flow

    # =========================================================================
    # Utility Methods
    # =========================================================================

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract normalized chat ID from event."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return f"group_{group_id}"
        if event.source and hasattr(event.source, "room_id"):
            room_id = getattr(event.source, "room_id", None)
            if room_id:
                return f"room_{room_id}"
        if event.source:
            user_id = getattr(event.source, "user_id", "unknown")
            return f"user_{user_id}"
        return "user_unknown"

    def _is_trigger(self, text: str, triggers: List[str]) -> bool:
        """
        Check if text matches any trigger.
        
        IMPORTANT: Triggers must START the message (after normalization)
        to prevent false matches from instructional text like:
        'you can say zeus add event' or 'just say zeus scrape'.
        
        Examples:
        - "zeus add event" -> MATCH
        - "add event tomorrow" -> MATCH  
        - "you can say zeus add event" -> NO MATCH (instructional)
        - "If you guys want to add event just say zeus add" -> NO MATCH
        """
        text_lower = text.lower().strip()
        
        # Check if ANY trigger starts the message
        return any(text_lower.startswith(trigger) for trigger in triggers)

    def _is_cancel_command(self, text: str) -> bool:
        """Check if text is a cancel command."""
        text_lower = text.lower().strip()
        return text_lower in CANCEL_KEYWORDS

    def _looks_like_bulk_dates(self, text: str) -> bool:
        """Detect if text contains bulk date input (should trigger scrape flow)."""
        if not text or len(text) < 50:
            return False
        
        text_lower = text.lower()
        
        # Check for Zeus OBSERVES pattern (image analysis output)
        if "zeus observes" in text_lower or "━━━━━" in text:
            return True
        
        # Check for multiple date patterns (numbered lists)
        numbered_items = len(re.findall(r'^\s*\d+\.', text, re.MULTILINE))
        if numbered_items >= 3:
            return True
        
        # Check for multiple date formats
        date_patterns = [
            r'\d{4}-\d{2}-\d{2}',  # ISO format
            r'\d{1,2}/\d{1,2}/\d{4}',  # Slash format
            r'(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}',  # Named month
        ]
        
        date_matches = sum(len(re.findall(pattern, text, re.IGNORECASE)) for pattern in date_patterns)
        if date_matches >= 3:
            return True
        
        # Check for multiple lines with dates
        lines_with_dates = sum(
            1 for line in text.split('\n')
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in date_patterns)
        )
        if lines_with_dates >= 3:
            return True
        
        return False

    # =========================================================================
    # Message Buffer (for scrape flow)
    # =========================================================================

    def _store_message_in_buffer(self, chat_id: str, user_id: str, text: str) -> None:
        """Store non-Zeus messages in buffer for potential scraping."""
        if not text:
            return
        
        text_lower = text.lower().strip()
        
        # Don't store Zeus commands or cancel keywords
        if text_lower.startswith("zeus") or text_lower in CANCEL_KEYWORDS:
            return
        
        # Store for scrape flow
        message_buffer_service.store_message(chat_id, user_id, text)

    # =========================================================================
    # Backward Compatibility Methods (for tests)
    # =========================================================================

    def _parse_inline_add(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse inline add syntax: "zeus add [date] [title]".
        
        Returns:
            Dict with 'date' (date object) and 'title' (str), or None
        """
        # Use DateParser but convert the result format
        result = self._date_parser.parse_inline_date(text)
        if result:
            date_obj, title = result
            return {
                "date": date_obj,
                "title": title
            }
        return None

    def _looks_like_event_message(self, text: str) -> bool:
        """Heuristic to detect event-like messages (for live bulk-add mode)."""
        t = (text or "").lower().strip()
        if not text:
            return False

        # Short messages unlikely to be event descriptions
        if len(t) < 10:
            return False

        # Zeus commands are not event messages
        if t.startswith("zeus"):
            return False

        # Check for date patterns
        date_patterns = [
            r'\b(tomorrow|today)\b',
            r'\b(next|this)\s+(week|month|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b',
            r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}',
            r'\b\d{1,2}/\d{1,2}(/\d{2,4})?\b',
            r'\b\d{4}-\d{2}-\d{2}\b',
        ]

        for pattern in date_patterns:
            if re.search(pattern, t, re.IGNORECASE):
                return True

        return False

    async def _is_friend(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi
    ) -> bool:
        """
        Check if user is a friend of the bot (for reminder delivery).
        
        Returns:
            bool: True if friend, False otherwise
        """
        # Delegate to add_flow's friendship check (they have caching logic)
        return await self.add_flow._check_is_friend(event, line_bot_api)

    # =========================================================================
    # Agent Interface Implementation
    # =========================================================================

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Check if this agent should handle the message.
        
        Handles:
        - Calendar triggers (view, add, remove, scrape)
        - Active calendar sessions
        - Calendar-related image events (delegated to ImageAnalyzerAgent)
        """
        if not text:
            return False

        text_lower = text.lower().strip()
        chat_id = self._get_chat_id(event)

        # Check for active calendar session
        session = calendar_session_manager.get_session(chat_id)
        if session and session.state != CalendarState.IDLE:
            return True

        # Check for explicit triggers
        if any(trigger in text_lower for trigger in 
               TRIGGERS_VIEW + TRIGGERS_ADD + TRIGGERS_REMOVE + TRIGGERS_SCRAPE + TRIGGERS_DISCRETE_SCRAPE):
            return True

        # Check for inline add syntax (zeus add [date] [title])
        if text_lower.startswith("zeus add ") and len(text) > 10:
            parsed = self._parse_inline_add(text)
            if parsed:
                return True

        return False

    async def handle(
        self, 
        event: MessageEvent, 
        text: str, 
        line_bot_api: MessagingApi
    ) -> bool:
        """
        Route calendar operations to appropriate flow handlers.
        
        This method acts as a dispatcher, delegating work to:
        - ViewFlow: For viewing events
        - RemoveFlow: For deleting events
        - InlineAddFlow: For quick "zeus add [date] [title]" syntax
        - AddFlow: For interactive multi-step add
        - ScrapeFlow: For message extraction
        """
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        session = calendar_session_manager.get_session(chat_id)

        # Session ownership check (in groups, only session owner can interact)
        if session and not calendar_session_manager.is_session_owner(chat_id, user_id):
            logger.debug(
                f"📅 User {user_id} tried to interact with calendar session owned by {session.user_id}"
            )
            return True

        with tracer.start_as_current_span("calendar_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)

            try:
                # Store message in buffer (for potential scraping later)
                if user_id and text and not text.lower().startswith("zeus"):
                    self._store_message_in_buffer(chat_id, user_id, text)

                # Check for cancel command
                if self._is_cancel_command(text):
                    if calendar_session_manager.cancel_flow(chat_id):
                        await self.add_flow.send_message(
                            event, line_bot_api,
                            "❌ Calendar operation cancelled.\n\nยกเลิกแล้วค่ะ"
                        )
                        return True
                    return False

                # ============================================================
                # Route based on trigger or session state
                # ============================================================

                # VIEW TRIGGER
                if self._is_trigger(text, TRIGGERS_VIEW):
                    return await self.view_flow.handle_view_events(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # REMOVE TRIGGER
                if self._is_trigger(text, TRIGGERS_REMOVE):
                    return await self.remove_flow.start_remove_flow(
                        event, line_bot_api, chat_id, user_id
                    )

                # DISCRETE SCRAPE TRIGGER (friend-only, DM delivery)
                if self._is_trigger(text, TRIGGERS_DISCRETE_SCRAPE):
                    return await self._handle_discrete_scrape(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # SCRAPE TRIGGER
                if self._is_trigger(text, TRIGGERS_SCRAPE):
                    return await self.scrape_flow.handle_scrape_trigger(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # INLINE ADD (zeus add [date] [title])
                text_lower = text.lower().strip()
                if text_lower.startswith("zeus add ") and len(text) > 10:
                    parsed = self._parse_inline_add(text)
                    if parsed:
                        return await self.inline_add_flow.handle_inline_add_trigger(
                            event, line_bot_api, chat_id, user_id, parsed
                        )
                    # If parsing failed, fallback to bulk detection
                    if self._looks_like_bulk_dates(text):
                        return await self.scrape_flow.handle_scrape_trigger(
                            event, line_bot_api, chat_id, user_id, text
                        )

                # INTERACTIVE ADD TRIGGER
                if self._is_trigger(text, TRIGGERS_ADD):
                    return await self.add_flow.start_add_flow(
                        event, line_bot_api, chat_id, user_id
                    )

                # ============================================================
                # Handle active session states
                # ============================================================

                if not session:
                    return False

                state = session.state

                # ViewFlow states (none - view is stateless)

                # RemoveFlow states
                if state == CalendarState.AWAITING_REMOVAL_SELECTION:
                    return await self.remove_flow.handle_removal_selection(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.CONFIRMING_REMOVAL:
                    return await self.remove_flow.handle_removal_confirmation(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # InlineAddFlow states
                if state == CalendarState.INLINE_ADD_REMINDER_DAYS:
                    return await self.inline_add_flow.handle_reminder_response(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.INLINE_ADD_CONFIRMING:
                    return await self.inline_add_flow.handle_confirmation(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # AddFlow states
                if state == CalendarState.AWAITING_DATE:
                    return await self.add_flow.handle_date_input(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.AWAITING_TITLE:
                    return await self.add_flow.handle_title_input(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.AWAITING_DESCRIPTION:
                    return await self.add_flow.handle_description_input(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.AWAITING_REMINDER_DAYS:
                    return await self.add_flow.handle_reminder_days_input(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.CONFIRMING_ADD:
                    return await self.add_flow.handle_add_confirmation(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # ScrapeFlow states
                if state == CalendarState.SCRAPE_REVIEWING:
                    return await self.scrape_flow.handle_scrape_review_response(
                        event, text, line_bot_api, chat_id, user_id
                    )
                
                if state == CalendarState.SCRAPE_REMINDER_DAYS:
                    return await self.scrape_flow.handle_scrape_reminder_response(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # Unknown state
                logger.warning(f"⚠️ Unknown calendar state: {state}")
                return False

            except Exception as e:
                logger.exception(f"❌ Error in calendar handler: {e}")
                await self.add_flow.send_message(
                    event, line_bot_api,
                    "❌ Something went wrong. Please try again.\n\n"
                    "เกิดข้อผิดพลาด กรุณาลองใหม่"
                )
                calendar_session_manager.cancel_flow(chat_id)
                return True

    # =========================================================================
    # Discrete Scrape (Privacy-Preserving Group Scraping)
    # =========================================================================

    async def _handle_discrete_scrape(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """
        Handle discrete scrape request.
        
        Scrapes dates from group messages but sends all confirmations
        and reminders via DM to the requester (if they're a friend).
        
        Args:
            event: LINE message event
            text: Message text
            line_bot_api: LINE Messaging API client
            chat_id: Chat ID (group/room)
            user_id: User ID of requester
            
        Returns:
            True if handled
        """
        from src.services.friend_check_service import friend_check_service
        import asyncio
        from linebot.v3.messaging import (
            PushMessageRequest,
            TextMessage,
        )

        if not user_id:
            await self._send_reply(
                event, line_bot_api,
                "❌ Cannot identify user for discrete scrape."
            )
            return True

        # Check if user is a friend
        is_friend = await friend_check_service.is_friend(user_id, line_bot_api)
        
        if not is_friend:
            await self._send_reply(
                event, line_bot_api,
                "Dear Mortal, I only do favors for friends! 🌩️\n\n"
                "Add me as a friend first to use discrete scraping.\n"
                "เพิ่มฉันเป็นเพื่อนก่อนเพื่อใช้การสแกนแบบลับ"
            )
            return True

        # Acknowledge request in group (briefly)
        await self._send_reply(
            event, line_bot_api,
            "🔍 Scanning messages discretely... Check your DM! 📨"
        )

        # Now run the normal scrape flow, but store user_id for DM delivery
        # We'll use the scrape flow but override the delivery target
        calendar_session_manager.set_discrete_scrape_target(chat_id, user_id)
        
        # Delegate to scrape flow (which will check for discrete mode)
        return await self.scrape_flow.handle_scrape_trigger(
            event, text, line_bot_api, chat_id, user_id, discrete_mode=True
        )

    # =========================================================================
    # Image-Triggered Calendar (ImageAnalyzerAgent Integration)
    # =========================================================================

    async def start_extraction_flow_from_image(
        self,
        chat_id: str,
        user_id: str,
        extracted_dates: List[Dict[str, Any]],
        is_friend: bool,
        event: Optional[MessageEvent] = None,
        line_bot_api: Optional[MessagingApi] = None,
    ) -> None:
        """
        Start processing dates extracted from an image.
        
        Called by ImageAnalyzerAgent when dates are detected.
        
        Args:
            chat_id: Chat ID where the image was sent
            user_id: User ID who sent the image
            extracted_dates: List of detected dates from image analysis
            is_friend: Whether the user is a friend of the bot
            event: Optional LINE message event (for sending prompts)
            line_bot_api: Optional LINE API client (for sending prompts)
        """
        # Start extraction flow via session manager
        calendar_session_manager.start_extraction_flow(
            chat_id, user_id, extracted_dates, is_friend
        )
        
        # If event and line_bot_api provided, prompt for first date
        if event and line_bot_api and extracted_dates:
            current_date = calendar_session_manager.get_current_extracted_date(chat_id)
            if current_date:
                # Delegate to scrape_flow for prompting (uses same review UI)
                await self.scrape_flow.prompt_scraped_event(
                    event, line_bot_api, current_date,
                    current=1, total=len(extracted_dates),
                    show_add_all=True
                )
