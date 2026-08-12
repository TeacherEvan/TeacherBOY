"""
Calendar Session Manager - Multi-step flow state machine for calendar operations.

Handles the conversational flow for:
1. Adding events (date -> title -> description -> reminder days)
2. Removing events (show list -> select numbers -> confirm)
3. Image date extraction (detected dates -> confirm add)

Similar pattern to image_analyzer_session_manager.py and news_session_manager.py.
"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class CalendarState(Enum):
    """States for the calendar session flow."""

    IDLE = "idle"
    AWAITING_DATE = "awaiting_date"
    AWAITING_TITLE = "awaiting_title"
    AWAITING_DESCRIPTION = "awaiting_description"
    AWAITING_REMINDER_DAYS = "awaiting_reminder_days"
    CONFIRMING_ADD = "confirming_add"
    AWAITING_REMOVAL_SELECTION = "awaiting_removal_selection"
    CONFIRMING_REMOVAL = "confirming_removal"
    # For image date extraction flow
    AWAITING_DATE_CONFIRMATION = "awaiting_date_confirmation"
    PROCESSING_EXTRACTED_DATES = "processing_extracted_dates"
    # For "Zeus Scrape" flow - scrapes dates from recent messages
    SCRAPE_PROCESSING = "scrape_processing"
    SCRAPE_REVIEWING = "scrape_reviewing"
    SCRAPE_SELECTING = "scrape_selecting"
    SCRAPE_REMINDER_DAYS = "scrape_reminder_days"

    # For "Zeus Add Event" smart mode selection
    ADD_MODE_SELECTION = "add_mode_selection"  # NEW: Choose between scan/listen/manual
    # For "Zeus Add Event" live bulk-add flow - scrapes dates from incoming messages
    LIVE_ADD_LISTENING = "live_add_listening"
    LIVE_ADD_REVIEWING = "live_add_reviewing"
    LIVE_ADD_REMINDER_DAYS = "live_add_reminder_days"
    # For "Zeus Add [date] [title]" inline flow
    INLINE_ADD_REMINDER_DAYS = "inline_add_reminder_days"
    INLINE_ADD_CONFIRMING = "inline_add_confirming"


@dataclass
class CalendarSession:
    """Session data for calendar operations."""

    user_id: str
    chat_id: str
    state: CalendarState = CalendarState.IDLE

    # Event being created
    pending_date: date | None = None
    pending_title: str | None = None
    pending_description: str | None = None
    pending_reminder_days: list[int] | None = None
    pending_is_friend: bool = False

    # For removal flow
    events_for_removal: list[dict[str, Any]] = field(default_factory=list)
    selected_event_ids: list[str] = field(default_factory=list)
    removal_revision: int = 0
    removal_flow_nonce: int = 0
    removal_confirmation_code: str = ""

    # For image date extraction
    extracted_dates: list[dict[str, Any]] = field(default_factory=list)  # [{date, title, description}]
    current_extraction_index: int = 0

    # For "Zeus Scrape" flow
    scraped_events: list[dict[str, Any]] = field(default_factory=list)  # Events extracted from messages
    current_scrape_index: int = 0  # Which scraped event is being processed
    selected_scraped_indices: list[int] = field(default_factory=list)
    scrape_selection_revision: int = 0
    scrape_preview_revision: int = 0
    scraped_source_messages: list[str] = field(default_factory=list)  # Source messages for context
    discrete_scrape_target: str | None = None  # User ID for discrete scrape DM delivery

    # For "Zeus Add Event" live bulk-add flow
    live_events: list[dict[str, Any]] = field(default_factory=list)  # Events scraped from incoming messages
    current_live_index: int = 0

    # For "Zeus Add [date] [title]" inline flow
    inline_event_data: dict[str, Any] | None = None  # Pre-parsed date/title from command

    # Timestamps
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)

    def update(self) -> None:
        """Update the timestamp."""
        self.updated_at = datetime.now()

    def is_expired(self, ttl_seconds: int = 120) -> bool:
        """Check if session has expired (2 minutes default)."""
        age = (datetime.now() - self.updated_at).total_seconds()
        return age > ttl_seconds

    def reset(self) -> None:
        """Reset session to idle state."""
        self.state = CalendarState.IDLE
        self.pending_date = None
        self.pending_title = None
        self.pending_description = None
        self.pending_reminder_days = None
        self.events_for_removal = []
        self.selected_event_ids = []
        self.removal_revision = 0
        self.removal_flow_nonce = 0
        self.removal_confirmation_code = ""
        self.extracted_dates = []
        self.current_extraction_index = 0
        # Reset scrape flow data
        self.scraped_events = []
        self.current_scrape_index = 0
        self.selected_scraped_indices = []
        self.scrape_selection_revision = 0
        self.scrape_preview_revision = 0
        self.scraped_source_messages = []
        self.discrete_scrape_target = None

        # Reset live bulk-add flow data
        self.live_events = []
        self.current_live_index = 0
        # Reset inline add data
        self.inline_event_data = None
        self.update()


class CalendarSessionManager:
    """Manages multi-step calendar sessions."""

    _REMOVE_NUMBER_SELECTION_PATTERN = re.compile(r"^\d+(?:\s*,\s*\d+)*$")
    _SCRAPE_NUMBER_SELECTION_PATTERN = re.compile(r"^\d+(?:\s*,\s*\d+)*$")

    def __init__(self):
        """Initialize calendar session manager."""
        self._sessions: dict[str, CalendarSession] = {}
        self._recently_expired_remove_flows: dict[str, dict[str, datetime]] = {}
        self._recently_expired_scrape_flows: dict[str, dict[str, datetime]] = {}
        self._session_ttl_seconds = 120  # 2 minutes per step
        self._cleanup_task: asyncio.Task | None = None
        self._cleanup_interval_seconds = 604800  # Run cleanup every 7 days (weekly)
        self._remove_flow_nonce_counter = 0

    def get_session(self, chat_id: str) -> CalendarSession | None:
        """
        Get session for a chat if it exists and hasn't expired.

        Args:
            chat_id: Chat identifier

        Returns:
            CalendarSession or None
        """
        if chat_id not in self._sessions:
            return None

        session = self._sessions[chat_id]

        if session.is_expired(self._session_ttl_seconds):
            logger.info(f"📅 Calendar session expired for chat {chat_id}")
            if session.state in {
                CalendarState.AWAITING_REMOVAL_SELECTION,
                CalendarState.CONFIRMING_REMOVAL,
            }:
                self._recently_expired_remove_flows.setdefault(chat_id, {})[session.user_id] = datetime.now()
            elif session.state in {
                CalendarState.SCRAPE_PROCESSING,
                CalendarState.SCRAPE_SELECTING,
                CalendarState.SCRAPE_REMINDER_DAYS,
            }:
                self._mark_recent_scrape_followup(session)
            del self._sessions[chat_id]
            return None

        return session

    def get_or_create_session(self, chat_id: str, user_id: str) -> CalendarSession:
        """
        Get existing session or create new one.

        Args:
            chat_id: Chat identifier
            user_id: User identifier

        Returns:
            CalendarSession
        """
        session = self.get_session(chat_id)
        if session:
            return session

        self._clear_recent_remove_marker(chat_id, user_id)

        session = CalendarSession(user_id=user_id, chat_id=chat_id)
        self._sessions[chat_id] = session
        logger.info(f"📅 Created calendar session for chat {chat_id}")
        return session

    def is_in_calendar_flow(self, chat_id: str) -> bool:
        """Check if chat is in an active calendar flow."""
        session = self.get_session(chat_id)
        return session is not None and session.state != CalendarState.IDLE

    def is_session_owner(self, chat_id: str, user_id: str | None) -> bool:
        """Check if user owns the session."""
        session = self.get_session(chat_id)
        if not session:
            return True  # No session, anyone can start one
        return session.user_id == user_id

    # =========================================================================
    # Add Event Flow
    # =========================================================================

    def start_add_flow(self, chat_id: str, user_id: str, is_friend: bool = False) -> CalendarSession:
        """
        Start the add event flow.

        Args:
            chat_id: Chat identifier
            user_id: User identifier
            is_friend: Whether user is LINE friend

        Returns:
            CalendarSession in AWAITING_DATE state
        """
        session = self.get_or_create_session(chat_id, user_id)
        session.reset()
        session.state = CalendarState.AWAITING_DATE
        session.pending_is_friend = is_friend
        session.update()

        logger.info(f"📅 Started add event flow for chat {chat_id}")
        return session

    def set_pending_date(self, chat_id: str, event_date: date) -> CalendarSession | None:
        """
        Set the pending event date and advance to title state.

        Args:
            chat_id: Chat identifier
            event_date: Event date

        Returns:
            Updated session or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.AWAITING_DATE:
            return None

        session.pending_date = event_date
        session.state = CalendarState.AWAITING_TITLE
        session.update()

        return session

    def set_pending_title(self, chat_id: str, title: str) -> CalendarSession | None:
        """
        Set the pending event title and advance to description state.

        Args:
            chat_id: Chat identifier
            title: Event title

        Returns:
            Updated session or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.AWAITING_TITLE:
            return None

        session.pending_title = title
        session.state = CalendarState.AWAITING_DESCRIPTION
        session.update()

        return session

    def set_pending_description(self, chat_id: str, description: str) -> CalendarSession | None:
        """
        Set the pending description and advance to reminder days state.

        Args:
            chat_id: Chat identifier
            description: Event description (can be empty)

        Returns:
            Updated session or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.AWAITING_DESCRIPTION:
            return None

        session.pending_description = description
        session.state = CalendarState.AWAITING_REMINDER_DAYS
        session.update()

        return session

    def set_pending_reminder_days(self, chat_id: str, reminder_days: list[int]) -> CalendarSession | None:
        """
        Set reminder days and advance to confirmation state.

        Args:
            chat_id: Chat identifier
            reminder_days: List of days before to remind

        Returns:
            Updated session or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.AWAITING_REMINDER_DAYS:
            return None

        # Always include day-of reminder
        if 0 not in reminder_days:
            reminder_days.append(0)

        session.pending_reminder_days = reminder_days
        session.state = CalendarState.CONFIRMING_ADD
        session.update()

        return session

    def get_pending_event_data(self, chat_id: str) -> dict[str, Any] | None:
        """
        Get all pending event data for creation.

        Returns:
            Dict with date, title, description, reminder_days, is_friend
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.CONFIRMING_ADD:
            return None

        return {
            "date": session.pending_date,
            "title": session.pending_title,
            "description": session.pending_description or "",
            "reminder_days": session.pending_reminder_days or [7, 3, 1, 0],
            "is_friend": session.pending_is_friend,
        }

    # =========================================================================
    # Remove Event Flow
    # =========================================================================

    def start_removal_flow(self, chat_id: str, user_id: str, events: list[dict[str, Any]]) -> CalendarSession:
        """
        Start the event removal flow.

        Args:
            chat_id: Chat identifier
            user_id: User identifier
            events: List of event dicts with 'event_id' and display info

        Returns:
            CalendarSession in AWAITING_REMOVAL_SELECTION state
        """
        session = self.get_or_create_session(chat_id, user_id)
        session.reset()
        session.state = CalendarState.AWAITING_REMOVAL_SELECTION
        session.events_for_removal = events
        session.removal_revision = 1
        session.removal_flow_nonce = self._next_remove_flow_nonce()
        session.removal_confirmation_code = ""
        self._clear_recent_remove_marker(chat_id, user_id)
        session.update()

        logger.info(f"📅 Started removal flow for chat {chat_id} with {len(events)} events")
        return session

    def set_removal_selection(self, chat_id: str, event_ids: list[str]) -> CalendarSession | None:
        """
        Set the events selected for removal.

        Args:
            chat_id: Chat identifier
            event_ids: List of event IDs to remove

        Returns:
            Updated session or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.AWAITING_REMOVAL_SELECTION:
            return None

        session.selected_event_ids = event_ids
        if session.removal_flow_nonce == 0:
            session.removal_flow_nonce = self._next_remove_flow_nonce()
        session.removal_confirmation_code = f"{session.removal_flow_nonce:08x}{session.removal_revision:04x}"
        session.state = CalendarState.CONFIRMING_REMOVAL
        session.update()

        return session

    def get_removal_event_ids(self, chat_id: str) -> list[str] | None:
        """
        Get the event IDs selected for removal.

        Returns:
            List of event IDs or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.CONFIRMING_REMOVAL:
            return None

        return session.selected_event_ids

    def apply_remove_selection(
        self,
        chat_id: str,
        text: str,
    ) -> CalendarSession | None:
        """Apply an explicit remove selection command while staying in selection mode."""
        session = self.get_session(chat_id)
        if not session or session.state not in (
            CalendarState.AWAITING_REMOVAL_SELECTION,
            CalendarState.CONFIRMING_REMOVAL,
        ):
            return None

        normalized = (text or "").strip().lower()
        event_ids: list[str] | None = None

        if normalized == "all":
            event_ids = [event["event_id"] for event in session.events_for_removal]
        elif normalized == "none":
            event_ids = []
        elif self._REMOVE_NUMBER_SELECTION_PATTERN.fullmatch(normalized):
            event_ids = self._parse_remove_number_selection(
                normalized,
                session.events_for_removal,
            )

        if event_ids is None:
            return None

        session.selected_event_ids = event_ids
        session.state = CalendarState.AWAITING_REMOVAL_SELECTION
        session.removal_revision += 1
        session.removal_confirmation_code = ""
        session.update()
        return session

    def finalize_remove_selection(self, chat_id: str) -> dict[str, Any] | None:
        """Lock the current remove selection into an explicit delete preview."""
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.AWAITING_REMOVAL_SELECTION:
            return None
        if not session.selected_event_ids:
            return None

        items = self._get_selected_removal_items(session)
        if len(items) != len(session.selected_event_ids):
            return None

        session.removal_confirmation_code = f"{session.removal_flow_nonce:08x}{session.removal_revision:04x}"
        session.state = CalendarState.CONFIRMING_REMOVAL
        session.update()
        return {
            "revision": session.removal_revision,
            "code": session.removal_confirmation_code,
            "event_ids": list(session.selected_event_ids),
            "items": items,
        }

    def validate_remove_confirmation(
        self,
        chat_id: str,
        user_id: str | None,
        code: str,
    ) -> dict[str, Any]:
        """Validate explicit delete confirmation against owner and preview code."""
        session = self.get_session(chat_id)
        if not session:
            return {"ok": False, "reason": "missing_session"}
        if session.user_id != user_id:
            return {"ok": False, "reason": "wrong_owner"}
        if session.state != CalendarState.CONFIRMING_REMOVAL:
            return {"ok": False, "reason": "invalid_state"}
        if not session.removal_confirmation_code or session.removal_confirmation_code != code:
            return {"ok": False, "reason": "stale_revision"}
        if not session.selected_event_ids:
            return {"ok": False, "reason": "no_selection"}

        items = self._get_selected_removal_items(session)
        if len(items) != len(session.selected_event_ids):
            return {"ok": False, "reason": "stale_revision"}

        return {
            "ok": True,
            "revision": session.removal_revision,
            "code": session.removal_confirmation_code,
            "event_ids": list(session.selected_event_ids),
            "items": items,
        }

    def confirm_remove_selection(
        self,
        chat_id: str,
        user_id: str | None,
        code: str,
    ) -> dict[str, Any] | None:
        """Return confirmed removal payload when the owner and preview code still match."""
        result = self.validate_remove_confirmation(chat_id, user_id, code)
        return result if result.get("ok") else None

    def _next_remove_flow_nonce(self) -> int:
        """Return a process-local monotonic nonce for remove-session uniqueness."""
        self._remove_flow_nonce_counter += 1
        return self._remove_flow_nonce_counter

    def _parse_remove_number_selection(
        self,
        text: str,
        events: list[dict[str, Any]],
    ) -> list[str] | None:
        """Parse comma-separated remove indexes without guessing mixed input."""
        selected_ids: list[str] = []
        seen_ids = set()

        for part in [piece.strip() for piece in text.split(",")]:
            index = int(part) - 1
            if index < 0 or index >= len(events):
                return None
            event_id = events[index]["event_id"]
            if event_id not in seen_ids:
                selected_ids.append(event_id)
                seen_ids.add(event_id)

        return selected_ids

    def _get_selected_removal_items(self, session: CalendarSession) -> list[dict[str, Any]]:
        """Resolve selected removal items in the same order as the current selection."""
        events_by_id = {event["event_id"]: event for event in session.events_for_removal}
        return [
            {
                "event_id": event_id,
                "title": events_by_id[event_id]["title"],
                "date": events_by_id[event_id]["date"],
            }
            for event_id in session.selected_event_ids
            if event_id in events_by_id
        ]

    # =========================================================================
    # Image Date Extraction Flow
    # =========================================================================

    def start_extraction_flow(
        self, chat_id: str, user_id: str, extracted_dates: list[dict[str, Any]], is_friend: bool = False
    ) -> CalendarSession:
        """
        Start flow for processing dates extracted from an image.

        Args:
            chat_id: Chat identifier
            user_id: User identifier
            extracted_dates: List of {date, title, description} dicts
            is_friend: Whether user is LINE friend

        Returns:
            CalendarSession in PROCESSING_EXTRACTED_DATES state
        """
        session = self.get_or_create_session(chat_id, user_id)
        session.reset()
        session.state = CalendarState.PROCESSING_EXTRACTED_DATES
        session.extracted_dates = extracted_dates
        session.current_extraction_index = 0
        session.pending_is_friend = is_friend
        session.update()

        logger.info(f"📅 Started extraction flow for chat {chat_id} with {len(extracted_dates)} dates")
        return session

    def get_current_extracted_date(self, chat_id: str) -> dict[str, Any] | None:
        """
        Get the current date being processed from extraction.

        Returns:
            Dict with date info or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.PROCESSING_EXTRACTED_DATES:
            return None

        if session.current_extraction_index >= len(session.extracted_dates):
            return None

        return session.extracted_dates[session.current_extraction_index]

    def advance_extraction_index(self, chat_id: str) -> bool:
        """
        Move to the next extracted date.

        Returns:
            True if there are more dates, False if done
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.PROCESSING_EXTRACTED_DATES:
            return False

        session.current_extraction_index += 1
        session.update()

        return session.current_extraction_index < len(session.extracted_dates)

    def set_extraction_reminder_days(self, chat_id: str, reminder_days: list[int]) -> dict[str, Any] | None:
        """
        Set reminder days for current extracted date.

        Returns:
            Dict with full event data ready for creation
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.PROCESSING_EXTRACTED_DATES:
            return None

        current = self.get_current_extracted_date(chat_id)
        if not current:
            return None

        # Always include day-of
        if 0 not in reminder_days:
            reminder_days.append(0)

        return {
            "date": current.get("date"),
            "title": current.get("title", "Event from image"),
            "description": current.get("description", ""),
            "reminder_days": reminder_days,
            "is_friend": session.pending_is_friend,
        }

    # =========================================================================
    # Zeus Scrape Flow - Extract dates from recent chat messages
    # =========================================================================

    def start_scrape_flow(
        self, chat_id: str, user_id: str, source_messages: list[str], is_friend: bool = False
    ) -> CalendarSession:
        """
        Start the scrape flow to extract dates from recent messages.

        Args:
            chat_id: Chat identifier
            user_id: User identifier
            source_messages: Recent messages to analyze
            is_friend: Whether user is LINE friend

        Returns:
            CalendarSession in SCRAPE_PROCESSING state
        """
        session = self.get_or_create_session(chat_id, user_id)
        self._clear_recent_scrape_marker(chat_id, user_id)
        self._clear_recent_scrape_marker(f"user_{user_id}", user_id)
        session.reset()
        session.state = CalendarState.SCRAPE_PROCESSING
        session.scraped_source_messages = source_messages
        session.pending_is_friend = is_friend
        session.update()

        logger.info(f"📅 Started scrape flow for chat {chat_id} with {len(source_messages)} messages")
        return session

    def set_discrete_scrape_target(self, chat_id: str, target_user_id: str) -> bool:
        """
        Set discrete scrape target for sending DMs.

        Args:
            chat_id: Chat identifier (group where scraping occurs)
            target_user_id: User ID to send confirmations/reminders to

        Returns:
            True if set successfully
        """
        session = self.get_session(chat_id)
        if not session:
            logger.warning(f"⚠️ No session found for discrete scrape target: {chat_id}")
            return False

        self._clear_conflicting_discrete_sessions(chat_id, target_user_id)
        session.discrete_scrape_target = target_user_id
        self._clear_recent_scrape_marker(f"user_{target_user_id}", session.user_id)
        session.update()
        logger.info(f"🔒 Set discrete scrape target for {chat_id} -> user {target_user_id}")
        return True

    def _clear_conflicting_discrete_sessions(self, chat_id: str, target_user_id: str) -> None:
        """Keep DM scrape replies unambiguous by allowing one DM/discrete session per user."""
        conflicting_chat_ids: list[str] = []
        user_chat_id = f"user_{target_user_id}"

        for candidate_chat_id, candidate in list(self._sessions.items()):
            if candidate_chat_id == chat_id:
                continue
            if candidate_chat_id == user_chat_id and candidate.state != CalendarState.IDLE:
                conflicting_chat_ids.append(candidate_chat_id)
                continue
            if candidate.user_id != target_user_id:
                continue
            if candidate.discrete_scrape_target != target_user_id:
                continue
            if candidate.state not in {
                CalendarState.SCRAPE_PROCESSING,
                CalendarState.SCRAPE_SELECTING,
                CalendarState.SCRAPE_REMINDER_DAYS,
            }:
                continue
            conflicting_chat_ids.append(candidate_chat_id)

        for conflicting_chat_id in conflicting_chat_ids:
            self.end_session(conflicting_chat_id)

    def resolve_discrete_scrape_chat_id(
        self,
        chat_id: str,
        user_id: str | None,
    ) -> str:
        """Resolve DM replies back to the owning discrete scrape session when one exists."""
        if not user_id or chat_id in self._sessions:
            return chat_id

        for candidate_chat_id, candidate in list(self._sessions.items()):
            if candidate.user_id != user_id:
                continue
            if candidate.discrete_scrape_target != user_id:
                continue
            if candidate.state not in {
                CalendarState.SCRAPE_PROCESSING,
                CalendarState.SCRAPE_REVIEWING,
                CalendarState.SCRAPE_SELECTING,
                CalendarState.SCRAPE_REMINDER_DAYS,
            }:
                continue

            live_session = self.get_session(candidate_chat_id)
            if not live_session:
                continue
            if live_session.user_id == user_id and live_session.discrete_scrape_target == user_id:
                return candidate_chat_id

        return chat_id

    def get_discrete_scrape_target(self, chat_id: str) -> str | None:
        """
        Get discrete scrape target user ID.

        Returns:
            User ID for discrete scrape DM delivery, or None
        """
        session = self.get_session(chat_id)
        return session.discrete_scrape_target if session else None

    def clear_discrete_scrape_target(self, chat_id: str) -> None:
        """Drop discrete DM routing so the scrape flow can continue in the current chat."""
        session = self.get_session(chat_id)
        if not session or session.discrete_scrape_target is None:
            return
        session.discrete_scrape_target = None
        session.update()

    # =========================================================================
    # Live Bulk Add Flow ("zeus add event") - Enhanced with Smart Mode Selection
    # =========================================================================

    def start_add_mode_selection(self, chat_id: str, user_id: str, is_friend: bool = False) -> None:
        """Start the add mode selection flow (scan/listen/manual)."""
        session = self.get_or_create_session(chat_id, user_id)
        session.state = CalendarState.ADD_MODE_SELECTION
        session.pending_is_friend = is_friend
        session.update()
        logger.info(f"📅 Started add mode selection for chat {chat_id}")

    def start_live_add_flow(
        self,
        chat_id: str,
        user_id: str,
        is_friend: bool = False,
    ) -> CalendarSession:
        """Start the live bulk-add flow that scrapes incoming messages."""
        session = self.get_or_create_session(chat_id, user_id)
        session.reset()
        session.state = CalendarState.LIVE_ADD_LISTENING
        session.pending_is_friend = is_friend
        session.update()
        logger.info(f"📅 Started live bulk-add flow for chat {chat_id}")
        return session

    def add_live_events(
        self,
        chat_id: str,
        events: list[dict[str, Any]],
    ) -> CalendarSession | None:
        """Append newly detected live events and move to review state if needed."""
        session = self.get_session(chat_id)
        if not session or session.state not in (
            CalendarState.LIVE_ADD_LISTENING,
            CalendarState.LIVE_ADD_REVIEWING,
        ):
            return None

        if not events:
            return session

        session.live_events.extend(events)
        # If we were just listening, switch to reviewing starting at the first new event.
        if session.state == CalendarState.LIVE_ADD_LISTENING:
            session.current_live_index = max(0, len(session.live_events) - len(events))
            session.state = CalendarState.LIVE_ADD_REVIEWING
        session.update()
        return session

    def get_current_live_event(self, chat_id: str) -> dict[str, Any] | None:
        """Return the current live-scraped event dict."""
        session = self.get_session(chat_id)
        if not session or session.state not in (
            CalendarState.LIVE_ADD_REVIEWING,
            CalendarState.LIVE_ADD_REMINDER_DAYS,
        ):
            return None
        if session.current_live_index >= len(session.live_events):
            return None
        return session.live_events[session.current_live_index]

    def accept_live_event(self, chat_id: str) -> CalendarSession | None:
        """Move from reviewing to reminder-days selection for the current live event."""
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.LIVE_ADD_REVIEWING:
            return None
        session.state = CalendarState.LIVE_ADD_REMINDER_DAYS
        session.update()
        return session

    def skip_live_event(self, chat_id: str) -> bool:
        """Skip current live event and return True if more remain."""
        session = self.get_session(chat_id)
        if not session or session.state not in (
            CalendarState.LIVE_ADD_REVIEWING,
            CalendarState.LIVE_ADD_REMINDER_DAYS,
        ):
            return False
        session.current_live_index += 1
        session.state = CalendarState.LIVE_ADD_REVIEWING
        session.update()
        return session.current_live_index < len(session.live_events)

    def set_live_reminder_days(
        self,
        chat_id: str,
        reminder_days: list[int],
    ) -> dict[str, Any] | None:
        """Return full event data for creation based on current live event."""
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.LIVE_ADD_REMINDER_DAYS:
            return None

        current = self.get_current_live_event(chat_id)
        if not current:
            return None

        if 0 not in reminder_days:
            reminder_days.append(0)

        return {
            "date": current.get("date"),
            "title": current.get("title", "Event"),
            "description": current.get("description", ""),
            "source_text": current.get("source_text", ""),
            "reminder_days": reminder_days,
            "is_friend": session.pending_is_friend,
        }

    def set_scraped_events(self, chat_id: str, events: list[dict[str, Any]]) -> CalendarSession | None:
        """
        Set the events extracted from scraping.

        Args:
            chat_id: Chat identifier
            events: List of extracted event dicts

        Returns:
            Updated session in SCRAPE_SELECTING state
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.SCRAPE_PROCESSING:
            return None

        session.scraped_events = events
        session.current_scrape_index = 0
        session.selected_scraped_indices = []
        session.scrape_selection_revision = 1
        session.scrape_preview_revision = 0
        session.state = CalendarState.SCRAPE_SELECTING
        session.update()

        logger.info(f"📅 Found {len(events)} events in scrape for chat {chat_id}")
        return session

    def get_current_scraped_event(self, chat_id: str) -> dict[str, Any] | None:
        """
        Get the current scraped event being reviewed.

        Returns:
            Current event dict or None
        """
        session = self.get_session(chat_id)
        if not session or session.state not in (
            CalendarState.SCRAPE_SELECTING,
            CalendarState.SCRAPE_REMINDER_DAYS,
        ):
            return None
        if session.current_scrape_index >= len(session.scraped_events):
            return None
        return session.scraped_events[session.current_scrape_index]

    def accept_scraped_event(self, chat_id: str) -> CalendarSession | None:
        """
        Accept the current scraped event and move to reminder days state.

        Returns:
            Updated session or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.SCRAPE_SELECTING:
            return None
        session.state = CalendarState.SCRAPE_REMINDER_DAYS
        session.update()
        return session

    def skip_scraped_event(self, chat_id: str) -> bool:
        """
        Skip the current scraped event and return True if more remain.

        Returns:
            True if there are more events, False if done
        """
        session = self.get_session(chat_id)
        if not session or session.state not in (
            CalendarState.SCRAPE_SELECTING,
            CalendarState.SCRAPE_REMINDER_DAYS,
        ):
            return False
        session.current_scrape_index += 1
        session.state = CalendarState.SCRAPE_SELECTING
        session.update()
        return session.current_scrape_index < len(session.scraped_events)

    def get_scrape_progress(self, chat_id: str) -> tuple[int, int]:
        """
        Get the current scrape progress as (current, total).

        Returns:
            Tuple of (current_index_1_based, total_events)
        """
        session = self.get_session(chat_id)
        if not session:
            return (0, 0)
        current = min(session.current_scrape_index + 1, len(session.scraped_events))
        total = len(session.scraped_events)
        return (current, total)

    def set_scrape_reminder_days(self, chat_id: str, reminder_days: list[int]) -> dict[str, Any] | None:
        """
        Set reminder days for the current scraped event.

        Returns:
            Dict with full event data ready for creation
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.SCRAPE_REMINDER_DAYS:
            return None

        current = self.get_current_scraped_event(chat_id)
        if not current:
            return None

        # Always include day-of
        if 0 not in reminder_days:
            reminder_days.append(0)

        return {
            "date": current.get("date"),
            "title": current.get("title", "Event"),
            "description": current.get("description", ""),
            "reminder_days": reminder_days,
            "is_friend": session.pending_is_friend,
        }

    def advance_scrape_index(self, chat_id: str) -> bool:
        """
        Advance to the next scraped event.

        Returns:
            True if there are more events, False if done
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.SCRAPE_REMINDER_DAYS:
            return False
        session.current_scrape_index += 1
        session.state = CalendarState.SCRAPE_SELECTING
        session.update()
        return session.current_scrape_index < len(session.scraped_events)

    def apply_scrape_selection(
        self,
        chat_id: str,
        text: str,
    ) -> CalendarSession | None:
        """Apply an explicit scrape-batch selection command while staying in selection mode."""
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.SCRAPE_SELECTING:
            return None

        normalized = (text or "").strip().lower()

        if normalized == "all":
            session.selected_scraped_indices = list(range(len(session.scraped_events)))
        elif normalized == "none":
            session.selected_scraped_indices = []
        elif self._SCRAPE_NUMBER_SELECTION_PATTERN.fullmatch(normalized):
            toggled = self._toggle_scrape_number_selection(
                normalized,
                session.scraped_events,
                session.selected_scraped_indices,
            )
            if toggled is None:
                return None
            session.selected_scraped_indices = toggled
        else:
            return None

        session.scrape_selection_revision += 1
        session.scrape_preview_revision = 0
        session.state = CalendarState.SCRAPE_SELECTING
        session.update()
        return session

    def get_selected_scraped_events(self, chat_id: str) -> list[dict[str, Any]]:
        """Return the currently selected scraped events in numeric order."""
        session = self.get_session(chat_id)
        if not session:
            return []

        selected_events: list[dict[str, Any]] = []
        for index in session.selected_scraped_indices:
            if index < 0 or index >= len(session.scraped_events):
                return []
            selected_events.append(session.scraped_events[index])
        return selected_events

    def finalize_scrape_selection(self, chat_id: str) -> dict[str, Any] | None:
        """Lock the current scrape selection and transition to the shared reminder step."""
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.SCRAPE_SELECTING:
            return None
        if not session.selected_scraped_indices:
            return None

        selected_events = self.get_selected_scraped_events(chat_id)
        if len(selected_events) != len(session.selected_scraped_indices):
            return None

        session.scrape_preview_revision = session.scrape_selection_revision
        session.state = CalendarState.SCRAPE_REMINDER_DAYS
        session.update()
        return {
            "revision": session.scrape_preview_revision,
            "selected_indices": list(session.selected_scraped_indices),
            "items": selected_events,
        }

    def validate_scrape_batch_confirmation(
        self,
        chat_id: str,
        user_id: str | None,
    ) -> dict[str, Any]:
        """Validate that the shared reminder choice still matches the preview owner and revision."""
        session = self.get_session(chat_id)
        if not session:
            return {"ok": False, "reason": "missing_session"}
        if session.user_id != user_id:
            return {"ok": False, "reason": "wrong_owner"}
        if session.state != CalendarState.SCRAPE_REMINDER_DAYS:
            return {"ok": False, "reason": "invalid_state"}
        if session.scrape_preview_revision == 0:
            return {"ok": False, "reason": "invalid_state"}
        if session.scrape_preview_revision != session.scrape_selection_revision:
            return {"ok": False, "reason": "stale_revision"}
        if not session.selected_scraped_indices:
            return {"ok": False, "reason": "no_selection"}

        selected_events = self.get_selected_scraped_events(chat_id)
        if len(selected_events) != len(session.selected_scraped_indices):
            return {"ok": False, "reason": "stale_revision"}

        return {
            "ok": True,
            "revision": session.scrape_preview_revision,
            "items": selected_events,
            "is_friend": session.pending_is_friend,
        }

    def _toggle_scrape_number_selection(
        self,
        text: str,
        events: list[dict[str, Any]],
        current_selection: list[int],
    ) -> list[int] | None:
        """Toggle selected scrape indexes without guessing mixed or out-of-range input."""
        toggled = set(current_selection)

        for part in [piece.strip() for piece in text.split(",")]:
            index = int(part) - 1
            if index < 0 or index >= len(events):
                return None
            if index in toggled:
                toggled.remove(index)
            else:
                toggled.add(index)

        return sorted(toggled)

    # =========================================================================
    # Zeus Add [date] [title] - Inline Add Flow
    # =========================================================================

    def start_inline_add_flow(
        self, chat_id: str, user_id: str, event_date: date, title: str, description: str = "", is_friend: bool = False
    ) -> CalendarSession:
        """
        Start inline add flow with pre-parsed date and title.

        Skips the date and title input steps.

        Args:
            chat_id: Chat identifier
            user_id: User identifier
            event_date: Pre-parsed event date
            title: Pre-parsed event title
            description: Optional description
            is_friend: Whether user is LINE friend

        Returns:
            CalendarSession in INLINE_ADD_REMINDER_DAYS state
        """
        session = self.get_or_create_session(chat_id, user_id)
        session.reset()
        session.state = CalendarState.INLINE_ADD_REMINDER_DAYS
        session.inline_event_data = {
            "date": event_date,
            "title": title,
            "description": description,
        }
        session.pending_is_friend = is_friend
        session.update()

        logger.info(f"📅 Started inline add flow for chat {chat_id}: {title} on {event_date}")
        return session

    def set_inline_reminder_days(self, chat_id: str, reminder_days: list[int]) -> dict[str, Any] | None:
        """
        Set reminder days for inline add event.

        Returns:
            Dict with full event data ready for creation
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.INLINE_ADD_REMINDER_DAYS:
            return None

        if not session.inline_event_data:
            return None

        # Always include day-of reminder
        if 0 not in reminder_days:
            reminder_days.append(0)

        session.pending_reminder_days = reminder_days
        session.state = CalendarState.INLINE_ADD_CONFIRMING
        session.update()

        return {
            "date": session.inline_event_data.get("date"),
            "title": session.inline_event_data.get("title", "Event"),
            "description": session.inline_event_data.get("description", ""),
            "reminder_days": reminder_days,
            "is_friend": session.pending_is_friend,
        }

    def get_inline_event_data(self, chat_id: str) -> dict[str, Any] | None:
        """
        Get the inline event data for display/confirmation.

        Returns:
            Dict with date, title, description
        """
        session = self.get_session(chat_id)
        if not session or session.state not in (CalendarState.INLINE_ADD_REMINDER_DAYS, CalendarState.INLINE_ADD_CONFIRMING):
            return None

        return session.inline_event_data

    # =========================================================================
    # Common Operations
    # =========================================================================

    def end_session(self, chat_id: str) -> None:
        """End and remove a session."""
        session = self._sessions.get(chat_id)
        if chat_id in self._sessions:
            del self._sessions[chat_id]
            logger.info(f"📅 Ended calendar session for chat {chat_id}")
        if session is not None:
            if session.state in {
                CalendarState.AWAITING_REMOVAL_SELECTION,
                CalendarState.CONFIRMING_REMOVAL,
            }:
                self._recently_expired_remove_flows.setdefault(chat_id, {})[session.user_id] = datetime.now()
            elif session.state in {
                CalendarState.SCRAPE_PROCESSING,
                CalendarState.SCRAPE_SELECTING,
                CalendarState.SCRAPE_REMINDER_DAYS,
            }:
                self._mark_recent_scrape_followup(session)
            else:
                self._clear_recent_remove_marker(chat_id, session.user_id)
        else:
            self._recently_expired_remove_flows.pop(chat_id, None)

    def had_recent_remove_flow(
        self,
        chat_id: str,
        user_id: str | None,
        grace_seconds: int = 180,
    ) -> bool:
        """Return whether a remove flow expired recently enough to explain a stale follow-up."""
        if not user_id:
            return False
        chat_markers = self._recently_expired_remove_flows.get(chat_id)
        if chat_markers is None:
            return False
        expired_at = chat_markers.get(user_id)
        if expired_at is None:
            return False
        if (datetime.now() - expired_at).total_seconds() > grace_seconds:
            del chat_markers[user_id]
            if not chat_markers:
                del self._recently_expired_remove_flows[chat_id]
            return False
        return True

    def had_recent_scrape_flow(
        self,
        chat_id: str,
        user_id: str | None,
        grace_seconds: int = 90,
    ) -> bool:
        """Return whether a scrape flow expired recently enough to explain an explicit follow-up."""
        if not user_id:
            return False
        chat_markers = self._recently_expired_scrape_flows.get(chat_id)
        if chat_markers is None:
            return False
        expired_at = chat_markers.get(user_id)
        if expired_at is None:
            return False
        if (datetime.now() - expired_at).total_seconds() > grace_seconds:
            del chat_markers[user_id]
            if not chat_markers:
                del self._recently_expired_scrape_flows[chat_id]
            return False
        return True

    def _mark_recent_scrape_followup(self, session: CalendarSession) -> None:
        """Remember expired scrape sessions briefly so explicit follow-ups fail closed."""
        if not session.user_id:
            return

        keys = {session.chat_id}
        if session.discrete_scrape_target:
            keys.add(f"user_{session.discrete_scrape_target}")

        now = datetime.now()
        for key in keys:
            self._recently_expired_scrape_flows.setdefault(key, {})[session.user_id] = now

    def _clear_recent_scrape_marker(
        self,
        chat_id: str,
        user_id: str | None,
    ) -> None:
        """Clear scrape-expiry markers once a new scrape flow starts."""
        if not user_id:
            return
        chat_markers = self._recently_expired_scrape_flows.get(chat_id)
        if not chat_markers:
            return
        chat_markers.pop(user_id, None)
        if not chat_markers:
            self._recently_expired_scrape_flows.pop(chat_id, None)

    def cancel_flow(self, chat_id: str) -> bool:
        """
        Cancel the current flow and reset session.

        Returns:
            True if a flow was cancelled
        """
        session = self.get_session(chat_id)
        if not session or session.state == CalendarState.IDLE:
            return False

        session.reset()
        logger.info(f"📅 Cancelled calendar flow for chat {chat_id}")
        return True

    def start_cleanup(self):
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
            logger.info("📅 Calendar session cleanup task started")

    async def stop_cleanup(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=5.0)
            except TimeoutError:
                logger.warning("⚠️ Calendar cleanup task shutdown timed out")
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None
            logger.info("📅 Calendar session cleanup task stopped")

    async def _cleanup_loop(self):
        """Background task to clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval_seconds)
                self._cleanup_expired_sessions()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"❌ Calendar session cleanup error: {e}")

    def _cleanup_expired_sessions(self):
        """Remove expired sessions."""
        expired = [
            (chat_id, session) for chat_id, session in self._sessions.items() if session.is_expired(self._session_ttl_seconds)
        ]

        for chat_id, session in expired:
            if session.state in {
                CalendarState.AWAITING_REMOVAL_SELECTION,
                CalendarState.CONFIRMING_REMOVAL,
            }:
                self._recently_expired_remove_flows.setdefault(chat_id, {})[session.user_id] = datetime.now()
            elif session.state in {
                CalendarState.SCRAPE_PROCESSING,
                CalendarState.SCRAPE_SELECTING,
                CalendarState.SCRAPE_REMINDER_DAYS,
            }:
                self._mark_recent_scrape_followup(session)
            del self._sessions[chat_id]

        self._prune_recent_remove_flow_markers()

        if expired:
            logger.info(f"📅 Cleaned up {len(expired)} expired calendar sessions")

    def _prune_recent_remove_flow_markers(self, grace_seconds: int = 180) -> None:
        """Drop expired recent-remove markers without requiring a chat lookup."""
        now = datetime.now()
        expired_chat_ids: list[str] = []
        for chat_id, user_markers in self._recently_expired_remove_flows.items():
            expired_users = [
                user_id for user_id, expired_at in user_markers.items() if (now - expired_at).total_seconds() > grace_seconds
            ]
            for user_id in expired_users:
                del user_markers[user_id]
            if not user_markers:
                expired_chat_ids.append(chat_id)
        for chat_id in expired_chat_ids:
            del self._recently_expired_remove_flows[chat_id]

    def _clear_recent_remove_marker(self, chat_id: str, user_id: str | None) -> None:
        """Clear the recent remove marker for one user in one chat."""
        if not user_id:
            return
        chat_markers = self._recently_expired_remove_flows.get(chat_id)
        if not chat_markers:
            return
        chat_markers.pop(user_id, None)
        if not chat_markers:
            del self._recently_expired_remove_flows[chat_id]


# Singleton instance
calendar_session_manager = CalendarSessionManager()
