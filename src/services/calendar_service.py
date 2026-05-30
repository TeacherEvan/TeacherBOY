"""
Calendar Service - Event storage and management with HF Hub persistence.

This service provides calendar event storage and retrieval with support for:
- User-specific event management
- Reminder scheduling integration
- Hugging Face Hub persistence (like conversation memory)
- Local JSON fallback

Events are tied to:
- user_id: The LINE user who created the event
- chat_id: The group/room/DM where the event was created
- reminder_days: Days before event to send reminders [7, 3, 1, 0]
"""

import asyncio
import hashlib
import json
import logging
import os
import uuid
import base64
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict

from src.services.history_log_service import get_history_log, EventType, LogLevel
from src.services.calendar_validator import calendar_validator
from src.config import settings

logger = logging.getLogger(__name__)

# Configuration constants
SYNC_INTERVAL_MINUTES = 5  # How often to sync to HF Hub
CALENDAR_FILENAME = "calendar_events.json"


def _schedule_audit_log(coro: "asyncio.Future[Any] | asyncio.coroutines.CoroWrapper | Any") -> None:
    """Best-effort scheduling of audit logging without breaking sync call sites."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(coro)


class CalendarEvent:
    """Represents a calendar event with reminder settings."""
    
    def __init__(
        self,
        event_id: str,
        user_id: str,
        chat_id: str,
        title: str,
        event_date: date,
        description: str = "",
        reminder_days: Optional[List[int]] = None,
        is_friend: bool = False,
        notification_target_user_id: Optional[str] = None,
        notified_dates: Optional[List[str]] = None,
        created_at: Optional[datetime] = None,
    ):
        """
        Initialize a calendar event.
        
        Args:
            event_id: Unique event identifier
            user_id: LINE user ID who created the event
            chat_id: Chat ID where event was created (group_xxx, room_xxx, or user_xxx)
            title: Event title
            event_date: Date of the event
            description: Optional event description
            reminder_days: Days before to remind [7, 3, 1, 0]. 0 = day-of (required)
            is_friend: Whether user is a LINE friend (for DM vs group notifications)
            notified_dates: List of dates when reminders were already sent
            created_at: When event was created
        """
        self.event_id = event_id
        self.user_id = user_id
        self.chat_id = chat_id
        self.title = title
        self.event_date = event_date
        self.description = description
        # Always include day-of reminder (0)
        self.reminder_days = reminder_days if reminder_days else [7, 3, 1, 0]
        if 0 not in self.reminder_days:
            self.reminder_days.append(0)
        self.is_friend = is_friend
        self.notification_target_user_id = notification_target_user_id or user_id
        self.notified_dates = notified_dates if notified_dates else []
        self.created_at = created_at or datetime.now(timezone.utc)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary for JSON serialization."""
        return {
            "event_id": self.event_id,
            "user_id": self.user_id,
            "chat_id": self.chat_id,
            "title": self.title,
            "event_date": self.event_date.isoformat(),
            "description": self.description,
            "reminder_days": self.reminder_days,
            "is_friend": self.is_friend,
            "notification_target_user_id": self.notification_target_user_id,
            "notified_dates": self.notified_dates,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CalendarEvent":
        """Create event from dictionary."""
        event_date_raw = data.get("event_date")
        event_date_parsed: date
        if isinstance(event_date_raw, str):
            event_date_parsed = date.fromisoformat(event_date_raw)
        elif isinstance(event_date_raw, date):
            event_date_parsed = event_date_raw
        else:
            event_date_parsed = date.today()  # Fallback
        
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        
        return cls(
            event_id=data.get("event_id", str(uuid.uuid4())),
            user_id=data.get("user_id", ""),
            chat_id=data.get("chat_id", ""),
            title=data.get("title", ""),
            event_date=event_date_parsed,
            description=data.get("description", ""),
            reminder_days=data.get("reminder_days", [7, 3, 1, 0]),
            is_friend=data.get("is_friend", False),
            notification_target_user_id=data.get("notification_target_user_id"),
            notified_dates=data.get("notified_dates", []),
            created_at=created_at,
        )

    def days_until(self) -> int:
        """Calculate days until this event."""
        today = date.today()
        return (self.event_date - today).days

    def is_past(self) -> bool:
        """Check if event date has passed."""
        return self.event_date < date.today()

    def needs_reminder(self, days_before: int) -> bool:
        """
        Check if event needs a reminder for the given days_before value.
        
        Args:
            days_before: Number of days before event (0 = day-of)
            
        Returns:
            True if reminder should be sent
        """
        if days_before not in self.reminder_days:
            return False
        
        reminder_date = (self.event_date - timedelta(days=days_before)).isoformat()
        return reminder_date not in self.notified_dates

    def mark_notified(self, days_before: int) -> None:
        """Mark that a reminder was sent for this days_before value."""
        reminder_date = (self.event_date - timedelta(days=days_before)).isoformat()
        if reminder_date not in self.notified_dates:
            self.notified_dates.append(reminder_date)


class CalendarService:
    """
    Service for managing calendar events with HF Hub persistence.
    
    Follows the same pattern as ConversationMemoryService for HF sync.
    """

    def __init__(
        self,
        hf_token: Optional[str] = None,
        hf_repo_id: Optional[str] = None,
        local_storage_path: str = "./data/calendar",
        encryption_key: Optional[str] = None,
    ):
        """
        Initialize calendar service.
        
        Args:
            hf_token: Hugging Face API token for persistent storage
            hf_repo_id: HF dataset repo ID (e.g., "username/zeus-memory")
            local_storage_path: Local directory for event storage
            encryption_key: Optional AES encryption key for local storage (base64)
        """
        self.hf_token = hf_token
        self.hf_repo_id = hf_repo_id
        self.local_storage_path = Path(local_storage_path)
        self._encryption_key = encryption_key
        self._cipher_suite: Optional[Any] = None
        
        # In-memory event store: {event_id: CalendarEvent}
        self._events: OrderedDict[str, CalendarEvent] = OrderedDict()
        
        # Track HF Hub configuration
        self._hf_enabled = bool(hf_token and hf_repo_id)
        self._hf_api: Optional[Any] = None
        self._commit_scheduler: Optional[Any] = None
        
        # Setup encryption if key provided
        if self._encryption_key:
            self._setup_encryption()
        
        # Ensure local storage directory exists
        self.local_storage_path.mkdir(parents=True, exist_ok=True)
        
        # Load existing events
        self._load_from_local_storage()
        
        if self._hf_enabled:
            self._setup_hf_storage()
        else:
            logger.info("📅 Calendar service initialized (local storage only)")

    def _setup_encryption(self):
        """Initialize AES encryption for local storage."""
        try:
            from cryptography.fernet import Fernet
            
            # Validate key format
            key_bytes = self._encryption_key.encode() if isinstance(self._encryption_key, str) else self._encryption_key
            self._cipher_suite = Fernet(key_bytes)
            logger.info("🔒 Calendar encryption enabled")
        except Exception as e:
            logger.error(f"❌ Failed to initialize encryption: {e}")
            logger.warning("⚠️ Continuing without encryption")
            self._encryption_key = None
            self._cipher_suite = None

    def _setup_hf_storage(self):
        """Initialize Hugging Face Hub storage backend."""
        if not self.hf_token or not self.hf_repo_id:
            self._hf_enabled = False
            return

        try:
            import importlib

            hf = importlib.import_module("huggingface_hub")
            HfApi = getattr(hf, "HfApi")
            CommitScheduler = getattr(hf, "CommitScheduler")

            hf_api = HfApi(token=self.hf_token)
            self._hf_api = hf_api
            
            # Ensure the dataset repo exists
            try:
                hf_api.create_repo(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    private=True,
                    exist_ok=True,
                )
                logger.info(f"📅 HF Hub dataset ready for calendar: {self.hf_repo_id}")
            except Exception as e:
                logger.warning(f"⚠️ Could not create/verify HF repo for calendar: {e}")
                self._hf_enabled = False
                return
            
            # Set up scheduled commits
            self._commit_scheduler = CommitScheduler(
                repo_id=self.hf_repo_id,
                repo_type="dataset",
                folder_path=str(self.local_storage_path),
                every=SYNC_INTERVAL_MINUTES,
                token=self.hf_token,
                private=True,
                squash_history=True,
            )
            
            # Load existing events from HF Hub (synchronously during startup)
            self._load_from_hub_sync()
            
            logger.info("📅 Calendar service initialized with HF Hub persistence")
            
        except ModuleNotFoundError:
            logger.warning("⚠️ huggingface_hub not installed, using local storage only")
            self._hf_enabled = False
        except Exception as e:
            logger.error(f"❌ Failed to initialize HF storage for calendar: {e}")
            self._hf_enabled = False

    def _load_from_hub_sync(self):
        """Load events from HF Hub synchronously during startup."""
        if not self._hf_enabled or not self._hf_api:
            return
            
        try:
            import importlib
            hf = importlib.import_module("huggingface_hub")
            hf_hub_download = getattr(hf, "hf_hub_download")
            
            logger.info(f"📥 Downloading calendar from HF Hub: {self.hf_repo_id}")
            
            local_file = hf_hub_download(
                repo_id=self.hf_repo_id,
                filename=CALENDAR_FILENAME,
                repo_type="dataset",
                token=self.hf_token,
                local_dir=str(self.local_storage_path),
            )
            
            with open(local_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Clear existing events before loading from HF Hub
            self._events.clear()
            
            events_data = data.get("events", [])
            for event_dict in events_data:
                try:
                    event = CalendarEvent.from_dict(event_dict)
                    self._events[event.event_id] = event
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load event: {e}")
            
            logger.info(f"✅ Loaded {len(self._events)} events from HF Hub")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load events from HF Hub (repo may be empty): {e}")
            logger.info("📅 Starting with empty calendar - will sync to HF Hub on first save")

    async def _load_from_hub(self):
        """Load events from HF Hub on startup."""
        if not self._hf_enabled or not self._hf_api:
            return
            
        try:
            import importlib
            hf = importlib.import_module("huggingface_hub")
            hf_hub_download = getattr(hf, "hf_hub_download")
            
            local_file = hf_hub_download(
                repo_id=self.hf_repo_id,
                filename=CALENDAR_FILENAME,
                repo_type="dataset",
                token=self.hf_token,
                local_dir=str(self.local_storage_path),
            )
            
            with open(local_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Clear existing events before loading from HF Hub
            self._events.clear()
            
            events_data = data.get("events", [])
            for event_dict in events_data:
                try:
                    event = CalendarEvent.from_dict(event_dict)
                    self._events[event.event_id] = event
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load event: {e}")
            
            logger.info(f"📅 Loaded {len(self._events)} events from HF Hub")
            
        except Exception as e:
            logger.warning(f"⚠️ Could not load events from HF Hub: {e}")

    def _load_from_local_storage(self):
        """Load events from local JSON file (with optional decryption)."""
        file_path = self.local_storage_path / CALENDAR_FILENAME
        
        if not file_path.exists():
            logger.info("📅 No existing calendar file, starting fresh")
            return
        
        try:
            with open(file_path, "rb" if self._cipher_suite else "r", encoding=None if self._cipher_suite else "utf-8") as f:
                file_content = f.read()
            
            # Decrypt if encryption enabled
            if self._cipher_suite:
                try:
                    decrypted = self._cipher_suite.decrypt(file_content)
                    data = json.loads(decrypted.decode("utf-8"))
                    logger.debug("🔓 Decrypted calendar data")
                except Exception as e:
                    logger.error(f"❌ Failed to decrypt calendar: {e}")
                    return
            else:
                data = json.loads(file_content) if isinstance(file_content, bytes) else file_content
            
            events_data = data.get("events", [])
            for event_dict in events_data:
                try:
                    event = CalendarEvent.from_dict(event_dict)
                    self._events[event.event_id] = event
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load event: {e}")
            
            logger.info(f"📅 Loaded {len(self._events)} events from local storage")
            
        except Exception as e:
            logger.error(f"❌ Failed to load calendar from local storage: {e}")

    def _save_to_local_storage(self):
        """Save all events to local JSON file (with optional encryption)."""
        file_path = self.local_storage_path / CALENDAR_FILENAME
        
        try:
            data = {
                "events": [event.to_dict() for event in self._events.values()],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            
            # Serialize to JSON
            json_str = json.dumps(data, indent=2, ensure_ascii=False)
            
            # Encrypt if encryption enabled
            if self._cipher_suite:
                try:
                    encrypted = self._cipher_suite.encrypt(json_str.encode("utf-8"))
                    with open(file_path, "wb") as f:
                        f.write(encrypted)
                    logger.debug(f"🔒 Encrypted and saved {len(self._events)} events")
                except Exception as e:
                    logger.error(f"❌ Failed to encrypt calendar: {e}")
                    return
            else:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(json_str)
                logger.debug(f"📅 Saved {len(self._events)} events to local storage")
            
        except Exception as e:
            logger.error(f"❌ Failed to save calendar to local storage: {e}")

    def has_duplicate_event(
        self,
        user_id: str,
        chat_id: str,
        title: str,
        event_date: date,
    ) -> bool:
        """
        Check if a duplicate event already exists.
        
        An event is considered a duplicate if:
        - Same user_id
        - Same chat_id
        - Same title (case-insensitive, trimmed)
        - Same event_date
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID
            title: Event title
            event_date: Event date
            
        Returns:
            True if duplicate exists
        """
        title_normalized = title.strip().lower()
        
        for event in self._events.values():
            if (
                event.user_id == user_id
                and event.chat_id == chat_id
                and event.title.strip().lower() == title_normalized
                and event.event_date == event_date
            ):
                return True
        
        return False

    def add_event(
        self,
        user_id: str,
        chat_id: str,
        title: str,
        event_date: date,
        description: str = "",
        reminder_days: Optional[List[int]] = None,
        is_friend: bool = False,
        notification_target_user_id: Optional[str] = None,
        skip_duplicate_check: bool = False,
    ) -> CalendarEvent:
        """
        Add a new calendar event.
        
        Args:
            user_id: LINE user ID
            chat_id: Chat ID (group/room/user)
            title: Event title
            event_date: Event date
            description: Event description
            reminder_days: Days before to remind
            is_friend: Whether user is LINE friend
            skip_duplicate_check: If True, bypass duplicate detection (use with caution)
            
        Returns:
            Created CalendarEvent
            
        Raises:
            ValueError: If event is invalid or duplicate exists
        """
        # Check for duplicates first (before validation to save processing)
        if not skip_duplicate_check:
            if self.has_duplicate_event(user_id, chat_id, title, event_date):
                raise ValueError(
                    f"Duplicate event: '{title}' on {event_date.isoformat()} already exists"
                )
        
        # Validate and sanitize inputs (defense-in-depth)
        is_valid, sanitized, error = calendar_validator.validate_event(
            title=title,
            event_date=event_date,
            description=description,
            reminder_days=reminder_days,
        )
        if not is_valid or not sanitized:
            raise ValueError(error or "Invalid calendar event")

        event = CalendarEvent(
            event_id=str(uuid.uuid4()),
            user_id=user_id,
            chat_id=chat_id,
            title=sanitized["title"],
            event_date=sanitized["event_date"],
            description=sanitized["description"],
            reminder_days=sanitized["reminder_days"],
            is_friend=is_friend,
            notification_target_user_id=notification_target_user_id,
        )
        
        self._events[event.event_id] = event
        self._save_to_local_storage()
        
        # Audit log: event creation (best-effort, non-blocking)
        history_log = get_history_log()
        if history_log:
            _schedule_audit_log(
                history_log.log(
                    event_type=EventType.CALENDAR_EVENT_CREATED,
                    message=f"Created event '{event.title}' on {event.event_date}",
                    level=LogLevel.INFO,
                    chat_id=chat_id,
                    user_id=user_id,
                    agent_name="CalendarService",
                    metadata={
                        "event_id": event.event_id,
                        "title": event.title,
                        "event_date": event.event_date.isoformat(),
                        "reminder_days": event.reminder_days,
                    },
                )
            )
        
        logger.info(f"📅 Added event '{event.title}' for {user_id} on {event.event_date}")
        return event

    def get_event(self, event_id: str) -> Optional[CalendarEvent]:
        """Get event by ID."""
        return self._events.get(event_id)

    def get_user_events(
        self, 
        user_id: str, 
        include_past: bool = False
    ) -> List[CalendarEvent]:
        """
        Get all events for a specific user.
        
        Args:
            user_id: LINE user ID
            include_past: Whether to include past events
            
        Returns:
            List of user's events sorted by date
        """
        events = [
            event for event in self._events.values()
            if event.user_id == user_id and (include_past or not event.is_past())
        ]
        return sorted(events, key=lambda e: e.event_date)

    def get_chat_events(
        self, 
        chat_id: str, 
        include_past: bool = False,
        requesting_user_id: Optional[str] = None
    ) -> List[CalendarEvent]:
        """
        Get all events for a specific chat (group/room/DM).
        
        Args:
            chat_id: Chat ID
            include_past: Whether to include past events
            requesting_user_id: User ID making the request (for audit logging)
            
        Returns:
            List of chat's events sorted by date
        """
        events = [
            event for event in self._events.values()
            if event.chat_id == chat_id and (include_past or not event.is_past())
        ]
        
        # Audit log: event viewing (best-effort)
        if requesting_user_id:
            history_log = get_history_log()
            if history_log:
                _schedule_audit_log(
                    history_log.log(
                        event_type=EventType.CALENDAR_EVENT_VIEWED,
                        message=f"Viewed {len(events)} events in chat",
                        level=LogLevel.DEBUG,
                        chat_id=chat_id,
                        user_id=requesting_user_id,
                        agent_name="CalendarService",
                        metadata={"event_count": len(events), "include_past": include_past},
                    )
                )
        
        return sorted(events, key=lambda e: e.event_date)

    def get_events_needing_reminder(self, days_before: int) -> List[CalendarEvent]:
        """
        Get all events that need a reminder for the given days_before.
        
        Args:
            days_before: Days before event (0 = day-of)
            
        Returns:
            List of events needing reminders
        """
        today = date.today()
        target_date = today + timedelta(days=days_before)
        
        return [
            event for event in self._events.values()
            if event.event_date == target_date and event.needs_reminder(days_before)
        ]

    def mark_event_notified(self, event_id: str, days_before: int) -> bool:
        """
        Mark that a reminder was sent for an event.
        
        Args:
            event_id: Event ID
            days_before: Days before value that was notified
            
        Returns:
            True if successful
        """
        event = self._events.get(event_id)
        if not event:
            return False
        
        event.mark_notified(days_before)
        self._save_to_local_storage()
        return True

    def remove_event(self, event_id: str, user_id: Optional[str] = None) -> bool:
        """
        Remove an event.
        
        Args:
            event_id: Event ID to remove
            user_id: Optional user ID for ownership verification
            
        Returns:
            True if event was removed
        """
        event = self._events.get(event_id)
        if not event:
            return False
        
        # Verify ownership if user_id provided
        if user_id and event.user_id != user_id:
            logger.warning(f"⚠️ User {user_id} tried to remove event owned by {event.user_id}")
            return False
        
        del self._events[event_id]
        self._save_to_local_storage()
        
        # Audit log: event deletion (best-effort, non-blocking)
        history_log = get_history_log()
        if history_log:
            _schedule_audit_log(
                history_log.log(
                    event_type=EventType.CALENDAR_EVENT_DELETED,
                    message=f"Deleted event '{event.title}'",
                    level=LogLevel.INFO,
                    chat_id=event.chat_id,
                    user_id=user_id or "system",
                    agent_name="CalendarService",
                    metadata={
                        "event_id": event_id,
                        "title": event.title,
                        "event_date": event.event_date.isoformat(),
                    },
                )
            )
        
        logger.info(f"📅 Removed event '{event.title}' ({event_id})")
        return True

    def remove_events_by_ids(
        self, 
        event_ids: List[str], 
        user_id: str
    ) -> Tuple[int, int]:
        """
        Remove multiple events by IDs (for multi-select removal).
        
        Args:
            event_ids: List of event IDs to remove
            user_id: User ID for ownership verification
            
        Returns:
            Tuple of (removed_count, failed_count)
        """
        removed = 0
        failed = 0
        
        for event_id in event_ids:
            if self.remove_event(event_id, user_id):
                removed += 1
            else:
                failed += 1
        
        return removed, failed

    def cleanup_past_events(self, days_to_keep: int = 30) -> int:
        """
        Remove events older than specified days.
        
        Args:
            days_to_keep: Keep events up to this many days in the past
            
        Returns:
            Number of events removed
        """
        cutoff_date = date.today() - timedelta(days=days_to_keep)
        
        to_remove = [
            event_id for event_id, event in self._events.items()
            if event.event_date < cutoff_date
        ]
        
        for event_id in to_remove:
            del self._events[event_id]
        
        if to_remove:
            self._save_to_local_storage()
            logger.info(f"📅 Cleaned up {len(to_remove)} old events")
        
        return len(to_remove)

    def get_all_events(self, include_past: bool = False) -> List[CalendarEvent]:
        """Get all events (for admin purposes)."""
        events = [
            event for event in self._events.values()
            if include_past or not event.is_past()
        ]
        return sorted(events, key=lambda e: e.event_date)

    def stop(self):
        """Stop the service and ensure data is saved."""
        self._save_to_local_storage()
        if self._commit_scheduler:
            # CommitScheduler handles its own cleanup
            pass
        logger.info("📅 Calendar service stopped")

    def configure(
        self,
        storage_path: Optional[str] = None,
        hf_token: Optional[str] = None,
        hf_repo_id: Optional[str] = None,
        sync_interval_seconds: int = 300,
    ) -> None:
        """
        Configure the calendar service after instantiation.
        
        This allows the singleton to be reconfigured during app startup.
        
        Args:
            storage_path: Local directory for event storage
            hf_token: Hugging Face API token for persistent storage
            hf_repo_id: HF dataset repo ID (e.g., "username/zeus-calendar")
            sync_interval_seconds: Interval for HF Hub sync (default: 5 minutes)
        """
        # Update storage path if provided
        if storage_path:
            self.local_storage_path = Path(storage_path)
            self.local_storage_path.mkdir(parents=True, exist_ok=True)
        
        # Update HF Hub configuration
        if hf_token and hf_repo_id:
            self.hf_token = hf_token
            self.hf_repo_id = hf_repo_id
            self._hf_enabled = True
            self._setup_hf_storage()
            logger.info(f"📅 Calendar service configured with HF Hub: {hf_repo_id}")
        else:
            # Only reload from local if NOT using HF Hub
            self._load_from_local_storage()
            self._hf_enabled = False
            logger.info("📅 Calendar service configured (local storage only)")


# Tuple import for type hint
from typing import Tuple

# Singleton instance - will be initialized in main.py
_calendar_service: Optional[CalendarService] = None


def init_calendar_service(
    hf_token: Optional[str] = None,
    hf_repo_id: Optional[str] = None,
) -> CalendarService:
    """
    Initialize the global calendar service instance.
    
    Args:
        hf_token: HF API token
        hf_repo_id: HF dataset repo ID
        
    Returns:
        Initialized CalendarService
    """
    global _calendar_service
    _calendar_service = CalendarService(
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
        local_storage_path=settings.calendar_data_path,
        encryption_key=settings.calendar_encryption_key,
    )
    return _calendar_service


def get_calendar_service() -> Optional[CalendarService]:
    """Get the global calendar service instance."""
    return _calendar_service


# Singleton instance - used by main.py and other modules
# Starts unconfigured; call calendar_service.configure() to set up HF Hub sync
calendar_service = CalendarService(
    local_storage_path=settings.calendar_data_path,
    encryption_key=settings.calendar_encryption_key,
)
