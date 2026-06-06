"""
Calendar Adapter - Unified interface for calendar storage backends.

This adapter provides a consistent interface for:
- Local JSON storage (original CalendarService)
- Google Calendar API (GoogleCalendarService)

The adapter automatically selects the appropriate backend based on configuration.
"""

import logging
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from src.config import settings

logger = logging.getLogger(__name__)

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class CalendarAdapter:
    """
    Unified calendar adapter that routes to the appropriate backend.

    Usage:
        adapter = CalendarAdapter()
        await adapter.initialize()

        # Create event
        event = await adapter.add_event(
            user_id="U1234",
            chat_id="group_C5678",
            title="Team Meeting",
            event_date=date(2026, 1, 15),
            reminder_days=[7, 1, 0]
        )

        # Get events
        events = await adapter.get_chat_events("group_C5678")
    """

    def __init__(self):
        self._backend: str = "local"  # "local" or "google"
        self._local_service: Any | None = None
        self._google_service: Any | None = None
        self._initialized: bool = False

    async def initialize(self) -> bool:
        """
        Initialize the calendar adapter with the appropriate backend.

        Returns:
            True if initialization successful
        """
        if self._initialized:
            return True

        # Try Google Calendar first if enabled
        if settings.google_calendar_enabled:
            try:
                from src.services.google_calendar_service import google_calendar_service

                configured = google_calendar_service.configure(
                    credentials_path=settings.google_calendar_credentials_file,
                    token_path=settings.google_calendar_token_file,
                    calendar_id=settings.google_calendar_id,
                )

                if configured and google_calendar_service.is_configured():
                    self._google_service = google_calendar_service
                    self._backend = "google"
                    self._initialized = True
                    logger.info("✅ Calendar adapter initialized with Google Calendar backend")
                    return True
                else:
                    logger.warning(
                        "⚠️ Google Calendar enabled but not configured. Run: python scripts/setup_google_calendar.py"
                    )
            except ImportError:
                logger.warning("⚠️ Google Calendar libraries not installed")
            except Exception as e:
                logger.error(f"❌ Failed to initialize Google Calendar: {e}")

        # Fall back to local storage
        try:
            from src.services.calendar_service import CalendarService

            self._local_service = CalendarService()
            self._backend = "local"
            self._initialized = True
            logger.info("📁 Calendar adapter initialized with local storage backend")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to initialize local calendar service: {e}")
            return False

    @property
    def backend(self) -> str:
        """Get the current backend type."""
        return self._backend

    def is_google(self) -> bool:
        """Check if using Google Calendar backend."""
        return self._backend == "google"

    async def add_event(
        self,
        user_id: str,
        chat_id: str,
        title: str,
        event_date: date,
        description: str = "",
        reminder_days: list[int] | None = None,
        is_friend: bool = False,
    ) -> dict[str, Any] | None:
        """
        Add a new calendar event.

        Args:
            user_id: LINE user ID
            chat_id: Chat ID (group/room/user)
            title: Event title
            event_date: Event date
            description: Event description
            reminder_days: Days before to remind (e.g., [7, 3, 1, 0])
            is_friend: Whether user is LINE friend

        Returns:
            Created event dictionary or None if failed
        """
        if not self._initialized:
            await self.initialize()

        # Convert reminder_days to minutes for Google Calendar
        reminder_minutes = None
        if reminder_days:
            # Convert days to minutes: 7 days = 7*24*60 = 10080 minutes
            reminder_minutes = [d * 24 * 60 if d > 0 else 60 for d in reminder_days]

        if self._backend == "google" and self._google_service:
            try:
                # Create datetime from date (set to 9 AM Bangkok time)
                start_dt = datetime.combine(event_date, datetime.min.time().replace(hour=9))
                start_dt = start_dt.replace(tzinfo=BANGKOK_TZ)

                event = await self._google_service.create_event(
                    title=title,
                    start=start_dt,
                    description=description,
                    reminder_minutes=reminder_minutes,
                    chat_id=chat_id,
                )

                if event:
                    return {
                        "event_id": event.id,
                        "user_id": user_id,
                        "chat_id": chat_id,
                        "title": event.title,
                        "event_date": event_date.isoformat(),
                        "description": description,
                        "reminder_days": reminder_days or [7, 1, 0],
                        "google_link": event.link,
                        "backend": "google",
                    }
            except Exception as e:
                logger.error(f"❌ Google Calendar add_event failed: {e}")
                # Don't fall back - if Google is configured, it should work
                return None

        # Local storage
        if self._local_service:
            try:
                event = self._local_service.add_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    title=title,
                    event_date=event_date,
                    description=description,
                    reminder_days=reminder_days,
                    is_friend=is_friend,
                )
                return event.to_dict() if event else None
            except Exception as e:
                logger.error(f"❌ Local calendar add_event failed: {e}")
                return None

        return None

    async def get_chat_events(
        self,
        chat_id: str,
        include_past: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get all events for a specific chat.

        Args:
            chat_id: Chat ID
            include_past: Whether to include past events

        Returns:
            List of event dictionaries
        """
        if not self._initialized:
            await self.initialize()

        if self._backend == "google" and self._google_service:
            try:
                events = await self._google_service.get_upcoming_events(
                    max_results=50,
                    chat_id=chat_id,  # Filter by chat_id in description
                )

                return [
                    {
                        "event_id": e.id,
                        "title": e.title,
                        "event_date": e.start.date().isoformat() if e.start else None,
                        "description": e.description,
                        "google_link": e.link,
                        "backend": "google",
                    }
                    for e in events
                ]
            except Exception as e:
                logger.error(f"❌ Google Calendar get_chat_events failed: {e}")
                return []

        # Local storage
        if self._local_service:
            try:
                events = self._local_service.get_chat_events(chat_id, include_past)
                return [e.to_dict() for e in events]
            except Exception as e:
                logger.error(f"❌ Local calendar get_chat_events failed: {e}")
                return []

        return []

    async def get_user_events(
        self,
        user_id: str,
        include_past: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Get all events for a specific user.

        Args:
            user_id: LINE user ID
            include_past: Whether to include past events

        Returns:
            List of event dictionaries
        """
        if not self._initialized:
            await self.initialize()

        # Google Calendar doesn't filter by user_id easily
        # For now, return all events (they're all user's events on their calendar)
        if self._backend == "google" and self._google_service:
            try:
                events = await self._google_service.get_upcoming_events(max_results=50)
                return [
                    {
                        "event_id": e.id,
                        "title": e.title,
                        "event_date": e.start.date().isoformat() if e.start else None,
                        "description": e.description,
                        "google_link": e.link,
                        "backend": "google",
                    }
                    for e in events
                ]
            except Exception as e:
                logger.error(f"❌ Google Calendar get_user_events failed: {e}")
                return []

        # Local storage
        if self._local_service:
            try:
                events = self._local_service.get_user_events(user_id, include_past)
                return [e.to_dict() for e in events]
            except Exception as e:
                logger.error(f"❌ Local calendar get_user_events failed: {e}")
                return []

        return []

    async def remove_event(
        self,
        event_id: str,
        user_id: str | None = None,
    ) -> bool:
        """
        Remove a calendar event.

        Args:
            event_id: Event ID to remove
            user_id: User ID for authorization (local only)

        Returns:
            True if removed successfully
        """
        if not self._initialized:
            await self.initialize()

        if self._backend == "google" and self._google_service:
            try:
                return await self._google_service.delete_event(event_id)
            except Exception as e:
                logger.error(f"❌ Google Calendar remove_event failed: {e}")
                return False

        # Local storage
        if self._local_service:
            try:
                return self._local_service.remove_event(event_id, user_id)
            except Exception as e:
                logger.error(f"❌ Local calendar remove_event failed: {e}")
                return False

        return False

    async def remove_events_by_ids(
        self,
        event_ids: list[str],
        user_id: str | None = None,
    ) -> tuple[int, int]:
        """
        Remove multiple events by their IDs.

        Args:
            event_ids: List of event IDs to remove
            user_id: User ID for authorization

        Returns:
            Tuple of (removed_count, failed_count)
        """
        if not self._initialized:
            await self.initialize()

        if self._backend == "google" and self._google_service:
            try:
                deleted = await self._google_service.delete_events(event_ids)
                return deleted, len(event_ids) - deleted
            except Exception as e:
                logger.error(f"❌ Google Calendar remove_events_by_ids failed: {e}")
                return 0, len(event_ids)

        # Local storage
        if self._local_service:
            try:
                return self._local_service.remove_events_by_ids(event_ids, user_id)
            except Exception as e:
                logger.error(f"❌ Local calendar remove_events_by_ids failed: {e}")
                return 0, len(event_ids)

        return 0, len(event_ids)

    async def quick_add(self, text: str) -> dict[str, Any] | None:
        """
        Add event using natural language (Google Calendar quickAdd).

        Only works with Google Calendar backend.

        Args:
            text: Natural language event description
                  e.g., "Meeting tomorrow at 3pm"

        Returns:
            Created event dictionary or None
        """
        if not self._initialized:
            await self.initialize()

        if self._backend == "google" and self._google_service:
            try:
                event = await self._google_service.quick_add(text)
                if event:
                    return {
                        "event_id": event.id,
                        "title": event.title,
                        "event_date": event.start.date().isoformat() if event.start else None,
                        "google_link": event.link,
                        "backend": "google",
                    }
            except Exception as e:
                logger.error(f"❌ Google Calendar quick_add failed: {e}")
                return None

        # Not available for local storage
        logger.warning("⚠️ quick_add only available with Google Calendar")
        return None


# Singleton instance
calendar_adapter = CalendarAdapter()
