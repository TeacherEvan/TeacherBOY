"""
Calendar Flow Base - Common utilities for all calendar flows.
Provides shared message sending, date formatting, and validation.
"""

import asyncio
import logging
import re
from abc import ABC
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class CalendarFlowBase(ABC):
    """Base class for calendar flow handlers with shared utilities."""

    def __init__(self, calendar_service: Any | None = None):
        """
        Initialize flow handler.

        Args:
            calendar_service: CalendarService instance for data operations (optional for lazy loading)
        """
        self._calendar_service = calendar_service

    # =========================================================================
    # Message Sending Utilities
    # =========================================================================

    async def send_message(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
    ) -> bool:
        """
        Send a simple text message.

        Args:
            event: LINE message event with reply_token
            line_bot_api: LINE Messaging API client
            text: Message text to send

        Returns:
            True if message sent successfully
        """
        try:
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                        notificationDisabled=False,
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to send message (reply token may be expired): {e}")
            return False

    async def send_message_with_quick_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
        actions: list[dict[str, str]] | QuickReply,
    ) -> bool:
        """
        Send message with Quick Reply buttons.

        Args:
            event: LINE message event with reply_token
            line_bot_api: LINE Messaging API client
            text: Message text to send
            actions: List of action dicts with 'label' and 'text' keys

        Returns:
            True if message sent successfully
        """
        try:
            if isinstance(actions, QuickReply):
                quick_reply = actions
            else:
                quick_reply_items = [
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label=action["label"], text=action["text"]),
                    )
                    for action in actions
                ]
                quick_reply = QuickReply(items=quick_reply_items)

            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[TextMessage(text=text, quickReply=quick_reply, quoteToken=None)],
                        notificationDisabled=False,
                    ),
                )
            return True
        except Exception as e:
            logger.warning(f"⚠️ Failed to send quick reply message (reply token may be expired): {e}")
            return False

    async def send_error_message(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Send generic error message."""
        return await self.send_message(
            event,
            line_bot_api,
            "❌ Something went wrong. Please try again.\n\nเกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้งค่ะ",
        )

    # =========================================================================
    # Date Formatting Utilities
    # =========================================================================

    @staticmethod
    def format_date_display(dt: date) -> str:
        """
        Format date for display in messages.

        Args:
            dt: Date object to format

        Returns:
            Formatted string like "Mon, Jan 15, 2025"
        """
        return dt.strftime("%a, %b %d, %Y")

    @staticmethod
    def format_date_thai(dt: date) -> str:
        """
        Format date in Thai-friendly display.

        Args:
            dt: Date object to format

        Returns:
            Formatted string like "15 ม.ค. 2568"
        """
        thai_months = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
        thai_year = dt.year + 543
        return f"{dt.day} {thai_months[dt.month - 1]} {thai_year}"

    @staticmethod
    def format_relative_date(dt: date) -> str:
        """
        Get relative date description (today, tomorrow, in X days).

        Args:
            dt: Date to describe

        Returns:
            Relative description string
        """
        today = datetime.now(BANGKOK_TZ).date()
        delta = (dt - today).days

        if delta == 0:
            return "today"
        elif delta == 1:
            return "tomorrow"
        elif delta < 0:
            return f"{abs(delta)} days ago"
        elif delta <= 7:
            return f"in {delta} days"
        else:
            return CalendarFlowBase.format_date_display(dt)

    # =========================================================================
    # Validation Utilities
    # =========================================================================

    @staticmethod
    def validate_title(title: str) -> tuple[bool, str]:
        """
        Validate event title.

        Args:
            title: Title string to validate

        Returns:
            Tuple of (is_valid, error_message_or_cleaned_title)
        """
        if not title or not title.strip():
            return False, "Title cannot be empty"

        cleaned = title.strip()[:200]  # Max 200 chars

        # Check for banned characters (basic XSS prevention)
        banned_chars = ["<", ">", "{", "}", "\\"]
        if any(c in cleaned for c in banned_chars):
            return False, "Title contains invalid characters"

        return True, cleaned

    @staticmethod
    def validate_date(dt: date) -> tuple[bool, str]:
        """
        Validate event date.

        Args:
            dt: Date to validate

        Returns:
            Tuple of (is_valid, error_message)
        """
        today = datetime.now(BANGKOK_TZ).date()

        # Can't schedule more than 2 years in future
        max_future = today + timedelta(days=730)
        if dt > max_future:
            return False, "Date cannot be more than 2 years in the future"

        # Allow dates up to 30 days in the past (for retroactive logging)
        min_past = today - timedelta(days=30)
        if dt < min_past:
            return False, "Date cannot be more than 30 days in the past"

        return True, ""

    @staticmethod
    def validate_future_date(dt: date) -> bool:
        """Return True if date is today or later (Bangkok time)."""
        today = datetime.now(BANGKOK_TZ).date()
        return dt >= today

    @staticmethod
    def is_skip_command(text: str) -> bool:
        """Return True if user indicates skipping an optional step."""
        normalized = text.strip().lower()
        return normalized in {"skip", "none", "no", "n/a", "-", "ข้าม", "ไม่"}

    @staticmethod
    def parse_date(text: str) -> date | None:
        """Parse a date-only user input into a date.

        Supported formats:
        - today, tomorrow
        - next week
        - in X days
        - Month Day [Year] (e.g., Jan 15, 2026; January 15)
        - DD/MM/YYYY
        - YYYY-MM-DD
        """
        raw = text.strip()
        if not raw:
            return None

        lowered = raw.lower()
        now = datetime.now(BANGKOK_TZ)
        today = now.date()

        if lowered in {"today", "วันนี้"}:
            return today
        if lowered in {"tomorrow", "พรุ่งนี้"}:
            return today + timedelta(days=1)
        if lowered in {"next week"}:
            return today + timedelta(days=7)

        match = re.match(r"^in\s+(\d+)\s+days?$", lowered)
        if match:
            try:
                days = int(match.group(1))
                return today + timedelta(days=days)
            except ValueError:
                return None

        match = re.match(r"^(\d{1,2})/(\d{1,2})/(\d{4})$", raw)
        if match:
            try:
                d, m, y = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return date(y, m, d)
            except ValueError:
                return None

        match = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", raw)
        if match:
            try:
                y, m, d = int(match.group(1)), int(match.group(2)), int(match.group(3))
                return date(y, m, d)
            except ValueError:
                return None

        match = re.match(
            r"^(?P<month>[A-Za-z]+)\s+(?P<day>\d{1,2})(?:,?\s+(?P<year>\d{4}))?$",
            raw,
        )
        if match:
            month_str = match.group("month").lower()
            day = int(match.group("day"))
            year = int(match.group("year")) if match.group("year") else today.year

            month_map = {
                "jan": 1,
                "january": 1,
                "feb": 2,
                "february": 2,
                "mar": 3,
                "march": 3,
                "apr": 4,
                "april": 4,
                "may": 5,
                "jun": 6,
                "june": 6,
                "jul": 7,
                "july": 7,
                "aug": 8,
                "august": 8,
                "sep": 9,
                "sept": 9,
                "september": 9,
                "oct": 10,
                "october": 10,
                "nov": 11,
                "november": 11,
                "dec": 12,
                "december": 12,
            }

            if month_str not in month_map:
                return None

            try:
                parsed = date(year, month_map[month_str], day)
            except ValueError:
                return None

            # If year not specified and date already passed, roll to next year.
            if not match.group("year") and parsed < today:
                try:
                    parsed = date(year + 1, month_map[month_str], day)
                except ValueError:
                    return None

            return parsed

        return None

    # =========================================================================
    # Chat ID Utilities
    # =========================================================================

    @staticmethod
    def get_chat_id(event: MessageEvent) -> str:
        """
        Extract normalized chat ID from event.

        Args:
            event: LINE message event

        Returns:
            Chat ID string in format "user_xxx", "group_xxx", or "room_xxx"
        """
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

    @staticmethod
    def get_user_id(event: MessageEvent) -> str | None:
        """
        Extract user ID from event.

        Args:
            event: LINE message event

        Returns:
            User ID string or None
        """
        return getattr(event.source, "user_id", None) if event.source else None

    # =========================================================================
    # Quick Reply Templates
    # =========================================================================

    @staticmethod
    def get_reminder_quick_replies() -> list[dict[str, str]]:
        """Get standard reminder day selection quick replies."""
        return [
            {"label": "7 days before", "text": "7"},
            {"label": "3 days before", "text": "3"},
            {"label": "1 day before", "text": "1"},
            {"label": "Same day", "text": "0"},
            {"label": "All (7,3,1,0)", "text": "all"},
            {"label": "No reminder", "text": "none"},
        ]

    @staticmethod
    def get_yes_no_quick_replies() -> list[dict[str, str]]:
        """Get standard yes/no quick replies."""
        return [
            {"label": "Yes ✓", "text": "yes"},
            {"label": "No ✗", "text": "no"},
        ]

    @staticmethod
    def get_cancel_quick_reply() -> dict[str, str]:
        """Get cancel quick reply."""
        return {"label": "Cancel ❌", "text": "cancel"}
