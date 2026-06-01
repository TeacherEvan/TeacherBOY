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

import logging
import re
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
from src.services.bot_identity_service import get_bot_identity_service
from src.services.calendar_session_manager import calendar_session_manager, CalendarState
from src.services.message_buffer_service import message_buffer_service
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
    "zeus calendar remove",
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
REMOVE_SELECTION_PATTERN = re.compile(r"^\d+(?:\s*,\s*\d+)*$")
REMOVE_DELETE_PATTERN = re.compile(r"^delete\s+[a-z0-9]{8,32}$")


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
        self._remove_flow._calendar_service = self._calendar_service
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
        text_lower = re.sub(r"\s+", " ", text.lower().strip())
        identity_service = get_bot_identity_service()

        for trigger in triggers:
            for variant in identity_service.expand_prefixed_trigger(trigger):
                if text_lower.startswith(variant):
                    return True
        return False

    def _has_identity_prefix(self, text: str) -> bool:
        prefix, _ = get_bot_identity_service().split_command_prefix(text)
        return prefix is not None

    def _is_cancel_command(self, text: str) -> bool:
        """Check if text is a cancel command."""
        normalized = (text or "").strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(normalized)
        text_lower = rest.lower().strip() if prefix else normalized.lower().strip()
        return text_lower in CANCEL_KEYWORDS

    def _is_remove_selection_command(self, text: str) -> bool:
        """Check whether text is a supported remove-selection command."""
        text_lower = text.lower().strip()
        return text_lower in {"all", "none", "done"} or bool(
            REMOVE_SELECTION_PATTERN.fullmatch(text_lower)
        )

    def _is_remove_confirmation_command(self, text: str) -> bool:
        """Check whether text is a supported remove-confirmation command."""
        text_lower = text.lower().strip()
        return self._is_cancel_command(text) or bool(REMOVE_DELETE_PATTERN.fullmatch(text_lower))

    def _is_remove_preview_followup(self, text: str) -> bool:
        """Accept legacy preview replies so the flow can reject them explicitly."""
        return text.lower().strip() in {
            "yes",
            "y",
            "no",
            "n",
            "confirm",
            "keep",
            "ใช่",
            "ไม่",
            "done",
        }

    def _is_remove_reselection_command(self, text: str) -> bool:
        """Commands that intentionally change the selected items from preview state."""
        text_lower = text.lower().strip()
        return text_lower in {"all", "none"} or bool(REMOVE_SELECTION_PATTERN.fullmatch(text_lower))

    def _looks_like_remove_selection_attempt(self, text: str) -> bool:
        """Catch mixed comma-separated selection attempts so they get explicit rejection."""
        normalized = text.lower().strip()
        if "," not in normalized:
            return False
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if not parts or not any(part.isdigit() for part in parts):
            return False
        keyword_starters = {"all", "none", "done", "cancel", "delete", "yes", "no", "confirm", "keep"}
        for part in parts:
            if part.isdigit():
                continue
            if re.fullmatch(r"[a-z0-9]+", part):
                return True
            leading_word = re.match(r"([a-z]+)", part)
            if leading_word and leading_word.group(1) in keyword_starters:
                return True
        return False

    def _is_remove_session_input(self, text: str, state: CalendarState) -> bool:
        """Limit active remove sessions to explicit remove commands only."""
        if state == CalendarState.AWAITING_REMOVAL_SELECTION:
            return (
                self._is_cancel_command(text)
                or self._is_remove_selection_command(text)
                or self._is_remove_confirmation_command(text)
                or self._looks_like_remove_selection_attempt(text)
            )

        if state == CalendarState.CONFIRMING_REMOVAL:
            return (
                self._is_remove_reselection_command(text)
                or self._is_remove_confirmation_command(text)
                or self._is_remove_preview_followup(text)
                or self._looks_like_remove_selection_attempt(text)
            )

        return False

    def _is_stale_remove_followup(self, text: str) -> bool:
        """Catch expired remove-flow follow-ups so they get an explicit expiry message."""
        text_lower = text.lower().strip()
        return (
            text_lower in {"all", "none", "done"}
            or bool(REMOVE_DELETE_PATTERN.fullmatch(text_lower))
            or ("," in text_lower and bool(REMOVE_SELECTION_PATTERN.fullmatch(text_lower)))
            or self._looks_like_remove_selection_attempt(text)
        )
    
    def _is_stale_scrape_followup(self, text: str) -> bool:
        """Catch explicit scrape follow-ups after expiry without hijacking ordinary chatter."""
        normalized = (text or "").strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(normalized)
        text_lower = rest.lower().strip() if prefix else normalized.lower().strip()
        return (
            text_lower in {"all", "none", "done", "cancel", "7", "3", "1", "7 days", "3 days", "1 day"}
            or bool(re.fullmatch(r"\d+(?:\s*,\s*\d+)*", text_lower))
        )

    def _is_scrape_session_input(self, text: str, state: CalendarState) -> bool:
        """Limit active scrape sessions to explicit scrape commands only."""
        if state == CalendarState.SCRAPE_SELECTING:
            return self.scrape_flow._is_explicit_scrape_selection_followup(text)

        if state == CalendarState.SCRAPE_REMINDER_DAYS:
            return self._is_cancel_command(text) or self.scrape_flow._is_explicit_scrape_reminder_followup(text)

        return False

    def _is_group_discrete_scrape_followup(
        self,
        chat_id: str,
        active_chat_id: str,
        session: Any,
        user_id: Optional[str],
    ) -> bool:
        """Keep discrete scrape follow-ups in DM once the flow has been handed off there."""
        if not session or session.state not in {
            CalendarState.SCRAPE_PROCESSING,
            CalendarState.SCRAPE_SELECTING,
            CalendarState.SCRAPE_REMINDER_DAYS,
        }:
            return False
        return (
            bool(user_id)
            and session.discrete_scrape_target == user_id
            and chat_id == active_chat_id
            and active_chat_id != f"user_{user_id}"
        )

    def _looks_like_bulk_dates(self, text: str) -> bool:
        """Detect if text contains bulk date input (should trigger scrape flow)."""
        if not text or len(text) < 50:
            return False
        
        text_lower = text.lower()
        
        # Check for image analysis output headers
        if "zeus observes" in text_lower or "ms. green observes" in text_lower or "━━━━━" in text:
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
        if self._has_identity_prefix(text) or text_lower in CANCEL_KEYWORDS:
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
        if self._has_identity_prefix(text):
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
        user_id = getattr(getattr(event, "source", None), "user_id", None)
        active_chat_id = calendar_session_manager.resolve_discrete_scrape_chat_id(chat_id, user_id)

        # Check for active calendar session
        session = calendar_session_manager.get_session(active_chat_id)
        if session and session.state != CalendarState.IDLE:
            if session.state in {
                CalendarState.AWAITING_REMOVAL_SELECTION,
                CalendarState.CONFIRMING_REMOVAL,
            }:
                return self._is_trigger(text, TRIGGERS_REMOVE) or self._is_remove_session_input(text, session.state)
            if session.state == CalendarState.SCRAPE_SELECTING:
                return self._is_scrape_session_input(text, session.state)
            if session.state == CalendarState.SCRAPE_REMINDER_DAYS:
                return self._is_scrape_session_input(text, session.state)
            return True

        if calendar_session_manager.had_recent_remove_flow(chat_id, user_id) and (
            REMOVE_DELETE_PATTERN.fullmatch(text_lower) or self._is_stale_remove_followup(text)
        ):
            return True

        if calendar_session_manager.had_recent_scrape_flow(chat_id, user_id) and self._is_stale_scrape_followup(text):
            return True

        # Check for explicit triggers (must START the message to avoid instructional text)
        all_triggers = TRIGGERS_VIEW + TRIGGERS_ADD + TRIGGERS_REMOVE + TRIGGERS_SCRAPE + TRIGGERS_DISCRETE_SCRAPE
        if self._is_trigger(text, all_triggers):
            return True

        # Check for inline add syntax ([alias] add [date] [title])
        prefix, rest = get_bot_identity_service().split_command_prefix(text)
        if prefix and rest.lower().startswith("add ") and len(text) > 10:
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
        active_chat_id = calendar_session_manager.resolve_discrete_scrape_chat_id(chat_id, user_id)
        session = calendar_session_manager.get_session(active_chat_id)
        if session and session.state == CalendarState.IDLE:
            session = None

        # Session ownership check (in groups, only session owner can interact)
        if session and not calendar_session_manager.is_session_owner(active_chat_id, user_id):
            logger.debug(
                f"📅 User {user_id} tried to interact with calendar session owned by {session.user_id}"
            )
            if session.state in {
                CalendarState.AWAITING_REMOVAL_SELECTION,
                CalendarState.CONFIRMING_REMOVAL,
            }:
                if self._is_trigger(text, TRIGGERS_REMOVE) or self._is_remove_session_input(text, session.state):
                    await self.remove_flow.send_message(
                        event,
                        line_bot_api,
                        "❌ Only the person who started this removal flow can change or confirm it.",
                    )
                    return True
                return False
            if session.state in {
                CalendarState.SCRAPE_SELECTING,
                CalendarState.SCRAPE_REMINDER_DAYS,
            }:
                if self._is_scrape_session_input(text, session.state):
                    await self.scrape_flow.send_message(
                        event,
                        line_bot_api,
                        "❌ Only the person who started this scrape flow can change or confirm it.",
                    )
                    return True
                return False
            return True

        if session and self._is_group_discrete_scrape_followup(chat_id, active_chat_id, session, user_id):
            if self._is_scrape_session_input(text, session.state):
                await self.scrape_flow.send_message(
                    event,
                    line_bot_api,
                    "❌ Continue this scrape in DM to keep it private.",
                )
                return True
            return False

        with tracer.start_as_current_span("calendar_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)

            try:
                # Store message in buffer (for potential scraping later)
                if user_id and text and not self._has_identity_prefix(text):
                    self._store_message_in_buffer(chat_id, user_id, text)

                # Let RemoveFlow own explicit cancel in remove states so it fully ends the session.
                if session and session.state in {
                    CalendarState.AWAITING_REMOVAL_SELECTION,
                    CalendarState.CONFIRMING_REMOVAL,
                } and self._is_cancel_command(text):
                    return await self.remove_flow.handle_removal_confirmation(
                        event, text, line_bot_api, active_chat_id, user_id
                    )

                # Check for cancel command
                if self._is_cancel_command(text) and (
                    not session
                    or session.state not in {
                        CalendarState.SCRAPE_PROCESSING,
                        CalendarState.SCRAPE_SELECTING,
                        CalendarState.SCRAPE_REMINDER_DAYS,
                    }
                ):
                    if calendar_session_manager.cancel_flow(active_chat_id):
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

                if not session and calendar_session_manager.had_recent_remove_flow(chat_id, user_id) and (
                    REMOVE_DELETE_PATTERN.fullmatch(text.lower().strip())
                    or self._is_stale_remove_followup(text)
                ):
                    await self.remove_flow.send_message(
                        event,
                        line_bot_api,
                        "❌ This remove flow is stale or expired. Start the remove flow again.",
                    )
                    return True
                
                if not session and calendar_session_manager.had_recent_scrape_flow(chat_id, user_id) and self._is_stale_scrape_followup(text):
                    await self.scrape_flow.send_message(
                        event,
                        line_bot_api,
                        "❌ This scrape flow is stale or expired. Start 'zeus scrape' again.",
                    )
                    return True

                # DISCRETE SCRAPE TRIGGER (friend-only, DM delivery)
                if self._is_trigger(text, TRIGGERS_DISCRETE_SCRAPE):
                    return await self._handle_discrete_scrape(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # SCRAPE TRIGGER
                if self._is_trigger(text, TRIGGERS_SCRAPE):
                    if getattr(getattr(event, "source", None), "type", None) in {"group", "room"}:
                        return await self._handle_discrete_scrape(
                            event, text, line_bot_api, chat_id, user_id
                        )
                    return await self.scrape_flow.handle_scrape_trigger(
                        event, text, line_bot_api, chat_id, user_id
                    )

                # INLINE ADD (zeus add [date] [title])
                prefix, rest = get_bot_identity_service().split_command_prefix(text)
                if prefix and rest.lower().startswith("add ") and len(text) > 10:
                    parsed = self._parse_inline_add(text)
                    if parsed:
                        return await self.inline_add_flow.handle_inline_add_trigger(
                            event, line_bot_api, chat_id, user_id, parsed
                        )
                    # If parsing failed, fallback to bulk detection
                    if self._looks_like_bulk_dates(text):
                        return await self.scrape_flow.handle_scrape_trigger(
                            event, text, line_bot_api, chat_id, user_id
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
                    if self._is_remove_confirmation_command(text):
                        return await self.remove_flow.handle_removal_confirmation(
                            event, text, line_bot_api, active_chat_id, user_id
                        )
                    if not self._is_remove_session_input(text, state):
                        return False
                    return await self.remove_flow.handle_removal_selection(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.CONFIRMING_REMOVAL:
                    if self._is_remove_reselection_command(text) or self._looks_like_remove_selection_attempt(text):
                        return await self.remove_flow.handle_removal_selection(
                            event, text, line_bot_api, active_chat_id, user_id
                        )
                    if not (
                        self._is_remove_confirmation_command(text)
                        or self._is_remove_preview_followup(text)
                    ):
                        return False
                    return await self.remove_flow.handle_removal_confirmation(
                        event, text, line_bot_api, active_chat_id, user_id
                    )

                # InlineAddFlow states
                if state == CalendarState.INLINE_ADD_REMINDER_DAYS:
                    return await self.inline_add_flow.handle_reminder_response(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.INLINE_ADD_CONFIRMING:
                    return await self.inline_add_flow.handle_confirmation(
                        event, text, line_bot_api, active_chat_id, user_id
                    )

                # AddFlow states
                if state == CalendarState.AWAITING_DATE:
                    return await self.add_flow.handle_date_input(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.AWAITING_TITLE:
                    return await self.add_flow.handle_title_input(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.AWAITING_DESCRIPTION:
                    return await self.add_flow.handle_description_input(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.AWAITING_REMINDER_DAYS:
                    return await self.add_flow.handle_reminder_days_input(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.CONFIRMING_ADD:
                    return await self.add_flow.handle_add_confirmation(
                        event, text, line_bot_api, active_chat_id, user_id
                    )

                # ScrapeFlow states
                if state == CalendarState.SCRAPE_SELECTING:
                    if not self.scrape_flow._is_explicit_scrape_selection_followup(text):
                        return False
                    return await self.scrape_flow.handle_scrape_review_response(
                        event, text, line_bot_api, active_chat_id, user_id
                    )
                
                if state == CalendarState.SCRAPE_REMINDER_DAYS:
                    if not (
                        self._is_cancel_command(text)
                        or self.scrape_flow._is_explicit_scrape_reminder_followup(text)
                    ):
                        return False
                    return await self.scrape_flow.handle_scrape_reminder_response(
                        event, text, line_bot_api, active_chat_id, user_id
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
        if not user_id:
            await self.add_flow.send_message(
                event, line_bot_api,
                "❌ Cannot identify user for discrete scrape."
            )
            return True

        is_friend = await self._is_friend(event, line_bot_api)
        if not is_friend:
            await self.add_flow.send_message(
                event,
                line_bot_api,
                "I can't continue in DM yet, so I'll continue here instead.",
            )
            return await self.scrape_flow.handle_scrape_trigger(
                event, text, line_bot_api, chat_id, user_id, discrete_mode=False
            )

        # Acknowledge request in group only after DM delivery is plausibly available.
        await self.add_flow.send_message(
            event, line_bot_api,
            "I'll try to continue in your DM. If that fails, I'll continue here."
        )

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
