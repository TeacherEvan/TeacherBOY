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
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Any
from enum import Enum
from dataclasses import dataclass, field

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


@dataclass
class CalendarSession:
    """Session data for calendar operations."""
    
    user_id: str
    chat_id: str
    state: CalendarState = CalendarState.IDLE
    
    # Event being created
    pending_date: Optional[date] = None
    pending_title: Optional[str] = None
    pending_description: Optional[str] = None
    pending_reminder_days: Optional[List[int]] = None
    pending_is_friend: bool = False
    
    # For removal flow
    events_for_removal: List[Dict[str, Any]] = field(default_factory=list)
    selected_event_ids: List[str] = field(default_factory=list)
    
    # For image date extraction
    extracted_dates: List[Dict[str, Any]] = field(default_factory=list)  # [{date, title, description}]
    current_extraction_index: int = 0
    
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
        self.extracted_dates = []
        self.current_extraction_index = 0
        self.update()


class CalendarSessionManager:
    """Manages multi-step calendar sessions."""

    def __init__(self):
        """Initialize calendar session manager."""
        self._sessions: Dict[str, CalendarSession] = {}
        self._session_ttl_seconds = 120  # 2 minutes per step
        self._cleanup_task: Optional[asyncio.Task] = None
        self._cleanup_interval_seconds = 60

    def get_session(self, chat_id: str) -> Optional[CalendarSession]:
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
            del self._sessions[chat_id]
            return None
        
        return session

    def get_or_create_session(
        self, 
        chat_id: str, 
        user_id: str
    ) -> CalendarSession:
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
        
        session = CalendarSession(user_id=user_id, chat_id=chat_id)
        self._sessions[chat_id] = session
        logger.info(f"📅 Created calendar session for chat {chat_id}")
        return session

    def is_in_calendar_flow(self, chat_id: str) -> bool:
        """Check if chat is in an active calendar flow."""
        session = self.get_session(chat_id)
        return session is not None and session.state != CalendarState.IDLE

    def is_session_owner(
        self, 
        chat_id: str, 
        user_id: Optional[str]
    ) -> bool:
        """Check if user owns the session."""
        session = self.get_session(chat_id)
        if not session:
            return True  # No session, anyone can start one
        return session.user_id == user_id

    # =========================================================================
    # Add Event Flow
    # =========================================================================

    def start_add_flow(
        self, 
        chat_id: str, 
        user_id: str,
        is_friend: bool = False
    ) -> CalendarSession:
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

    def set_pending_date(self, chat_id: str, event_date: date) -> Optional[CalendarSession]:
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

    def set_pending_title(self, chat_id: str, title: str) -> Optional[CalendarSession]:
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

    def set_pending_description(
        self, 
        chat_id: str, 
        description: str
    ) -> Optional[CalendarSession]:
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

    def set_pending_reminder_days(
        self, 
        chat_id: str, 
        reminder_days: List[int]
    ) -> Optional[CalendarSession]:
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

    def get_pending_event_data(self, chat_id: str) -> Optional[Dict[str, Any]]:
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

    def start_removal_flow(
        self, 
        chat_id: str, 
        user_id: str,
        events: List[Dict[str, Any]]
    ) -> CalendarSession:
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
        session.update()
        
        logger.info(f"📅 Started removal flow for chat {chat_id} with {len(events)} events")
        return session

    def set_removal_selection(
        self, 
        chat_id: str, 
        event_ids: List[str]
    ) -> Optional[CalendarSession]:
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
        session.state = CalendarState.CONFIRMING_REMOVAL
        session.update()
        
        return session

    def get_removal_event_ids(self, chat_id: str) -> Optional[List[str]]:
        """
        Get the event IDs selected for removal.

        Returns:
            List of event IDs or None
        """
        session = self.get_session(chat_id)
        if not session or session.state != CalendarState.CONFIRMING_REMOVAL:
            return None
        
        return session.selected_event_ids

    # =========================================================================
    # Image Date Extraction Flow
    # =========================================================================

    def start_extraction_flow(
        self, 
        chat_id: str, 
        user_id: str,
        extracted_dates: List[Dict[str, Any]],
        is_friend: bool = False
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
        
        logger.info(
            f"📅 Started extraction flow for chat {chat_id} "
            f"with {len(extracted_dates)} dates"
        )
        return session

    def get_current_extracted_date(self, chat_id: str) -> Optional[Dict[str, Any]]:
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

    def set_extraction_reminder_days(
        self, 
        chat_id: str, 
        reminder_days: List[int]
    ) -> Optional[Dict[str, Any]]:
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
    # Common Operations
    # =========================================================================

    def end_session(self, chat_id: str) -> None:
        """End and remove a session."""
        if chat_id in self._sessions:
            del self._sessions[chat_id]
            logger.info(f"📅 Ended calendar session for chat {chat_id}")

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

    def stop_cleanup(self):
        """Stop background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
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
            chat_id for chat_id, session in self._sessions.items()
            if session.is_expired(self._session_ttl_seconds)
        ]
        
        for chat_id in expired:
            del self._sessions[chat_id]
        
        if expired:
            logger.info(f"📅 Cleaned up {len(expired)} expired calendar sessions")


# Singleton instance
calendar_session_manager = CalendarSessionManager()
