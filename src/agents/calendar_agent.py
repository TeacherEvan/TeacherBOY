"""Calendar agent - Handles scheduled Google Calendar reminders."""

import logging
import os
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    PushMessageRequest,
    FlexMessage,
    FlexContainer,
)

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)

# Scopes for Google Calendar API
SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

# Optional Google Calendar imports (handle gracefully if not installed)
try:
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    GOOGLE_CALENDAR_AVAILABLE = True
except ImportError:
    GOOGLE_CALENDAR_AVAILABLE = False
    Request = None  # type: ignore
    Credentials = None  # type: ignore
    InstalledAppFlow = None  # type: ignore
    build = None  # type: ignore
    HttpError = Exception  # type: ignore
    logger.warning("⚠️  Google Calendar API libraries not installed. Run: pip install google-api-python-client google-auth-oauthlib")


class CalendarAgent(BaseAgent):
    """Agent for scheduled Google Calendar reminders."""
    
    def __init__(self, group_chat_id: Optional[str] = None):
        """
        Initialize CalendarAgent.
        
        Args:
            group_chat_id: The LINE group chat ID to send reminders to
        """
        super().__init__(
            name="CalendarAgent",
            description="Scheduled Google Calendar reminders at 07:00 and 14:00"
        )
        self.group_chat_id = group_chat_id
        self.calendar_service = None
        self._initialize_calendar_service()
    
    def get_priority(self) -> int:
        """Calendar agent has lower priority than translation (doesn't handle user messages)."""
        return 20
    
    def _initialize_calendar_service(self):
        """Initialize Google Calendar service with OAuth2 credentials."""
        if not GOOGLE_CALENDAR_AVAILABLE:
            logger.warning("⚠️  Google Calendar libraries not available")
            return
            
        try:
            creds = None
            # Look for credentials in project root
            base_path = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            token_path = os.path.join(base_path, "token.json")
            credentials_path = os.path.join(base_path, "credentials.json")
            
            # Load credentials from token.json if it exists
            if os.path.exists(token_path):
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
            # If no valid credentials, try to refresh or get new ones
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                elif os.path.exists(credentials_path):
                    flow = InstalledAppFlow.from_client_secrets_file(
                        credentials_path, SCOPES
                    )
                    # For headless environments, use console flow
                    creds = flow.run_local_server(port=0)
                else:
                    logger.warning(
                        f"⚠️  Google Calendar credentials.json not found at {credentials_path}. "
                        "Calendar agent will not be able to fetch events."
                    )
                    return
                
                # Save credentials for next run
                with open(token_path, "w") as token:
                    token.write(creds.to_json())
            
            # Build the service
            self.calendar_service = build("calendar", "v3", credentials=creds)
            logger.info("✅ Google Calendar service initialized successfully")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize Google Calendar service: {e}")
            self.calendar_service = None
    
    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Calendar agent doesn't handle user messages directly.
        It only sends scheduled messages.
        """
        return False
    
    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """
        This agent doesn't handle direct messages.
        Use send_daily_reminder() and send_weekly_overview() instead.
        """
        return False
    
    async def _get_events_for_date(self, target_date: datetime) -> List[Dict[str, Any]]:
        """
        Fetch events from Google Calendar for a specific date.
        
        Args:
            target_date: The date to fetch events for
            
        Returns:
            List of event dictionaries
        """
        if not self.calendar_service:
            logger.warning("⚠️  Calendar service not initialized")
            return []
        
        try:
            # Set time range for the target date (start of day to end of day)
            time_min = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
            time_max = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            
            # Call the Calendar API
            events_result = (
                self.calendar_service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min.isoformat() + "Z",
                    timeMax=time_max.isoformat() + "Z",
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            
            events = events_result.get("items", [])
            logger.info(f"📅 Found {len(events)} events for {target_date.date()}")
            return events
            
        except HttpError as error:
            logger.error(f"❌ Google Calendar API error: {error}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching calendar events: {e}")
            return []
    
    async def _get_events_for_week(self) -> List[Dict[str, Any]]:
        """
        Fetch events from Google Calendar for the current week.
        
        Returns:
            List of event dictionaries
        """
        if not self.calendar_service:
            logger.warning("⚠️  Calendar service not initialized")
            return []
        
        try:
            # Get events from today to 7 days ahead
            now = datetime.now()
            time_max = now + timedelta(days=7)
            
            # Call the Calendar API
            events_result = (
                self.calendar_service.events()
                .list(
                    calendarId="primary",
                    timeMin=now.isoformat() + "Z",
                    timeMax=time_max.isoformat() + "Z",
                    maxResults=50,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            
            events = events_result.get("items", [])
            logger.info(f"📅 Found {len(events)} events for the upcoming week")
            return events
            
        except HttpError as error:
            logger.error(f"❌ Google Calendar API error: {error}")
            return []
        except Exception as e:
            logger.error(f"❌ Error fetching calendar events: {e}")
            return []
    
    def _format_event_time(self, event: Dict[str, Any]) -> str:
        """Format event time for display."""
        start = event.get("start", {})
        
        # Handle all-day events
        if "date" in start:
            return "All day"
        
        # Handle timed events
        if "dateTime" in start:
            try:
                dt = datetime.fromisoformat(start["dateTime"].replace("Z", "+00:00"))
                return dt.strftime("%I:%M %p")
            except Exception:
                return "Time TBA"
        
        return "Time TBA"
    
    def _create_daily_reminder_flex(self, events: List[Dict[str, Any]]) -> FlexMessage:
        """Create a Flex Message for daily reminder using dict format."""
        # Build event items
        event_contents = []
        
        if not events:
            event_contents.append({
                "type": "text",
                "text": "Nothing due today. 🎉",
                "size": "md",
                "color": "#999999",
                "wrap": True
            })
        else:
            for i, event in enumerate(events):
                summary = event.get("summary", "Untitled Event")
                time_str = self._format_event_time(event)
                
                event_contents.append({
                    "type": "box",
                    "layout": "vertical",
                    "margin": "md",
                    "spacing": "sm",
                    "contents": [
                        {
                            "type": "text",
                            "text": f"• {summary}",
                            "size": "md",
                            "color": "#333333",
                            "weight": "bold",
                            "wrap": True
                        },
                        {
                            "type": "text",
                            "text": f"  {time_str}",
                            "size": "sm",
                            "color": "#999999"
                        }
                    ]
                })
                
                # Add separator between events
                if i < len(events) - 1:
                    event_contents.append({
                        "type": "separator",
                        "margin": "md"
                    })
        
        flex_dict = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📅 Today's Schedule",
                        "size": "xl",
                        "weight": "bold",
                        "color": "#ffffff"
                    },
                    {
                        "type": "text",
                        "text": datetime.now().strftime("%A, %B %d, %Y"),
                        "size": "sm",
                        "color": "#ffffff"
                    }
                ],
                "backgroundColor": "#0066FF",
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": event_contents,
                "spacing": "md",
                "paddingAll": "20px"
            }
        }
        
        return FlexMessage(
            altText="Today's Schedule",
            contents=FlexContainer.from_dict(flex_dict)
        )
    
    def _create_weekly_overview_flex(self, events: List[Dict[str, Any]]) -> FlexMessage:
        """Create a Flex Message for weekly overview using dict format."""
        # Group events by date
        events_by_date: Dict[str, List[Dict[str, Any]]] = {}
        
        for event in events:
            start = event.get("start", {})
            date_str = start.get("date") or start.get("dateTime", "")[:10]
            
            if date_str not in events_by_date:
                events_by_date[date_str] = []
            events_by_date[date_str].append(event)
        
        # Build day sections
        day_contents = []
        
        if not events:
            day_contents.append({
                "type": "text",
                "text": "Nothing due this week. 🎉",
                "size": "md",
                "color": "#999999",
                "wrap": True
            })
        else:
            sorted_dates = sorted(events_by_date.keys())
            for i, date_str in enumerate(sorted_dates):
                try:
                    date_obj = datetime.fromisoformat(date_str)
                except ValueError:
                    continue
                    
                day_events = events_by_date[date_str]
                
                # Add date header
                day_contents.append({
                    "type": "text",
                    "text": date_obj.strftime("%A, %b %d"),
                    "size": "lg",
                    "weight": "bold",
                    "color": "#0066FF",
                    "margin": "lg" if i > 0 else "none"
                })
                
                # Add events for this day
                for event in day_events:
                    summary = event.get("summary", "Untitled Event")
                    time_str = self._format_event_time(event)
                    
                    day_contents.append({
                        "type": "box",
                        "layout": "vertical",
                        "margin": "sm",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"• {summary}",
                                "size": "md",
                                "color": "#333333",
                                "wrap": True
                            },
                            {
                                "type": "text",
                                "text": f"  {time_str}",
                                "size": "sm",
                                "color": "#999999"
                            }
                        ]
                    })
                
                # Add separator after each day (except last)
                if i < len(sorted_dates) - 1:
                    day_contents.append({
                        "type": "separator",
                        "margin": "lg"
                    })
        
        flex_dict = {
            "type": "bubble",
            "size": "mega",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "📆 Week Overview",
                        "size": "xl",
                        "weight": "bold",
                        "color": "#ffffff"
                    },
                    {
                        "type": "text",
                        "text": "Upcoming events this week",
                        "size": "sm",
                        "color": "#ffffff"
                    }
                ],
                "backgroundColor": "#0066FF",
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": day_contents,
                "spacing": "sm",
                "paddingAll": "20px"
            }
        }
        
        return FlexMessage(
            altText="Week Overview",
            contents=FlexContainer.from_dict(flex_dict)
        )
    
    async def send_daily_reminder(self, line_bot_api: MessagingApi):
        """
        Send daily reminder (triggered at 07:00).
        Checks today's events and sends "Class reports due today" or "Nothing due today".
        """
        if not self.group_chat_id:
            logger.warning("⚠️  Group chat ID not configured for calendar reminders")
            return
        
        if not self.is_enabled():
            logger.info("📴 CalendarAgent is disabled, skipping daily reminder")
            return
        
        try:
            # Get today's events
            today = datetime.now()
            events = await self._get_events_for_date(today)
            
            # Create and send Flex Message
            flex_message = self._create_daily_reminder_flex(events)
            
            line_bot_api.push_message(
                PushMessageRequest(
                    to=self.group_chat_id,
                    messages=[flex_message]
                )
            )
            
            logger.info(f"✅ Daily reminder sent to group {self.group_chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Error sending daily reminder: {e}")
    
    async def send_weekly_overview(self, line_bot_api: MessagingApi):
        """
        Send weekly overview (triggered at 14:00).
        Shows all events happening this week.
        """
        if not self.group_chat_id:
            logger.warning("⚠️  Group chat ID not configured for calendar reminders")
            return
        
        if not self.is_enabled():
            logger.info("📴 CalendarAgent is disabled, skipping weekly overview")
            return
        
        try:
            # Get this week's events
            events = await self._get_events_for_week()
            
            # Create and send Flex Message
            flex_message = self._create_weekly_overview_flex(events)
            
            line_bot_api.push_message(
                PushMessageRequest(
                    to=self.group_chat_id,
                    messages=[flex_message]
                )
            )
            
            logger.info(f"✅ Weekly overview sent to group {self.group_chat_id}")
            
        except Exception as e:
            logger.error(f"❌ Error sending weekly overview: {e}")
