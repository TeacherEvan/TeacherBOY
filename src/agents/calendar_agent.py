"""
Calendar Agent - Handles calendar and reminder commands for Zeus.

Supports:
- Adding events with reminders (multi-step flow)
- Viewing user's events
- Removing events (multi-select)
- Processing dates extracted from images

Triggers:
- "zeus calendar" / "zeus my calendar" / "my events" -> View events
- "zeus add event" / "zeus remind me" / "zeus calendar add" -> Add event
- "zeus remove event" / "zeus delete event" -> Remove events
"""

import asyncio
import logging
import re
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any
from zoneinfo import ZoneInfo

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.messaging.exceptions import ApiException

from .base_agent import BaseAgent
from src.services.calendar_session_manager import (
    calendar_session_manager,
    CalendarState,
)
from src.services.privilege_service import privilege_service
from src.services.message_buffer_service import message_buffer_service
from src.services.date_extraction_service import date_extraction_service
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

# New triggers for scrape and inline add
TRIGGERS_SCRAPE = [
    "zeus scrape",
    "zeus scan",
    "zeus scan messages",
]

# Cancel keywords
CANCEL_KEYWORDS = ["cancel", "nevermind", "never mind", "ยกเลิก", "exit", "quit"]

# Skip keywords for description
SKIP_KEYWORDS = ["skip", "none", "no", "-", "ข้าม"]


