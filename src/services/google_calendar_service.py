"""
Google Calendar Service - Full integration with Google Calendar API.

Features:
- OAuth 2.0 authentication
- Create, read, update, delete events
- Native Google Calendar reminders
- Natural language date parsing via quickAdd
- Timezone handling (Bangkok)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

# Try to import Google libraries
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError

    GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    GOOGLE_LIBS_AVAILABLE = False
    logger.warning("⚠️ Google Calendar libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib")


# Scopes required for calendar access
SCOPES = ["https://www.googleapis.com/auth/calendar"]


class GoogleCalendarEvent:
    """Represents a Google Calendar event."""

    def __init__(
        self,
        id: str,
        title: str,
        start: datetime,
        end: datetime | None = None,
        description: str = "",
        reminders: list[int] | None = None,
        link: str = "",
        creator: str = "",
    ):
        self.id = id
        self.title = title
        self.start = start
        self.end = end or start + timedelta(hours=1)
        self.description = description
        self.reminders = reminders or []
        self.link = link
        self.creator = creator

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "title": self.title,
            "start": self.start.isoformat(),
            "end": self.end.isoformat() if self.end else None,
            "description": self.description,
            "reminders": self.reminders,
            "link": self.link,
            "creator": self.creator,
        }

    @classmethod
    def from_google_event(cls, event: dict) -> "GoogleCalendarEvent":
        """Create from Google Calendar API response."""
        # Parse start time
        start_data = event.get("start", {})
        if "dateTime" in start_data:
            start = datetime.fromisoformat(start_data["dateTime"].replace("Z", "+00:00"))
        elif "date" in start_data:
            # All-day event
            start = datetime.strptime(start_data["date"], "%Y-%m-%d").replace(tzinfo=BANGKOK_TZ)
        else:
            start = datetime.now(BANGKOK_TZ)

        # Parse end time
        end_data = event.get("end", {})
        if "dateTime" in end_data:
            end = datetime.fromisoformat(end_data["dateTime"].replace("Z", "+00:00"))
        elif "date" in end_data:
            end = datetime.strptime(end_data["date"], "%Y-%m-%d").replace(tzinfo=BANGKOK_TZ)
        else:
            end = start + timedelta(hours=1)

        # Extract reminders
        reminders = []
        reminder_data = event.get("reminders", {})
        if not reminder_data.get("useDefault", True):
            overrides = reminder_data.get("overrides", [])
            for r in overrides:
                if r.get("method") == "popup":
                    reminders.append(r.get("minutes", 0))

        return cls(
            id=event.get("id", ""),
            title=event.get("summary", "Untitled Event"),
            start=start,
            end=end,
            description=event.get("description", ""),
            reminders=reminders,
            link=event.get("htmlLink", ""),
            creator=event.get("creator", {}).get("email", ""),
        )


class GoogleCalendarService:
    """Service for interacting with Google Calendar API."""

    def __init__(self):
        self._credentials: Credentials | None = None
        self._service = None
        self._credentials_path: Path | None = None
        self._token_path: Path | None = None
        self._calendar_id = "primary"  # Use primary calendar by default
        self._initialized = False

    def configure(
        self,
        credentials_path: str = "data/google_credentials.json",
        token_path: str = "data/google_token.json",
        calendar_id: str = "primary",
    ) -> bool:
        """
        Configure the Google Calendar service.

        Args:
            credentials_path: Path to OAuth client credentials JSON
            token_path: Path to store/load OAuth token
            calendar_id: Google Calendar ID (default: 'primary')

        Returns:
            True if configured successfully
        """
        if not GOOGLE_LIBS_AVAILABLE:
            logger.error("❌ Google Calendar libraries not available")
            return False

        self._credentials_path = Path(credentials_path)
        self._token_path = Path(token_path)
        self._calendar_id = calendar_id

        # Ensure data directory exists
        self._token_path.parent.mkdir(parents=True, exist_ok=True)

        # Try to load existing credentials
        if self._load_credentials():
            self._build_service()
            self._initialized = True
            logger.info("✅ Google Calendar service configured with existing token")
            return True

        logger.warning("⚠️ Google Calendar needs authorization. Run: python scripts/setup_google_calendar.py")
        return False

    def _load_credentials(self) -> bool:
        """Load credentials from token file."""
        if not self._token_path or not self._token_path.exists():
            return False

        try:
            self._credentials = Credentials.from_authorized_user_file(str(self._token_path), SCOPES)

            # Refresh if expired
            if self._credentials and self._credentials.expired and self._credentials.refresh_token:
                self._credentials.refresh(Request())
                self._save_credentials()
                logger.info("🔄 Refreshed Google Calendar credentials")

            return self._credentials is not None and self._credentials.valid
        except Exception as e:
            logger.error(f"❌ Failed to load credentials: {e}")
            return False

    def _save_credentials(self) -> None:
        """Save credentials to token file."""
        if self._credentials and self._token_path:
            self._token_path.write_text(self._credentials.to_json())

    def _build_service(self) -> None:
        """Build the Google Calendar service."""
        if self._credentials:
            self._service = build("calendar", "v3", credentials=self._credentials)

    def is_configured(self) -> bool:
        """Check if service is configured and authenticated."""
        return self._initialized and self._service is not None

    def authorize_interactive(self) -> bool:
        """
        Run interactive OAuth flow (for setup script).

        Returns:
            True if authorization successful
        """
        if not GOOGLE_LIBS_AVAILABLE:
            return False

        if not self._credentials_path or not self._credentials_path.exists():
            logger.error(f"❌ Credentials file not found: {self._credentials_path}")
            logger.info("📋 Download from: https://console.cloud.google.com/apis/credentials")
            return False

        try:
            flow = InstalledAppFlow.from_client_secrets_file(str(self._credentials_path), SCOPES)
            self._credentials = flow.run_local_server(port=0)
            self._save_credentials()
            self._build_service()
            self._initialized = True
            logger.info("✅ Google Calendar authorization successful!")
            return True
        except Exception as e:
            logger.error(f"❌ Authorization failed: {e}")
            return False

    async def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime | None = None,
        description: str = "",
        reminder_minutes: list[int] | None = None,
        chat_id: str = "",
    ) -> GoogleCalendarEvent | None:
        """
        Create a new calendar event.

        Args:
            title: Event title/summary
            start: Event start time
            end: Event end time (default: 1 hour after start)
            description: Event description
            reminder_minutes: List of reminder times in minutes before event
            chat_id: LINE chat ID (stored in description for reference)

        Returns:
            Created event or None if failed
        """
        if not self.is_configured():
            logger.error("❌ Google Calendar not configured")
            return None

        # Default end time is 1 hour after start
        if not end:
            end = start + timedelta(hours=1)

        # Ensure timezone
        if start.tzinfo is None:
            start = start.replace(tzinfo=BANGKOK_TZ)
        if end.tzinfo is None:
            end = end.replace(tzinfo=BANGKOK_TZ)

        # Build event body
        event_body = {
            "summary": title,
            "description": f"{description}\n\n[TeacherBOY: {chat_id}]" if chat_id else description,
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": "Asia/Bangkok",
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "Asia/Bangkok",
            },
        }

        # Add reminders
        if reminder_minutes:
            event_body["reminders"] = {
                "useDefault": False,
                "overrides": [{"method": "popup", "minutes": m} for m in reminder_minutes],
            }
        else:
            # Default: 1 day and 1 hour before
            event_body["reminders"] = {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 1440},  # 1 day
                    {"method": "popup", "minutes": 60},  # 1 hour
                ],
            }

        try:
            result = await asyncio.to_thread(
                self._service.events().insert(calendarId=self._calendar_id, body=event_body).execute
            )

            event = GoogleCalendarEvent.from_google_event(result)
            logger.info(f"✅ Created event: {title} on {start.strftime('%Y-%m-%d %H:%M')}")
            return event
        except HttpError as e:
            logger.error(f"❌ Failed to create event: {e}")
            return None

    async def quick_add(self, text: str) -> GoogleCalendarEvent | None:
        """
        Create event using natural language (Google's quickAdd).

        Examples:
            "Meeting tomorrow at 3pm"
            "Dentist appointment next Tuesday 10am"
            "Call mom on Jan 15 at 2pm"

        Args:
            text: Natural language event description

        Returns:
            Created event or None if failed
        """
        if not self.is_configured():
            logger.error("❌ Google Calendar not configured")
            return None

        try:
            result = await asyncio.to_thread(self._service.events().quickAdd(calendarId=self._calendar_id, text=text).execute)

            event = GoogleCalendarEvent.from_google_event(result)
            logger.info(f"✅ Quick add event: {event.title}")
            return event
        except HttpError as e:
            logger.error(f"❌ Failed to quick add event: {e}")
            return None

    async def get_upcoming_events(
        self,
        max_results: int = 10,
        chat_id: str | None = None,
    ) -> list[GoogleCalendarEvent]:
        """
        Get upcoming events.

        Args:
            max_results: Maximum number of events to return
            chat_id: Filter by chat ID (in description)

        Returns:
            List of upcoming events
        """
        if not self.is_configured():
            logger.error("❌ Google Calendar not configured")
            return []

        try:
            now = datetime.now(BANGKOK_TZ).isoformat()

            result = await asyncio.to_thread(
                self._service.events()
                .list(
                    calendarId=self._calendar_id, timeMin=now, maxResults=max_results, singleEvents=True, orderBy="startTime"
                )
                .execute
            )

            events = []
            for item in result.get("items", []):
                event = GoogleCalendarEvent.from_google_event(item)

                # Filter by chat_id if specified
                if chat_id:
                    if f"[TeacherBOY: {chat_id}]" in (event.description or ""):
                        events.append(event)
                else:
                    events.append(event)

            logger.info(f"📅 Retrieved {len(events)} upcoming events")
            return events
        except HttpError as e:
            logger.error(f"❌ Failed to get events: {e}")
            return []

    async def get_events_for_date(self, date: datetime) -> list[GoogleCalendarEvent]:
        """
        Get events for a specific date.

        Args:
            date: Date to get events for

        Returns:
            List of events on that date
        """
        if not self.is_configured():
            return []

        try:
            # Start and end of day
            start_of_day = date.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=BANGKOK_TZ)
            end_of_day = start_of_day + timedelta(days=1)

            result = await asyncio.to_thread(
                self._service.events()
                .list(
                    calendarId=self._calendar_id,
                    timeMin=start_of_day.isoformat(),
                    timeMax=end_of_day.isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute
            )

            events = [GoogleCalendarEvent.from_google_event(item) for item in result.get("items", [])]
            return events
        except HttpError as e:
            logger.error(f"❌ Failed to get events for date: {e}")
            return []

    async def delete_event(self, event_id: str) -> bool:
        """
        Delete an event.

        Args:
            event_id: Google Calendar event ID

        Returns:
            True if deleted successfully
        """
        if not self.is_configured():
            return False

        try:
            await asyncio.to_thread(self._service.events().delete(calendarId=self._calendar_id, eventId=event_id).execute)
            logger.info(f"🗑️ Deleted event: {event_id}")
            return True
        except HttpError as e:
            logger.error(f"❌ Failed to delete event: {e}")
            return False

    async def delete_events(self, event_ids: list[str]) -> int:
        """
        Delete multiple events.

        Args:
            event_ids: List of event IDs to delete

        Returns:
            Number of successfully deleted events
        """
        deleted = 0
        for event_id in event_ids:
            if await self.delete_event(event_id):
                deleted += 1
        return deleted

    async def update_event(
        self,
        event_id: str,
        title: str | None = None,
        start: datetime | None = None,
        end: datetime | None = None,
        description: str | None = None,
        reminder_minutes: list[int] | None = None,
    ) -> GoogleCalendarEvent | None:
        """
        Update an existing event.

        Args:
            event_id: Event ID to update
            title: New title (optional)
            start: New start time (optional)
            end: New end time (optional)
            description: New description (optional)
            reminder_minutes: New reminders (optional)

        Returns:
            Updated event or None if failed
        """
        if not self.is_configured():
            return None

        try:
            # Get existing event
            existing = await asyncio.to_thread(
                self._service.events().get(calendarId=self._calendar_id, eventId=event_id).execute
            )

            # Update fields
            if title:
                existing["summary"] = title
            if description:
                existing["description"] = description
            if start:
                if start.tzinfo is None:
                    start = start.replace(tzinfo=BANGKOK_TZ)
                existing["start"] = {
                    "dateTime": start.isoformat(),
                    "timeZone": "Asia/Bangkok",
                }
            if end:
                if end.tzinfo is None:
                    end = end.replace(tzinfo=BANGKOK_TZ)
                existing["end"] = {
                    "dateTime": end.isoformat(),
                    "timeZone": "Asia/Bangkok",
                }
            if reminder_minutes is not None:
                existing["reminders"] = {
                    "useDefault": False,
                    "overrides": [{"method": "popup", "minutes": m} for m in reminder_minutes],
                }

            result = await asyncio.to_thread(
                self._service.events().update(calendarId=self._calendar_id, eventId=event_id, body=existing).execute
            )

            return GoogleCalendarEvent.from_google_event(result)
        except HttpError as e:
            logger.error(f"❌ Failed to update event: {e}")
            return None


# Singleton instance
google_calendar_service = GoogleCalendarService()
