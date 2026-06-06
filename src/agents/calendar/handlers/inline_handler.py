"""
Inline Handler - Processes "zeus add [date] [title]" shorthand format.

This handler provides a quick way to add events without the multi-step flow,
parsing date and title from a single command.
"""

import asyncio
import logging
import re
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
)
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.bot_identity_service import get_bot_identity_service
from src.services.calendar_access_control import calendar_access_control
from src.services.calendar_service import CalendarService
from src.services.calendar_session_manager import (
    CalendarState,
    calendar_session_manager,
)
from src.services.history_log_service import EventType, LogLevel, get_history_log
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter

from ..base_handler import CalendarHandler

logger = logging.getLogger(__name__)

BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

TRIGGERS_ADD = [
    "zeus add event",
    "zeus remind me",
    "zeus calendar add",
    "zeus new event",
    "add reminder",
    "add event",
]


class InlineHandler(CalendarHandler):
    """Handler for inline "zeus add [date] [title]" commands."""

    def __init__(self) -> None:
        super().__init__(
            name="InlineHandler",
            description="Processes quick 'zeus add [date] [title]' format",
        )
        self._friend_cache: dict[str, tuple[bool, datetime]] = {}

    def get_triggers(self) -> list:
        return ["zeus add", "ms. green add", "ms green add"]

    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)
        session = calendar_session_manager.get_session(chat_id)
        if session and session.state in (
            CalendarState.INLINE_ADD_REMINDER_DAYS,
            CalendarState.INLINE_ADD_CONFIRMING,
        ):
            return True

        return bool(self._parse_inline_add(text))

    async def handle(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
        context: dict,
    ) -> bool:
        calendar_service: CalendarService | None = context.get("calendar_service")
        session = calendar_session_manager.get_session(chat_id)

        inline_data = self._parse_inline_add(text)
        if inline_data:
            return await self._handle_inline_add_trigger(event, line_bot_api, chat_id, user_id, inline_data)

        if not session:
            return False

        if session.state == CalendarState.INLINE_ADD_REMINDER_DAYS:
            return await self._handle_inline_add_reminder_response(event, text, line_bot_api, chat_id, user_id)

        if session.state == CalendarState.INLINE_ADD_CONFIRMING:
            return await self._handle_inline_add_confirmation(event, text, line_bot_api, chat_id, user_id, calendar_service)

        return False

    def _parse_inline_add(self, text: str) -> dict[str, Any] | None:
        normalized = (text or "").strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(normalized)
        command_text = rest.strip() if prefix else normalized
        text_lower = command_text.lower().strip()

        if not text_lower.startswith("add "):
            return None

        if self._is_trigger(text, TRIGGERS_ADD):
            return None

        remainder = command_text[4:].strip()
        if not remainder:
            return None

        parsed_date = None
        title_start = 0

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
            match = re.match(r"in\s+(\d+)\s+days?\s+(.+)", remainder_lower)
            if match:
                days = int(match.group(1))
                today = datetime.now(BANGKOK_TZ).date()
                parsed_date = today + timedelta(days=days)
                title_start = match.start(2)

        if not parsed_date:
            date_patterns = [
                (
                    r"(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d{1,2})(?:,?\s+(\d{4}))?\s+(.+)",
                    "named",
                ),
                (r"(\d{1,2})[/\-](\d{1,2})(?:[/\-](\d{4}))?\s+(.+)", "slash"),
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

                            month_map = {
                                "jan": 1,
                                "feb": 2,
                                "mar": 3,
                                "apr": 4,
                                "may": 5,
                                "jun": 6,
                                "jul": 7,
                                "aug": 8,
                                "sep": 9,
                                "oct": 10,
                                "nov": 11,
                                "dec": 12,
                            }
                            month = month_map.get(month_str, 1)

                            try:
                                parsed_date = date(year, month, day)
                                if parsed_date < datetime.now(BANGKOK_TZ).date() and not match.group(3):
                                    parsed_date = date(year + 1, month, day)
                            except ValueError:
                                continue

                            title = match.group(4).strip()
                            if title:
                                return {
                                    "date": parsed_date,
                                    "title": remainder[match.start(4) :].strip()[:100],
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
                                    "title": remainder[match.start(4) :].strip()[:100],
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
                                    "title": remainder[match.start(4) :].strip()[:100],
                                }
                    except (ValueError, IndexError):
                        continue
                    break

        if parsed_date and title_start > 0:
            title = remainder[title_start:].strip()
            if title:
                return {
                    "date": parsed_date,
                    "title": title[:100],
                }

        return None

    async def _handle_inline_add_trigger(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
        parsed_data: dict[str, Any],
    ) -> bool:
        if not user_id:
            await self._send_message(event, line_bot_api, "❌ Cannot identify user.")
            return True

        can_create = await calendar_access_control.can_create_event(user_id, chat_id, line_bot_api)
        if not can_create:
            logger.warning(f"❌ Access denied: {user_id} cannot create events in {chat_id}")
            history_log = get_history_log()
            if history_log:
                await history_log.log(
                    event_type=EventType.CALENDAR_ACCESS_DENIED,
                    message="Access denied: attempted to create event inline",
                    level=LogLevel.WARNING,
                    chat_id=chat_id,
                    user_id=user_id,
                    agent_name=self.name,
                    metadata={"operation": "create_event_inline"},
                )
            await self._send_message(
                event,
                line_bot_api,
                "❌ You don't have permission to create events in this chat.",
            )
            return True

        is_admin = privilege_service.is_admin(user_id)
        if not rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin):
            await self._send_message(
                event,
                line_bot_api,
                "⏳ Calendar rate limit exceeded. Please try again later.",
            )
            return True

        event_date = parsed_data["date"]
        title = parsed_data["title"]

        today = datetime.now(BANGKOK_TZ).date()
        if event_date < today:
            await self._send_message(
                event,
                line_bot_api,
                "❌ That date is in the past!\n\nPlease use a future date.\n\nวันที่ที่ระบุผ่านไปแล้ว กรุณาใส่วันที่ในอนาคต",
            )
            return True

        is_friend = await self._is_friend(event, line_bot_api)

        calendar_session_manager.start_inline_add_flow(
            chat_id=chat_id,
            user_id=user_id,
            event_date=event_date,
            title=title,
            description="",
            is_friend=is_friend,
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

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="7 days", text="7"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="3 days", text="3"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="1 day", text="1"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="All", text="all"),
                ),
            ]
        )

        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_inline_add_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
    ) -> bool:
        text_lower = text.lower().strip()

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
                event,
                line_bot_api,
                "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\nกรุณาเลือก 7, 3, 1 หรือ all",
            )
            return True

        event_data = calendar_session_manager.set_inline_reminder_days(chat_id, reminder_days)

        if not event_data:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(event, line_bot_api, "❌ Something went wrong. Please try again.")
            return True

        date_str = event_data["date"].strftime("%B %d, %Y")
        reminder_str = ", ".join(
            [f"{d} days" if d > 0 else "day-of" for d in sorted(event_data["reminder_days"], reverse=True)]
        )

        msg = (
            "📝 Confirm event:\n\n"
            f"📆 Date: {date_str}\n"
            f"📌 Title: {event_data['title']}\n"
            f"⏰ Reminders: {reminder_str}\n\n"
            "Is this correct? (yes/no)"
        )

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="✅ Yes", text="yes"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="❌ No", text="no"),
                ),
            ]
        )

        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_inline_add_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
        calendar_service: CalendarService | None,
    ) -> bool:
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "ใช่", "ok", "confirm"]:
            session = calendar_session_manager.get_session(chat_id)

            if not session or not session.inline_event_data or not calendar_service or not user_id:
                await self._send_message(event, line_bot_api, "❌ Something went wrong. Please try again.")
                calendar_session_manager.end_session(chat_id)
                return True

            new_event = calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=session.inline_event_data["title"],
                event_date=session.inline_event_data["date"],
                description=session.inline_event_data.get("description", ""),
                reminder_days=session.pending_reminder_days,
                is_friend=session.pending_is_friend,
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

        if text_lower in ["no", "n", "ไม่"]:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event,
                line_bot_api,
                "❌ Event creation cancelled.\n\nSay 'Ms. Green add [date] [title]' to try again.\n\nยกเลิกแล้ว",
            )
            return True

        await self._send_message(
            event,
            line_bot_api,
            "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no",
        )
        return True

    async def _is_friend(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            return False

        cached = self._friend_cache.get(user_id)
        if cached:
            is_friend, cached_at = cached
            age = (datetime.now() - cached_at).total_seconds()
            if age < settings.friend_cache_ttl_seconds:
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

    def _get_chat_id(self, event: MessageEvent) -> str:
        if event.source and getattr(event.source, "group_id", None):
            return f"group_{event.source.group_id}"
        if event.source and getattr(event.source, "room_id", None):
            return f"room_{event.source.room_id}"
        if event.source and getattr(event.source, "user_id", None):
            return f"user_{event.source.user_id}"
        return "user_unknown"