class CalendarAgent(BaseAgent):
    """Agent for managing calendar events and reminders."""

    def __init__(self, calendar_service: Optional[Any] = None):
        """
        Initialize CalendarAgent.

        Args:
            calendar_service: CalendarService instance (injected from main.py)
        """
        super().__init__(
            name="CalendarAgent",
            description="Calendar events and reminders management",
        )
        self._calendar_service = calendar_service
        # Cache for friend status
        self._friend_cache: Dict[str, tuple[bool, datetime]] = {}

    def set_calendar_service(self, service: Any) -> None:
        """Set the calendar service (for delayed injection)."""
        self._calendar_service = service

    def get_priority(self) -> int:
        """
        Calendar agent priority.
        
        Priority 6: After admin (5), before profiler (7) and search (8).
        """
        return 6

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
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
        """Check if text matches any trigger."""
        text_lower = text.lower().strip()
        return any(trigger in text_lower for trigger in triggers)

    def _is_cancel_command(self, text: str) -> bool:
        """Check if text is a cancel command."""
        text_lower = text.lower().strip()
        return text_lower in CANCEL_KEYWORDS

    def _is_skip_command(self, text: str) -> bool:
        """Check if text is a skip command."""
        text_lower = text.lower().strip()
        return text_lower in SKIP_KEYWORDS

    async def _is_friend(
        self, 
        event: MessageEvent, 
        line_bot_api: MessagingApi
    ) -> bool:
        """Check if user is a LINE friend."""
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            return False

        # Check cache
        cached = self._friend_cache.get(user_id)
        if cached:
            is_friend, cached_at = cached
            age = (datetime.now() - cached_at).total_seconds()
            if age < 300:  # 5 minute cache
                return is_friend

        try:
            await asyncio.to_thread(line_bot_api.get_profile, user_id)
            self._friend_cache[user_id] = (True, datetime.now())
            return True
        except ApiException:
            self._friend_cache[user_id] = (False, datetime.now())
            return False
        except Exception:
            return False

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Text matches a calendar trigger
        2. Text is "zeus add [date] [title]" inline format
        3. Chat is in an active calendar flow
        """
        # Check for triggers
        if self._is_trigger(text, TRIGGERS_VIEW):
            return True
        if self._is_trigger(text, TRIGGERS_ADD):
            return True
        if self._is_trigger(text, TRIGGERS_REMOVE):
            return True
        if self._is_trigger(text, TRIGGERS_SCRAPE):
            return True
        
        # Check for inline add format: "zeus add [date] [title]"
        if self._parse_inline_add(text):
            return True

        # Check if in active calendar flow
        chat_id = self._get_chat_id(event)
        return calendar_session_manager.is_in_calendar_flow(chat_id)

    def _parse_inline_add(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Parse inline add format: "zeus add [date] [title]"
        
        Examples:
        - "zeus add Jan 15 Birthday party"
        - "zeus add tomorrow Meeting with team"
        - "zeus add 2025-03-20 Conference"
        
        Returns:
            Dict with 'date' and 'title' if parsed successfully, None otherwise
        """
        text_lower = text.lower().strip()
        
        # Check prefix
        if not text_lower.startswith("zeus add "):
            return None
        
        # Don't match the existing triggers
        if self._is_trigger(text, TRIGGERS_ADD):
            return None
        
        # Remove "zeus add " prefix
        remainder = text[9:].strip()  # len("zeus add ") = 9
        
        if not remainder:
            return None
        
        # Try to parse date from the beginning
        # Common date patterns to try
        parsed_date = None
        title_start = 0
        
        # Try relative dates first
        relative_dates = {
            "today": 0,
            "tomorrow": 1,
            "วันนี้": 0,
            "พรุ่งนี้": 1,
        }
        
        remainder_lower = remainder.lower()
        for rel_word, days in relative_dates.items():
            if remainder_lower.startswith(rel_word + " "):
                today = datetime.now(BANGKOK_TZ).date()
                parsed_date = today + timedelta(days=days)
                title_start = len(rel_word) + 1
                break
        
        if not parsed_date:
            # Try "in X days" pattern
            match = re.match(r"in\s+(\d+)\s+days?\s+(.+)", remainder_lower)
            if match:
                days = int(match.group(1))
                today = datetime.now(BANGKOK_TZ).date()
                parsed_date = today + timedelta(days=days)
                title_start = match.start(2)
        
        if not parsed_date:
            # Try common date formats at the start
            date_patterns = [
                # "Jan 15" or "January 15" (assume current/next year)
                (r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,?\s+(\d{4}))?\s+(.+)", "named"),
                # "15/01" or "15/01/2025"
                (r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?\s+(.+)", "slash"),
                # "2025-01-15"
                (r"(\d{4})-(\d{2})-(\d{2})\s+(.+)", "iso"),
            ]
            
            for pattern, fmt in date_patterns:
                match = re.match(pattern, remainder_lower)
                if match:
                    try:
                        if fmt == "named":
                            month_str = match.group(1)[:3]
                            day = int(match.group(2))
                            year = int(match.group(3)) if match.group(3) else datetime.now().year
                            
                            # Map month name to number
                            month_map = {
                                "jan": 1, "feb": 2, "mar": 3, "apr": 4,
                                "may": 5, "jun": 6, "jul": 7, "aug": 8,
                                "sep": 9, "oct": 10, "nov": 11, "dec": 12
                            }
                            month = month_map.get(month_str, 1)
                            
                            # If date would be in past, use next year
                            try:
                                parsed_date = date(year, month, day)
                                if parsed_date < datetime.now(BANGKOK_TZ).date() and not match.group(3):
                                    parsed_date = date(year + 1, month, day)
                            except ValueError:
                                continue
                            
                            # Title is in group 4
                            title = match.group(4).strip()
                            if title:
                                return {
                                    "date": parsed_date,
                                    "title": remainder[match.start(4):].strip()[:100]  # Use original case
                                }
                        
                        elif fmt == "slash":
                            day = int(match.group(1))
                            month = int(match.group(2))
                            year = int(match.group(3)) if match.group(3) else datetime.now().year
                            
                            parsed_date = date(year, month, day)
                            if parsed_date < datetime.now(BANGKOK_TZ).date() and not match.group(3):
                                parsed_date = date(year + 1, month, day)
                            
                            title = match.group(4).strip()
                            if title:
                                return {
                                    "date": parsed_date,
                                    "title": remainder[match.start(4):].strip()[:100]
                                }
                        
                        elif fmt == "iso":
                            year = int(match.group(1))
                            month = int(match.group(2))
                            day = int(match.group(3))
                            parsed_date = date(year, month, day)
                            
                            title = match.group(4).strip()
                            if title:
                                return {
                                    "date": parsed_date,
                                    "title": remainder[match.start(4):].strip()[:100]
                                }
                    except (ValueError, IndexError):
                        continue
                    break
        
        # If we parsed a date with relative word
        if parsed_date and title_start > 0:
            title = remainder[title_start:].strip()
            if title:
                return {
                    "date": parsed_date,
                    "title": title[:100]
                }
        
        return None

    async def handle(
        self, 
        event: MessageEvent, 
        text: str, 
        line_bot_api: MessagingApi
    ) -> bool:
        """Process calendar-related messages."""
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        session = calendar_session_manager.get_session(chat_id)

        with tracer.start_as_current_span("calendar_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)

            try:
                # Check for cancel command first
                if self._is_cancel_command(text):
                    if calendar_session_manager.cancel_flow(chat_id):
                        await self._send_message(
                            event, line_bot_api,
                            "❌ Calendar operation cancelled.\n\nยกเลิกแล้วค่ะ"
                        )
                        return True
                    return False

                # Handle based on trigger or session state
                if self._is_trigger(text, TRIGGERS_VIEW):
                    return await self._handle_view_events(
                        event, text, line_bot_api, chat_id, user_id
                    )

                if self._is_trigger(text, TRIGGERS_ADD):
                    return await self._start_add_flow(
                        event, line_bot_api, chat_id, user_id
                    )

                if self._is_trigger(text, TRIGGERS_REMOVE):
                    return await self._start_remove_flow(
                        event, line_bot_api, chat_id, user_id
                    )

                # Check for scrape trigger
                if self._is_trigger(text, TRIGGERS_SCRAPE):
                    return await self._handle_scrape_trigger(
                        event, line_bot_api, chat_id, user_id
                    )

                # Check for inline add format: "zeus add [date] [title]"
                inline_data = self._parse_inline_add(text)
                if inline_data:
                    return await self._handle_inline_add_trigger(
                        event, line_bot_api, chat_id, user_id, inline_data
                    )

                # Handle ongoing session
                if session:
                    return await self._handle_session_state(
                        event, text, line_bot_api, chat_id, user_id, session
                    )

                return False

            except Exception as e:
                logger.error(f"❌ CalendarAgent error: {e}", exc_info=True)
                calendar_session_manager.end_session(chat_id)
                await self._send_error_message(event, line_bot_api)
                return False

    # =========================================================================
    # View Events
    # =========================================================================

    async def _handle_view_events(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Show user's calendar events."""
        if not self._calendar_service or not user_id:
            await self._send_message(
                event, line_bot_api,
                "❌ Calendar service not available."
            )
            return True

        events = self._calendar_service.get_user_events(user_id)

        if not events:
            await self._send_message(
                event, line_bot_api,
                "📅 You don't have any events yet!\n\n"
                "Say 'zeus add event' to create one.\n\n"
                "คุณยังไม่มีกิจกรรมในปฏิทิน\n"
                "พิมพ์ 'zeus add event' เพื่อเพิ่มกิจกรรม"
            )
            return True

        # Format events list
        msg_lines = [
            f"📅 Your Events ({len(events)})",
            "━" * 20,
            ""
        ]

        today = datetime.now(BANGKOK_TZ).date()
        
        for i, evt in enumerate(events[:10], 1):  # Show max 10
            date_str = evt.event_date.strftime("%b %d, %Y")
            days_until = (evt.event_date - today).days
            
            if days_until < 0:
                time_str = "(past)"
            elif days_until == 0:
                time_str = "(TODAY)"
            elif days_until == 1:
                time_str = "(tomorrow)"
            else:
                time_str = f"(in {days_until} days)"
            
            reminder_str = ", ".join([f"{d}d" for d in sorted(evt.reminder_days, reverse=True)])
            
            msg_lines.append(f"{i}. {evt.title}")
            msg_lines.append(f"   📆 {date_str} {time_str}")
            msg_lines.append(f"   ⏰ Reminders: {reminder_str}")
            msg_lines.append("")

        if len(events) > 10:
            msg_lines.append(f"... and {len(events) - 10} more events")

        msg_lines.append("")
        msg_lines.append("💡 Say 'zeus remove event' to delete events")

        await self._send_message(event, line_bot_api, "\n".join(msg_lines))
        return True

    # =========================================================================
    # Add Event Flow
    # =========================================================================

    async def _start_add_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Start the add event flow."""
        if not user_id:
            await self._send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        # Check if user is friend
        is_friend = await self._is_friend(event, line_bot_api)
        
        # Start session
        calendar_session_manager.start_add_flow(chat_id, user_id, is_friend)

        # Ask for date
        msg = (
            "📅 Let's add a new event!\n\n"
            "Step 1/4: When is the event?\n\n"
            "Enter the date (e.g., Jan 15, 2025 or 15/01/2025)\n\n"
            "พิมพ์วันที่ของกิจกรรม\n"
            "(ตัวอย่าง: 15 ม.ค. 2568 หรือ 15/01/2025)\n\n"
            "💡 Say 'cancel' to stop"
        )
        
        await self._send_message(event, line_bot_api, msg)
        return True

    async def _handle_session_state(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        session: Any
    ) -> bool:
        """Handle ongoing session based on state."""
        state = session.state

        if state == CalendarState.AWAITING_DATE:
            return await self._handle_date_input(
                event, text, line_bot_api, chat_id
            )

        elif state == CalendarState.AWAITING_TITLE:
            return await self._handle_title_input(
                event, text, line_bot_api, chat_id
            )

        elif state == CalendarState.AWAITING_DESCRIPTION:
            return await self._handle_description_input(
                event, text, line_bot_api, chat_id
            )

        elif state == CalendarState.AWAITING_REMINDER_DAYS:
            return await self._handle_reminder_days_input(
                event, text, line_bot_api, chat_id
            )

        elif state == CalendarState.CONFIRMING_ADD:
            return await self._handle_add_confirmation(
                event, text, line_bot_api, chat_id, user_id
            )

        elif state == CalendarState.AWAITING_REMOVAL_SELECTION:
            return await self._handle_removal_selection(
                event, text, line_bot_api, chat_id
            )

        elif state == CalendarState.CONFIRMING_REMOVAL:
            return await self._handle_removal_confirmation(
                event, text, line_bot_api, chat_id
            )

        elif state == CalendarState.PROCESSING_EXTRACTED_DATES:
            return await self._handle_extracted_date_response(
                event, text, line_bot_api, chat_id, user_id
            )

        # New states for scrape flow
        elif state == CalendarState.SCRAPE_REVIEWING:
            return await self._handle_scrape_review_response(
                event, text, line_bot_api, chat_id, user_id
            )

        elif state == CalendarState.SCRAPE_REMINDER_DAYS:
            return await self._handle_scrape_reminder_response(
                event, text, line_bot_api, chat_id, user_id
            )

        # New states for inline add flow
        elif state == CalendarState.INLINE_ADD_REMINDER_DAYS:
            return await self._handle_inline_add_reminder_response(
                event, text, line_bot_api, chat_id, user_id
            )

        elif state == CalendarState.INLINE_ADD_CONFIRMING:
            return await self._handle_inline_add_confirmation(
                event, text, line_bot_api, chat_id, user_id
            )

        return False

    async def _handle_date_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str
    ) -> bool:
        """Handle date input."""
        parsed_date = self._parse_date(text)
        
        if not parsed_date:
            await self._send_message(
                event, line_bot_api,
                "❌ I couldn't understand that date.\n\n"
                "Try formats like:\n"
                "• Jan 15, 2025\n"
                "• 15/01/2025\n"
                "• 2025-01-15\n"
                "• tomorrow\n"
                "• next week\n\n"
                "ไม่เข้าใจวันที่ กรุณาลองอีกครั้ง"
            )
            return True

        # Check if date is in the past
        today = datetime.now(BANGKOK_TZ).date()
        if parsed_date < today:
            await self._send_message(
                event, line_bot_api,
                "❌ That date is in the past!\n\n"
                "Please enter a future date.\n\n"
                "วันที่ที่ระบุผ่านไปแล้ว กรุณาใส่วันที่ในอนาคต"
            )
            return True

        # Update session
        calendar_session_manager.set_pending_date(chat_id, parsed_date)
        
        date_str = parsed_date.strftime("%B %d, %Y")
        msg = (
            f"✅ Date: {date_str}\n\n"
            "Step 2/4: What's the event title?\n\n"
            "Enter a short title (e.g., 'Doctor appointment')\n\n"
            "พิมพ์ชื่อกิจกรรม"
        )
        
        await self._send_message(event, line_bot_api, msg)
        return True

    async def _handle_title_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str
    ) -> bool:
        """Handle title input."""
        title = text.strip()[:100]  # Max 100 chars
        
        if len(title) < 2:
            await self._send_message(
                event, line_bot_api,
                "❌ Title is too short. Please enter at least 2 characters.\n\n"
                "ชื่อสั้นเกินไป กรุณาใส่อย่างน้อย 2 ตัวอักษร"
            )
            return True

        calendar_session_manager.set_pending_title(chat_id, title)
        
        msg = (
            f"✅ Title: {title}\n\n"
            "Step 3/4: Add a description (optional)\n\n"
            "Enter details or say 'skip' to continue.\n\n"
            "ใส่รายละเอียดเพิ่มเติม หรือพิมพ์ 'skip' เพื่อข้าม"
        )
        
        await self._send_message(event, line_bot_api, msg)
        return True

    async def _handle_description_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str
    ) -> bool:
        """Handle description input."""
        description = "" if self._is_skip_command(text) else text.strip()[:500]
        
        calendar_session_manager.set_pending_description(chat_id, description)
        
        # Show reminder options with Quick Reply
        msg = (
            "Step 4/4: When should I remind you?\n\n"
            "Choose reminder timing:\n"
            "• 7 - Remind 7 days before\n"
            "• 3 - Remind 3 days before\n"
            "• 1 - Remind 1 day before\n"
            "• all - All of the above\n\n"
            "เลือกเวลาเตือน:\n"
            "• 7 - เตือนล่วงหน้า 7 วัน\n"
            "• 3 - เตือนล่วงหน้า 3 วัน\n"
            "• 1 - เตือนล่วงหน้า 1 วัน\n"
            "• all - ทั้งหมด\n\n"
            "(Day-of reminder is always included)"
        )
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="7 days", text="7")),
            QuickReplyItem(type="action", action=MessageAction(label="3 days", text="3")),
            QuickReplyItem(type="action", action=MessageAction(label="1 day", text="1")),
            QuickReplyItem(type="action", action=MessageAction(label="All", text="all")),
        ])
        
        await self._send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )
        return True

    async def _handle_reminder_days_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str
    ) -> bool:
        """Handle reminder days selection."""
        text_lower = text.lower().strip()
        
        reminder_days = []
        
        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 0]
        elif text_lower in ["3", "3 days"]:
            reminder_days = [3, 0]
        elif text_lower in ["1", "1 day"]:
            reminder_days = [1, 0]
        else:
            # Try to parse custom input like "7,3,1"
            try:
                parts = re.split(r"[,\s]+", text_lower)
                for part in parts:
                    if part.isdigit():
                        day = int(part)
                        if 0 <= day <= 30:
                            reminder_days.append(day)
            except:
                pass
            
            if not reminder_days:
                await self._send_message(
                    event, line_bot_api,
                    "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                    "กรุณาเลือก 7, 3, 1 หรือ all"
                )
                return True

        # Ensure 0 (day-of) is always included
        if 0 not in reminder_days:
            reminder_days.append(0)
        
        calendar_session_manager.set_pending_reminder_days(chat_id, reminder_days)
        
        # Get full event data for confirmation
        session = calendar_session_manager.get_session(chat_id)
        if not session:
            return False
        
        date_str = session.pending_date.strftime("%B %d, %Y") if session.pending_date else "N/A"
        reminder_str = ", ".join([f"{d} days" if d > 0 else "day-of" for d in sorted(reminder_days, reverse=True)])
        
        msg = (
            "📝 Please confirm your event:\n\n"
            f"📆 Date: {date_str}\n"
            f"📌 Title: {session.pending_title}\n"
            f"📝 Description: {session.pending_description or '(none)'}\n"
            f"⏰ Reminders: {reminder_str}\n\n"
            "Is this correct? (yes/no)\n\n"
            "ข้อมูลถูกต้องไหม? (yes/no)"
        )
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="✅ Yes", text="yes")),
            QuickReplyItem(type="action", action=MessageAction(label="❌ No", text="no")),
        ])
        
        await self._send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )
        return True

    async def _handle_add_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Handle event creation confirmation."""
        text_lower = text.lower().strip()
        
        if text_lower in ["yes", "y", "ใช่", "ok", "confirm"]:
            # Get event data
            event_data = calendar_session_manager.get_pending_event_data(chat_id)
            if not event_data or not self._calendar_service or not user_id:
                await self._send_message(
                    event, line_bot_api,
                    "❌ Something went wrong. Please try again."
                )
                calendar_session_manager.end_session(chat_id)
                return True

            # Create the event
            new_event = self._calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data["description"],
                reminder_days=event_data["reminder_days"],
                is_friend=event_data["is_friend"]
            )
            
            calendar_session_manager.end_session(chat_id)
            
            date_str = new_event.event_date.strftime("%B %d, %Y")
            reminder_str = ", ".join([f"{d}d" for d in sorted(new_event.reminder_days, reverse=True)])
            
            msg = (
                "✅ Event created!\n\n"
                f"📆 {new_event.title}\n"
                f"📅 {date_str}\n"
                f"⏰ Reminders: {reminder_str}\n\n"
                "I'll remind you at 8 AM Bangkok time.\n\n"
                "เพิ่มกิจกรรมเรียบร้อยแล้ว! จะเตือนตอน 8 โมงเช้าค่ะ"
            )
            
            await self._send_message(event, line_bot_api, msg)
            return True
            
        elif text_lower in ["no", "n", "ไม่"]:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "❌ Event creation cancelled.\n\n"
                "Say 'zeus add event' to try again.\n\n"
                "ยกเลิกแล้ว พิมพ์ 'zeus add event' เพื่อลองใหม่"
            )
            return True
        else:
            await self._send_message(
                event, line_bot_api,
                "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no"
            )
            return True

    # =========================================================================
    # Remove Event Flow
    # =========================================================================

    async def _start_remove_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Start the remove event flow."""
        if not self._calendar_service or not user_id:
            await self._send_message(
                event, line_bot_api,
                "❌ Calendar service not available."
            )
            return True

        events = self._calendar_service.get_user_events(user_id)

        if not events:
            await self._send_message(
                event, line_bot_api,
                "📅 You don't have any events to remove.\n\n"
                "คุณไม่มีกิจกรรมที่จะลบ"
            )
            return True

        # Start removal flow with events
        events_data = [
            {
                "event_id": evt.event_id,
                "title": evt.title,
                "date": evt.event_date.strftime("%b %d"),
            }
            for evt in events[:10]  # Max 10 for removal
        ]
        
        calendar_session_manager.start_removal_flow(chat_id, user_id, events_data)

        # Format selection message
        msg_lines = [
            "🗑️ Select events to remove:",
            "",
        ]
        
        for i, evt in enumerate(events_data, 1):
            msg_lines.append(f"{i}. {evt['title']} ({evt['date']})")
        
        msg_lines.extend([
            "",
            "Enter numbers separated by commas (e.g., 1,3,5)",
            "Or say 'all' to remove everything.",
            "",
            "พิมพ์เลขที่ต้องการลบ คั่นด้วยเครื่องหมาย ,",
            "หรือพิมพ์ 'all' เพื่อลบทั้งหมด",
            "",
            "💡 Say 'cancel' to stop"
        ])
        
        await self._send_message(event, line_bot_api, "\n".join(msg_lines))
        return True

    async def _handle_removal_selection(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str
    ) -> bool:
        """Handle event selection for removal."""
        session = calendar_session_manager.get_session(chat_id)
        if not session:
            return False

        events_for_removal = session.events_for_removal
        text_lower = text.lower().strip()
        
        selected_ids = []
        
        if text_lower == "all":
            selected_ids = [e["event_id"] for e in events_for_removal]
        else:
            # Parse numbers
            try:
                parts = re.split(r"[,\s]+", text)
                for part in parts:
                    if part.isdigit():
                        idx = int(part) - 1  # Convert to 0-based
                        if 0 <= idx < len(events_for_removal):
                            selected_ids.append(events_for_removal[idx]["event_id"])
            except:
                pass
            
            if not selected_ids:
                await self._send_message(
                    event, line_bot_api,
                    "❌ Invalid selection. Enter numbers (e.g., 1,3) or 'all'.\n\n"
                    "กรุณาใส่ตัวเลข (เช่น 1,3) หรือ 'all'"
                )
                return True

        calendar_session_manager.set_removal_selection(chat_id, selected_ids)
        
        # Show confirmation
        count = len(selected_ids)
        msg = (
            f"⚠️ Remove {count} event{'s' if count > 1 else ''}?\n\n"
            "This cannot be undone!\n\n"
            "Are you sure? (yes/no)\n\n"
            f"ต้องการลบ {count} กิจกรรม? (yes/no)"
        )
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="✅ Yes, delete", text="yes")),
            QuickReplyItem(type="action", action=MessageAction(label="❌ No, keep", text="no")),
        ])
        
        await self._send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )
        return True

    async def _handle_removal_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str
    ) -> bool:
        """Handle removal confirmation."""
        text_lower = text.lower().strip()
        
        if text_lower in ["yes", "y", "ใช่", "delete", "confirm"]:
            event_ids = calendar_session_manager.get_removal_event_ids(chat_id)
            if not event_ids or not self._calendar_service:
                await self._send_message(
                    event, line_bot_api,
                    "❌ Something went wrong. Please try again."
                )
                calendar_session_manager.end_session(chat_id)
                return True

            # Remove events
            removed_count = self._calendar_service.remove_events_by_ids(event_ids)
            
            calendar_session_manager.end_session(chat_id)
            
            msg = (
                f"✅ Removed {removed_count} event{'s' if removed_count > 1 else ''}!\n\n"
                f"ลบ {removed_count} กิจกรรมเรียบร้อยแล้ว"
            )
            
            await self._send_message(event, line_bot_api, msg)
            return True
            
        elif text_lower in ["no", "n", "ไม่", "keep"]:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "✅ No events were removed.\n\nไม่มีกิจกรรมถูกลบ"
            )
            return True
        else:
            await self._send_message(
                event, line_bot_api,
                "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no"
            )
            return True

    # =========================================================================
    # Image Extraction Flow (for ImageAnalyzerAgent integration)
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
        calendar_session_manager.start_extraction_flow(
            chat_id, user_id, extracted_dates, is_friend
        )
        
        # If event and line_bot_api provided, prompt for first date
        if event and line_bot_api and extracted_dates:
            await self._prompt_extracted_date(
                event, line_bot_api, extracted_dates[0]
            )

    async def _handle_extracted_date_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Handle response during extracted date processing."""
        # This handles "yes/no" for adding extracted dates
        # and reminder day selection
        
        text_lower = text.lower().strip()
        session = calendar_session_manager.get_session(chat_id)
        
        if not session:
            return False

        current_date = calendar_session_manager.get_current_extracted_date(chat_id)
        
        if not current_date:
            calendar_session_manager.end_session(chat_id)
            return False

        # Check if this is a yes/no for adding
        if text_lower in ["yes", "y", "ใช่", "add"]:
            # Move to reminder selection
            msg = (
                "Choose reminder timing:\n"
                "• 7 - 7 days before\n"
                "• 3 - 3 days before\n"
                "• 1 - 1 day before\n"
                "• all - All of the above"
            )
            
            quick_reply = QuickReply(items=[
                QuickReplyItem(type="action", action=MessageAction(label="7 days", text="7")),
                QuickReplyItem(type="action", action=MessageAction(label="3 days", text="3")),
                QuickReplyItem(type="action", action=MessageAction(label="1 day", text="1")),
                QuickReplyItem(type="action", action=MessageAction(label="All", text="all")),
            ])
            
            await self._send_message_with_quick_reply(
                event, line_bot_api, msg, quick_reply
            )
            return True
            
        elif text_lower in ["no", "n", "ไม่", "skip"]:
            # Skip this date, move to next
            has_more = calendar_session_manager.advance_extraction_index(chat_id)
            if has_more:
                next_date = calendar_session_manager.get_current_extracted_date(chat_id)
                if next_date:
                    await self._prompt_extracted_date(
                        event, line_bot_api, next_date
                    )
            else:
                calendar_session_manager.end_session(chat_id)
                await self._send_message(
                    event, line_bot_api,
                    "✅ Finished processing dates.\n\nเสร็จสิ้นการประมวลผลวันที่"
                )
            return True
            
        elif text_lower in ["7", "3", "1", "all"]:
            # Handle reminder selection for extracted date
            if text_lower == "all":
                reminder_days = [7, 3, 1, 0]
            else:
                reminder_days = [int(text_lower), 0]
            
            event_data = calendar_session_manager.set_extraction_reminder_days(
                chat_id, reminder_days
            )
            
            if event_data and self._calendar_service and user_id:
                # Create the event
                self._calendar_service.add_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    title=event_data["title"],
                    event_date=event_data["date"],
                    description=event_data["description"],
                    reminder_days=event_data["reminder_days"],
                    is_friend=event_data["is_friend"]
                )
                
                await self._send_message(
                    event, line_bot_api,
                    f"✅ Added: {event_data['title']}"
                )
            
            # Move to next extracted date
            has_more = calendar_session_manager.advance_extraction_index(chat_id)
            if has_more:
                next_date = calendar_session_manager.get_current_extracted_date(chat_id)
                if next_date:
                    await self._prompt_extracted_date(
                        event, line_bot_api, next_date
                    )
            else:
                calendar_session_manager.end_session(chat_id)
                await self._send_message(
                    event, line_bot_api,
                    "✅ Finished processing all dates!\n\nเพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว"
                )
            return True

        return False

    async def _prompt_extracted_date(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        date_info: Dict[str, Any]
    ) -> None:
        """Prompt user about an extracted date."""
        date_obj = date_info.get("date")
        title = date_info.get("title", "Event")
        description = date_info.get("description", "")
        
        date_str = date_obj.strftime("%B %d, %Y") if date_obj else "Unknown"
        
        msg = (
            f"📅 Found event in image:\n\n"
            f"📌 {title}\n"
            f"📆 {date_str}\n"
        )
        
        if description:
            msg += f"📝 {description}\n"
        
        msg += "\nAdd to calendar? (yes/no)"
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="✅ Yes", text="yes")),
            QuickReplyItem(type="action", action=MessageAction(label="❌ No", text="no")),
        ])
        
        await self._send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )

    # =========================================================================
    # Zeus Scrape Flow - Extract dates from recent chat messages
    # =========================================================================

    async def _handle_scrape_trigger(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """
        Handle "zeus scrape" trigger.
        
        Retrieves recent messages from buffer, extracts dates using AI,
        and guides user through adding events.
        """
        if not user_id:
            await self._send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        # Get recent messages from buffer
        messages = message_buffer_service.get_message_texts(chat_id, limit=10)
        
        if not messages:
            await self._send_message(
                event, line_bot_api,
                "📭 No recent messages found to scan.\n\n"
                "I can only scan messages that arrived while I was active.\n\n"
                "ไม่พบข้อความล่าสุดที่จะสแกน\n"
                "ฉันสามารถสแกนเฉพาะข้อความที่มาถึงขณะที่ฉันทำงานอยู่"
            )
            return True

        # Send processing message
        await self._send_message(
            event, line_bot_api,
            f"🔍 Scanning {len(messages)} recent messages...\n\n"
            f"กำลังสแกน {len(messages)} ข้อความล่าสุด..."
        )

        # Check friendship status
        is_friend = await self._is_friend(event, line_bot_api)

        # Start scrape flow
        calendar_session_manager.start_scrape_flow(
            chat_id, user_id, messages, is_friend
        )

        # Extract dates using AI
        try:
            events = await date_extraction_service.extract_events_from_messages(messages)
        except Exception as e:
            logger.error(f"❌ Date extraction failed: {e}", exc_info=True)
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "❌ Failed to scan messages. Please try again.\n\n"
                "สแกนข้อความไม่สำเร็จ กรุณาลองใหม่"
            )
            return True

        if not events:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "📭 No dates or events found in recent messages.\n\n"
                "ไม่พบวันที่หรือกิจกรรมในข้อความล่าสุด\n\n"
                "💡 Try 'zeus add [date] [title]' to add directly."
            )
            return True

        # Convert ExtractedEvent objects to dicts
        events_data = [
            {
                "date": evt.event_date,
                "title": evt.title,
                "description": evt.description or "",
                "source_text": evt.source_text,
                "confidence": evt.confidence,
            }
            for evt in events
        ]

        # Store extracted events and move to review state
        calendar_session_manager.set_scraped_events(chat_id, events_data)

        # Send summary and prompt for first event
        await self._send_message(
            event, line_bot_api,
            f"✅ Found {len(events_data)} event(s) in messages!\n\n"
            f"พบ {len(events_data)} กิจกรรมในข้อความ!"
        )

        # Prompt for first event
        first_event = calendar_session_manager.get_current_scraped_event(chat_id)
        if first_event:
            await self._prompt_scraped_event(event, line_bot_api, first_event, 1, len(events_data))

        return True

    async def _prompt_scraped_event(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        event_data: Dict[str, Any],
        current: int,
        total: int
    ) -> None:
        """Prompt user about a scraped event."""
        date_obj = event_data.get("date")
        title = event_data.get("title", "Event")
        source = event_data.get("source_text", "")
        confidence = event_data.get("confidence", "medium")
        
        date_str = date_obj.strftime("%B %d, %Y") if date_obj else "Unknown"
        
        msg = (
            f"📅 Event {current}/{total}:\n\n"
            f"📌 {title}\n"
            f"📆 {date_str}\n"
        )
        
        if source:
            # Truncate source text
            source_preview = source[:50] + "..." if len(source) > 50 else source
            msg += f"📝 From: \"{source_preview}\"\n"
        
        msg += f"🎯 Confidence: {confidence}\n\n"
        msg += "Add this to calendar? (yes/no/skip all)"
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="✅ Yes", text="yes")),
            QuickReplyItem(type="action", action=MessageAction(label="⏭️ Skip", text="no")),
            QuickReplyItem(type="action", action=MessageAction(label="🚫 Skip All", text="done")),
        ])
        
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)

    async def _handle_scrape_review_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Handle user response during scrape review."""
        text_lower = text.lower().strip()
        
        if text_lower in ["yes", "y", "ใช่", "ok"]:
            # Accept this event, ask for reminder days
            calendar_session_manager.accept_scraped_event(chat_id)
            
            current_event = calendar_session_manager.get_current_scraped_event(chat_id)
            if current_event:
                msg = (
                    f"✅ Adding: {current_event.get('title', 'Event')}\n\n"
                    "When should I remind you?\n\n"
                    "• 7 - 7 days before\n"
                    "• 3 - 3 days before\n"
                    "• 1 - 1 day before\n"
                    "• all - All of the above\n\n"
                    "(Day-of reminder is always included)"
                )
                
                quick_reply = QuickReply(items=[
                    QuickReplyItem(type="action", action=MessageAction(label="7 days", text="7")),
                    QuickReplyItem(type="action", action=MessageAction(label="3 days", text="3")),
                    QuickReplyItem(type="action", action=MessageAction(label="1 day", text="1")),
                    QuickReplyItem(type="action", action=MessageAction(label="All", text="all")),
                ])
                
                await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
            return True
            
        elif text_lower in ["no", "n", "ไม่", "skip"]:
            # Skip this event, move to next
            has_more = calendar_session_manager.skip_scraped_event(chat_id)
            if has_more:
                next_event = calendar_session_manager.get_current_scraped_event(chat_id)
                if next_event:
                    current, total = calendar_session_manager.get_scrape_progress(chat_id)
                    await self._prompt_scraped_event(
                        event, line_bot_api, next_event, current, total
                    )
            else:
                calendar_session_manager.end_session(chat_id)
                await self._send_message(
                    event, line_bot_api,
                    "✅ Finished processing scraped events.\n\n"
                    "เสร็จสิ้นการประมวลผลกิจกรรมที่สแกน"
                )
            return True
            
        elif text_lower in ["done", "skip all", "finish", "เสร็จ"]:
            # End scrape flow
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "✅ Scrape session ended.\n\nเสร็จสิ้นการสแกน"
            )
            return True

        return False

    async def _handle_scrape_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Handle reminder days selection for scraped event."""
        text_lower = text.lower().strip()
        
        # Parse reminder days
        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 0]
        elif text_lower in ["3", "3 days"]:
            reminder_days = [3, 0]
        elif text_lower in ["1", "1 day"]:
            reminder_days = [1, 0]
        else:
            await self._send_message(
                event, line_bot_api,
                "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                "กรุณาเลือก 7, 3, 1 หรือ all"
            )
            return True
        
        # Get event data with reminder days
        event_data = calendar_session_manager.set_scrape_reminder_days(chat_id, reminder_days)
        
        if event_data and self._calendar_service and user_id:
            # Create the event
            self._calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data["description"],
                reminder_days=event_data["reminder_days"],
                is_friend=event_data["is_friend"]
            )
            
            await self._send_message(
                event, line_bot_api,
                f"✅ Added: {event_data['title']}\n\n"
                f"เพิ่มแล้ว: {event_data['title']}"
            )
        
        # Move to next event
        has_more = calendar_session_manager.advance_scrape_index(chat_id)
        if has_more:
            next_event = calendar_session_manager.get_current_scraped_event(chat_id)
            if next_event:
                current, total = calendar_session_manager.get_scrape_progress(chat_id)
                await self._prompt_scraped_event(
                    event, line_bot_api, next_event, current, total
                )
        else:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "✅ Finished adding all scraped events!\n\n"
                "เพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว"
            )
        
        return True

    # =========================================================================
    # Zeus Add [date] [title] - Inline Add Flow
    # =========================================================================

    async def _handle_inline_add_trigger(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        parsed_data: Dict[str, Any]
    ) -> bool:
        """
        Handle "zeus add [date] [title]" inline trigger.
        
        Starts directly at reminder selection since date and title are already provided.
        """
        if not user_id:
            await self._send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        event_date = parsed_data["date"]
        title = parsed_data["title"]
        
        # Validate date is in the future
        today = datetime.now(BANGKOK_TZ).date()
        if event_date < today:
            await self._send_message(
                event, line_bot_api,
                "❌ That date is in the past!\n\n"
                "Please use a future date.\n\n"
                "วันที่ที่ระบุผ่านไปแล้ว กรุณาใส่วันที่ในอนาคต"
            )
            return True

        # Check friendship status
        is_friend = await self._is_friend(event, line_bot_api)

        # Start inline add flow (skips date/title input)
        calendar_session_manager.start_inline_add_flow(
            chat_id=chat_id,
            user_id=user_id,
            event_date=event_date,
            title=title,
            description="",
            is_friend=is_friend
        )

        date_str = event_date.strftime("%B %d, %Y")
        
        msg = (
            f"📅 Adding event:\n\n"
            f"📌 {title}\n"
            f"📆 {date_str}\n\n"
            "When should I remind you?\n\n"
            "• 7 - 7 days before\n"
            "• 3 - 3 days before\n"
            "• 1 - 1 day before\n"
            "• all - All of the above\n\n"
            "(Day-of reminder is always included)"
        )
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="7 days", text="7")),
            QuickReplyItem(type="action", action=MessageAction(label="3 days", text="3")),
            QuickReplyItem(type="action", action=MessageAction(label="1 day", text="1")),
            QuickReplyItem(type="action", action=MessageAction(label="All", text="all")),
        ])
        
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_inline_add_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Handle reminder days selection for inline add."""
        text_lower = text.lower().strip()
        
        # Parse reminder days
        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 0]
        elif text_lower in ["3", "3 days"]:
            reminder_days = [3, 0]
        elif text_lower in ["1", "1 day"]:
            reminder_days = [1, 0]
        else:
            await self._send_message(
                event, line_bot_api,
                "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                "กรุณาเลือก 7, 3, 1 หรือ all"
            )
            return True
        
        # Get event data with reminder days (moves to CONFIRMING state)
        event_data = calendar_session_manager.set_inline_reminder_days(chat_id, reminder_days)
        
        if not event_data:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "❌ Something went wrong. Please try again."
            )
            return True

        # Show confirmation
        date_str = event_data["date"].strftime("%B %d, %Y")
        reminder_str = ", ".join([
            f"{d} days" if d > 0 else "day-of" 
            for d in sorted(event_data["reminder_days"], reverse=True)
        ])
        
        msg = (
            "📝 Confirm event:\n\n"
            f"📆 Date: {date_str}\n"
            f"📌 Title: {event_data['title']}\n"
            f"⏰ Reminders: {reminder_str}\n\n"
            "Is this correct? (yes/no)"
        )
        
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", action=MessageAction(label="✅ Yes", text="yes")),
            QuickReplyItem(type="action", action=MessageAction(label="❌ No", text="no")),
        ])
        
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_inline_add_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str]
    ) -> bool:
        """Handle confirmation for inline add."""
        text_lower = text.lower().strip()
        
        if text_lower in ["yes", "y", "ใช่", "ok", "confirm"]:
            # Get session to retrieve event data
            session = calendar_session_manager.get_session(chat_id)
            
            if not session or not session.inline_event_data or not self._calendar_service or not user_id:
                await self._send_message(
                    event, line_bot_api,
                    "❌ Something went wrong. Please try again."
                )
                calendar_session_manager.end_session(chat_id)
                return True

            # Create the event
            new_event = self._calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=session.inline_event_data["title"],
                event_date=session.inline_event_data["date"],
                description=session.inline_event_data.get("description", ""),
                reminder_days=session.pending_reminder_days,
                is_friend=session.pending_is_friend
            )
            
            calendar_session_manager.end_session(chat_id)
            
            date_str = new_event.event_date.strftime("%B %d, %Y")
            reminder_str = ", ".join([f"{d}d" for d in sorted(new_event.reminder_days, reverse=True)])
            
            msg = (
                "✅ Event created!\n\n"
                f"📆 {new_event.title}\n"
                f"📅 {date_str}\n"
                f"⏰ Reminders: {reminder_str}\n\n"
                "I'll remind you at 8 AM Bangkok time.\n\n"
                "เพิ่มกิจกรรมเรียบร้อยแล้ว! จะเตือนตอน 8 โมงเช้าค่ะ"
            )
            
            await self._send_message(event, line_bot_api, msg)
            return True
            
        elif text_lower in ["no", "n", "ไม่"]:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api,
                "❌ Event creation cancelled.\n\n"
                "Say 'zeus add [date] [title]' to try again.\n\n"
                "ยกเลิกแล้ว"
            )
            return True
        else:
            await self._send_message(
                event, line_bot_api,
                "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no"
            )
            return True

    # =========================================================================
    # Date Parsing
    # =========================================================================

    def _parse_date(self, text: str) -> Optional[date]:
        """
        Parse date from various formats.
        
        Supports:
        - ISO format: 2025-01-15
        - Slash format: 15/01/2025, 01/15/2025
        - Named format: Jan 15, 2025 / January 15, 2025
        - Relative: tomorrow, next week, in 3 days
        """
        text = text.strip().lower()
        today = datetime.now(BANGKOK_TZ).date()
        
        # Relative dates
        if text in ["today", "วันนี้"]:
            return today
        if text in ["tomorrow", "พรุ่งนี้"]:
            return today + timedelta(days=1)
        if text in ["next week", "สัปดาห์หน้า"]:
            return today + timedelta(weeks=1)
        
        # "in X days"
        match = re.match(r"in\s+(\d+)\s+days?", text)
        if match:
            days = int(match.group(1))
            return today + timedelta(days=days)
        
        # Try python-dateutil if available
        try:
            from dateutil import parser as date_parser
            from dateutil.parser import ParserError
            
            try:
                # IMPORTANT: Pass default=today to ensure missing year/month/day
                # components use the CURRENT date, not a stale cached value.
                # Without this, dateutil may use the year from when it was imported.
                default_dt = datetime.now(BANGKOK_TZ)
                parsed = date_parser.parse(text, dayfirst=True, fuzzy=True, default=default_dt)
                return parsed.date()
            except (ParserError, ValueError):
                pass
        except ImportError:
            pass
        
        # Fallback: manual parsing
        # Try ISO format
        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            pass
        
        # Try DD/MM/YYYY
        try:
            return datetime.strptime(text, "%d/%m/%Y").date()
        except ValueError:
            pass
        
        # Try MM/DD/YYYY
        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            pass
        
        # Try "Jan 15, 2025"
        try:
            return datetime.strptime(text, "%b %d, %Y").date()
        except ValueError:
            pass
        
        return None

    # =========================================================================
    # Message Helpers
    # =========================================================================

    async def _send_message(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str
    ) -> None:
        """Send a text message."""
        msg = TextMessage(text=text, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[msg],
                    notificationDisabled=False,
                ),
            )

    async def _send_message_with_quick_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
        quick_reply: QuickReply
    ) -> None:
        """Send a text message with Quick Reply buttons."""
        msg = TextMessage(text=text, quickReply=quick_reply, quoteToken=None)
        
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[msg],
                    notificationDisabled=False,
                ),
            )

    async def _send_error_message(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi
    ) -> None:
        """Send error message."""
        await self._send_message(
            event, line_bot_api,
            "❌ Something went wrong. Please try again.\n\n"
            "เกิดข้อผิดพลาด กรุณาลองใหม่"
        )
