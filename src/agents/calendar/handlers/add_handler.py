"""
Add Handler - Handles adding calendar events (multi-step flow).

This handler manages the complex multi-step process of adding calendar events,
including date, title, description, and reminder configuration.
"""
import asyncio
import logging
import re
from datetime import datetime, date, timedelta
from typing import Optional, Dict, Any, List
from zoneinfo import ZoneInfo
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi, QuickReply, QuickReplyItem, MessageAction
from linebot.v3.messaging.exceptions import ApiException

from ..base_handler import CalendarHandler
from src.services.calendar_session_manager import (
    calendar_session_manager,
    CalendarState,
)
from src.services.calendar_access_control import calendar_access_control
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter
from src.services.message_buffer_service import message_buffer_service
from src.services.date_extraction_service import date_extraction_service
from src.services.history_log_service import EventType, LogLevel, get_history_log
from src.services.bot_identity_service import get_bot_identity_service

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

CANCEL_KEYWORDS = ["cancel", "nevermind", "never mind", "ยกเลิก", "exit", "quit"]
SKIP_KEYWORDS = ["skip", "none", "no", "-", "ข้าม"]
LIVE_STOP_KEYWORDS = ["stop", "done", "finish", "end", "หยุด", "พอแล้ว", "เสร็จ"]


class AddHandler(CalendarHandler):
    """Handler for adding calendar events via multi-step flow."""

    def __init__(self) -> None:
        super().__init__(
            name="AddHandler",
            description="Adds calendar events via multi-step flow",
        )
        self._friend_cache: Dict[str, tuple[bool, datetime]] = {}

    def get_triggers(self) -> list:
        return TRIGGERS_ADD

    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)
        session = calendar_session_manager.get_session(chat_id)
        if session and session.state in (
            CalendarState.AWAITING_DATE,
            CalendarState.AWAITING_TITLE,
            CalendarState.AWAITING_DESCRIPTION,
            CalendarState.AWAITING_REMINDER_DAYS,
            CalendarState.CONFIRMING_ADD,
            CalendarState.ADD_MODE_SELECTION,
            CalendarState.LIVE_ADD_LISTENING,
            CalendarState.LIVE_ADD_REVIEWING,
            CalendarState.LIVE_ADD_REMINDER_DAYS,
        ):
            return True

        return self._is_trigger(text, TRIGGERS_ADD)

    async def handle(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        context: dict,
    ) -> bool:
        calendar_service = context.get("calendar_service")
        session = calendar_session_manager.get_session(chat_id)

        if self._is_trigger(text, TRIGGERS_ADD):
            return await self._start_add_flow(event, line_bot_api, chat_id, user_id)

        if not session:
            return False

        state = session.state

        if state == CalendarState.AWAITING_DATE:
            return await self._handle_date_input(event, text, line_bot_api, chat_id)
        if state == CalendarState.AWAITING_TITLE:
            return await self._handle_title_input(event, text, line_bot_api, chat_id)
        if state == CalendarState.AWAITING_DESCRIPTION:
            return await self._handle_description_input(event, text, line_bot_api, chat_id)
        if state == CalendarState.AWAITING_REMINDER_DAYS:
            return await self._handle_reminder_days_input(event, text, line_bot_api, chat_id)
        if state == CalendarState.CONFIRMING_ADD:
            return await self._handle_add_confirmation(
                event, text, line_bot_api, chat_id, user_id, calendar_service
            )
        if state == CalendarState.ADD_MODE_SELECTION:
            return await self._handle_add_mode_selection(
                event, text, line_bot_api, chat_id, user_id
            )
        if state == CalendarState.LIVE_ADD_LISTENING:
            return await self._handle_live_listening_message(
                event, text, line_bot_api, chat_id, user_id
            )
        if state == CalendarState.LIVE_ADD_REVIEWING:
            return await self._handle_live_review_response(
                event, text, line_bot_api, chat_id, user_id
            )
        if state == CalendarState.LIVE_ADD_REMINDER_DAYS:
            return await self._handle_live_reminder_response(
                event, text, line_bot_api, chat_id, user_id, calendar_service
            )

        return False

    async def _start_add_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        if not user_id:
            await self._send_message(event, line_bot_api, "❌ Cannot identify user.")
            return True

        can_create = await calendar_access_control.can_create_event(
            user_id, chat_id, line_bot_api
        )
        if not can_create:
            logger.warning(
                f"❌ Access denied: {user_id} cannot create events in {chat_id}"
            )
            history_log = get_history_log()
            if history_log:
                await history_log.log(
                    event_type=EventType.CALENDAR_ACCESS_DENIED,
                    message="Access denied: attempted to create event",
                    level=LogLevel.WARNING,
                    chat_id=chat_id,
                    user_id=user_id,
                    agent_name=self.name,
                    metadata={"operation": "create_event"},
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

        is_friend = await self._is_friend(event, line_bot_api)
        calendar_session_manager.start_add_flow(chat_id, user_id, is_friend)

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

    async def _handle_add_mode_selection(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        choice = text.strip()

        if choice == "1":
            calendar_session_manager.end_session(chat_id)
            from .scrape_handler import ScrapeHandler

            handler = ScrapeHandler()
            return await handler.handle(
                event,
                text,
                line_bot_api,
                chat_id,
                user_id,
                {"calendar_service": None},
            )
        if choice == "2":
            calendar_session_manager.end_session(chat_id)
            return await self._start_original_live_bulk_add(
                event, line_bot_api, chat_id, user_id
            )
        if choice == "3":
            calendar_session_manager.end_session(chat_id)
            return await self._start_add_flow(event, line_bot_api, chat_id, user_id)

        await self._send_message(
            event,
            line_bot_api,
            "❌ Invalid choice. Please reply with 1, 2, or 3.\n\nกรุณาเลือก 1, 2 หรือ 3",
        )
        return True

    async def _start_live_bulk_add_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        if not user_id:
            await self._send_message(event, line_bot_api, "❌ Cannot identify user.")
            return True

        recent_messages = message_buffer_service.get_message_texts(chat_id, limit=10)
        event_like_messages = [
            msg for msg in recent_messages if self._looks_like_event_message(msg)
        ]

        if len(event_like_messages) >= 2:
            msg = (
                f"🔍 I found {len(event_like_messages)} recent messages that might contain events!\n\n"
                "Would you like me to:\n\n"
                "1️⃣ Scan recent messages for dates\n"
                "2️⃣ Listen for new messages with dates\n"
                "3️⃣ Manually add an event\n\n"
                "Reply with 1, 2, or 3"
            )
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="🔍 Scan recent", text="1"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="🎯 Listen for new", text="2"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="✏️ Manual add", text="3"),
                    ),
                ]
            )
            calendar_session_manager.start_add_mode_selection(
                chat_id, user_id, is_friend=await self._is_friend(event, line_bot_api)
            )
            await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
            return True

        return await self._start_original_live_bulk_add(event, line_bot_api, chat_id, user_id)

    async def _start_original_live_bulk_add(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        if not user_id:
            await self._send_message(event, line_bot_api, "❌ Cannot identify user.")
            return True

        is_friend = await self._is_friend(event, line_bot_api)
        calendar_session_manager.start_live_add_flow(chat_id, user_id, is_friend)

        msg = (
            "📅 Live Bulk Add: ON\n\n"
            "Send messages normally. If I detect an event with a date, I'll propose it for adding.\n\n"
            "Examples:\n"
            "- Dear all, meeting on Friday\n"
            "- Deadline is Jan 15\n\n"
            "Type 'stop' anytime to exit.\n\n"
            "โหมดเพิ่มกิจกรรมอัตโนมัติ: เปิด\n"
            "พิมพ์ 'stop' เพื่อหยุด"
        )
        await self._send_message(event, line_bot_api, msg)
        return True

    async def _handle_live_listening_message(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        if self._is_live_stop_command(text) or self._is_cancel_command(text):
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event,
                line_bot_api,
                "✅ Live Bulk Add: OFF\n\nStopped listening for events.\n\nปิดโหมดเพิ่มกิจกรรมอัตโนมัติแล้ว",
            )
            return True

        if not self._looks_like_event_message(text):
            return True

        events = await self._extract_events_from_single_message(text)
        if not events:
            return True

        session = calendar_session_manager.add_live_events(chat_id, events)
        if not session:
            return True

        current = calendar_session_manager.get_current_live_event(chat_id)
        if current:
            await self._prompt_live_event(event, line_bot_api, current)
        return True

    async def _prompt_live_event(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        event_data: dict,
    ) -> None:
        date_obj = event_data.get("date")
        title = event_data.get("title", "Event")
        source = event_data.get("source_text", "")

        try:
            date_str = date_obj.strftime("%B %d, %Y") if date_obj else "Unknown"
        except Exception:
            date_str = "Unknown"

        source_preview = (
            source[:80] + "..." if isinstance(source, str) and len(source) > 80 else (source or "")
        )

        msg = (
            "🧾 Events scraped (live):\n\n"
            f"📆 {date_str}\n"
            f"📌 {title}\n"
            + (f"📝 From: \"{source_preview}\"\n" if source_preview else "")
            + "\nAdd this event? (yes/no)"
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
                    action=MessageAction(label="⏭️ No", text="no"),
                ),
            ]
        )
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)

    async def _handle_live_review_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        text_lower = text.lower().strip()

        if self._is_live_stop_command(text_lower) or self._is_cancel_command(text_lower):
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event,
                line_bot_api,
                "✅ Live Bulk Add: OFF\n\nStopped listening for events.",
            )
            return True

        if text_lower in ["yes", "y", "ใช่", "ok", "add"]:
            calendar_session_manager.accept_live_event(chat_id)
            msg = (
                "When should I remind you?\n\n"
                "• 7 - 7 days before\n"
                "• 3 - 3 days before\n"
                "• 1 - 1 day before\n"
                "• all - All of the above\n\n"
                "(Day-of reminder is always included)"
            )
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="7 days", text="7")),
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="3 days", text="3")),
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="1 day", text="1")),
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="All", text="all")),
                ]
            )
            await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
            return True

        if text_lower in ["no", "n", "ไม่", "skip"]:
            has_more = calendar_session_manager.skip_live_event(chat_id)
            if has_more:
                nxt = calendar_session_manager.get_current_live_event(chat_id)
                if nxt:
                    await self._prompt_live_event(event, line_bot_api, nxt)
            else:
                session = calendar_session_manager.get_session(chat_id)
                if session:
                    session.state = CalendarState.LIVE_ADD_LISTENING
                    session.update()
                await self._send_message(
                    event,
                    line_bot_api,
                    "✅ Skipped. Keep sending messages; I'll propose new events when found.\n\nType 'stop' to exit.",
                )
            return True

        await self._send_message(event, line_bot_api, "Please answer yes or no (or 'stop').")
        return True

    async def _handle_live_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Any,
    ) -> bool:
        text_lower = text.lower().strip()

        if self._is_live_stop_command(text_lower) or self._is_cancel_command(text_lower):
            calendar_session_manager.end_session(chat_id)
            await self._send_message(event, line_bot_api, "✅ Live Bulk Add: OFF")
            return True

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
                "❌ Invalid selection. Please choose 7, 3, 1, or all.",
            )
            return True

        event_data = calendar_session_manager.set_live_reminder_days(chat_id, reminder_days)
        if not event_data or not calendar_service or not user_id:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(event, line_bot_api, "❌ Something went wrong. Please try again.")
            return True

        try:
            new_event = calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data.get("description", ""),
                reminder_days=event_data.get("reminder_days"),
                is_friend=bool(event_data.get("is_friend", False)),
            )
        except Exception as exc:
            logger.error(f"❌ Failed to add live event: {exc}", exc_info=True)
            await self._send_message(event, line_bot_api, "❌ Failed to add event. Please try again.")
            session = calendar_session_manager.get_session(chat_id)
            if session:
                session.state = CalendarState.LIVE_ADD_LISTENING
                session.update()
            return True

        await self._send_message(
            event,
            line_bot_api,
            f"✅ Added: {new_event.title}\n📅 {new_event.event_date.strftime('%B %d, %Y')}\n\nKeep sending messages; I'll propose more. Type 'stop' to exit.",
        )

        has_more = calendar_session_manager.skip_live_event(chat_id)
        if has_more:
            nxt = calendar_session_manager.get_current_live_event(chat_id)
            if nxt:
                await self._prompt_live_event(event, line_bot_api, nxt)
        else:
            session = calendar_session_manager.get_session(chat_id)
            if session:
                session.state = CalendarState.LIVE_ADD_LISTENING
                session.update()
        return True

    async def _handle_date_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        if self._looks_like_bulk_dates(text):
            logger.info("🔍 Detected bulk date input, switching to extraction flow")
            session = calendar_session_manager.get_session(chat_id)
            if not session:
                return False
            user_id = session.user_id

            calendar_session_manager.end_session(chat_id)
            is_friend = await self._is_friend(event, line_bot_api)
            calendar_session_manager.start_scrape_flow(chat_id, user_id, [text], is_friend)

            try:
                events = await date_extraction_service.extract_events_from_messages([text])
                if not events:
                    await self._send_message(
                        event,
                        line_bot_api,
                        "🤔 I see you pasted event details, but I couldn't extract any dates.\n\n"
                        "Please try using 'Ms. Green scrape' or enter a single date.\n\n"
                        "ฉันเห็นว่าคุณวางรายละเอียดกิจกรรม แต่ไม่สามารถดึงวันที่ได้",
                    )
                    calendar_session_manager.end_session(chat_id)
                    return True

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

                calendar_session_manager.set_scraped_events(chat_id, events_data)
                first_event = calendar_session_manager.get_current_scraped_event(chat_id)
                if first_event:
                    await self._prompt_scraped_event(
                        event,
                        line_bot_api,
                        first_event,
                        1,
                        len(events_data),
                        header=f"✨ I extracted {len(events_data)} event(s) from your input!\n\n",
                    )
                return True

            except Exception as exc:
                logger.error(f"❌ Bulk date extraction failed: {exc}", exc_info=True)
                await self._send_message(
                    event,
                    line_bot_api,
                    "❌ Failed to process bulk dates. Please try 'Ms. Green scrape' or enter one date at a time.",
                )
                calendar_session_manager.end_session(chat_id)
                return True

        parsed_date = self._parse_date(text)
        if not parsed_date:
            await self._send_message(
                event,
                line_bot_api,
                "❌ I couldn't understand that date.\n\n"
                "Try formats like:\n"
                "• Jan 15, 2025\n"
                "• 15/01/2025\n"
                "• 2025-01-15\n"
                "• tomorrow\n"
                "• next week\n\n"
                "💡 TIP: Paste multiple events? I'll extract them automatically!\n\n"
                "ไม่เข้าใจวันที่ กรุณาลองอีกครั้ง",
            )
            return True

        today = datetime.now(BANGKOK_TZ).date()
        if parsed_date < today:
            await self._send_message(
                event,
                line_bot_api,
                "❌ That date is in the past!\n\n"
                "Please enter a future date.\n\n"
                "วันที่ที่ระบุผ่านไปแล้ว กรุณาใส่วันที่ในอนาคต",
            )
            return True

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
        chat_id: str,
    ) -> bool:
        title = text.strip()[:100]
        if len(title) < 2:
            await self._send_message(
                event,
                line_bot_api,
                "❌ Title is too short. Please enter at least 2 characters.\n\n"
                "ชื่อสั้นเกินไป กรุณาใส่อย่างน้อย 2 ตัวอักษร",
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
        chat_id: str,
    ) -> bool:
        description = "" if self._is_skip_command(text) else text.strip()[:500]
        calendar_session_manager.set_pending_description(chat_id, description)

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
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="7 days", text="7")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="3 days", text="3")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="1 day", text="1")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="All", text="all")),
            ]
        )
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_reminder_days_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        text_lower = text.lower().strip()
        reminder_days: List[int] = []

        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 0]
        elif text_lower in ["3", "3 days"]:
            reminder_days = [3, 0]
        elif text_lower in ["1", "1 day"]:
            reminder_days = [1, 0]
        else:
            try:
                parts = re.split(r"[,\s]+", text_lower)
                for part in parts:
                    if part.isdigit():
                        day = int(part)
                        if 0 <= day <= 30:
                            reminder_days.append(day)
            except Exception:
                pass

            if not reminder_days:
                await self._send_message(
                    event,
                    line_bot_api,
                    "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                    "กรุณาเลือก 7, 3, 1 หรือ all",
                )
                return True

        if 0 not in reminder_days:
            reminder_days.append(0)

        calendar_session_manager.set_pending_reminder_days(chat_id, reminder_days)
        session = calendar_session_manager.get_session(chat_id)
        if not session:
            return False

        date_str = session.pending_date.strftime("%B %d, %Y") if session.pending_date else "N/A"
        reminder_str = ", ".join(
            [f"{d} days" if d > 0 else "day-of" for d in sorted(reminder_days, reverse=True)]
        )
        msg = (
            "📝 Please confirm your event:\n\n"
            f"📆 Date: {date_str}\n"
            f"📌 Title: {session.pending_title}\n"
            f"📝 Description: {session.pending_description or '(none)'}\n"
            f"⏰ Reminders: {reminder_str}\n\n"
            "Is this correct? (yes/no)\n\n"
            "ข้อมูลถูกต้องไหม? (yes/no)"
        )
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="✅ Yes", text="yes")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="❌ No", text="no")),
            ]
        )
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_add_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Any,
    ) -> bool:
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "ใช่", "ok", "confirm"]:
            event_data = calendar_session_manager.get_pending_event_data(chat_id)
            if not event_data or not calendar_service or not user_id:
                await self._send_message(event, line_bot_api, "❌ Something went wrong. Please try again.")
                calendar_session_manager.end_session(chat_id)
                return True

            new_event = calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data["description"],
                reminder_days=event_data["reminder_days"],
                is_friend=event_data["is_friend"],
            )

            calendar_session_manager.end_session(chat_id)
            date_str = new_event.event_date.strftime("%B %d, %Y")
            reminder_str = ", ".join(
                [f"{d}d" for d in sorted(new_event.reminder_days, reverse=True)]
            )
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
                "❌ Event creation cancelled.\n\n"
                "Say 'Ms. Green add event' to try again.\n\n"
                "ยกเลิกแล้ว พิมพ์ 'Ms. Green add event' เพื่อลองใหม่",
            )
            return True

        await self._send_message(event, line_bot_api, "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no")
        return True

    async def _prompt_scraped_event(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        event_data: Dict[str, Any],
        current: int,
        total: int,
        header: str = "",
    ) -> None:
        date_obj = event_data.get("date")
        title = event_data.get("title", "Event")
        source = event_data.get("source_text", "")
        confidence = event_data.get("confidence", "medium")

        date_str = date_obj.strftime("%B %d, %Y") if date_obj else "Unknown"

        msg = header + (
            f"📅 Event {current}/{total}:\n\n"
            f"📌 {title}\n"
            f"📆 {date_str}\n"
        )

        if source:
            source_preview = source[:50] + "..." if len(source) > 50 else source
            msg += f"📝 From: \"{source_preview}\"\n"

        msg += f"🎯 Confidence: {confidence}\n\n"
        msg += "Add this to calendar? (yes/no/skip all)"

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="✅ Yes", text="yes")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="⏭️ Skip", text="no")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="🚫 Skip All", text="done")),
            ]
        )
        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)

    def _looks_like_bulk_dates(self, text: str) -> bool:
        if not text or len(text) < 50:
            return False

        text_lower = text.lower()
        if "zeus observes" in text_lower or "━━━━━" in text:
            return True

        numbered_items = len(re.findall(r"^\s*\d+\.", text, re.MULTILINE))
        if numbered_items >= 3:
            return True

        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{1,2}/\d{1,2}/\d{4}",
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}",
        ]

        date_matches = sum(
            len(re.findall(pattern, text, re.IGNORECASE)) for pattern in date_patterns
        )
        if date_matches >= 3:
            return True

        lines_with_dates = sum(
            1
            for line in text.split("\n")
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in date_patterns)
        )
        return lines_with_dates >= 3

    def _looks_like_event_message(self, text: str) -> bool:
        t = (text or "").lower().strip()
        if not t:
            return False

        prefix, _ = get_bot_identity_service().split_command_prefix(text or "")
        if prefix is not None or t.startswith("/admin") or t.startswith("/special"):
            return False

        keywords = [
            "meeting",
            "call",
            "appointment",
            "deadline",
            "due",
            "schedule",
            "remind",
            "reminder",
            "party",
            "event",
            "workshop",
            "interview",
            "class",
            "exam",
            "บิน",
            "ประชุม",
            "นัด",
            "เดดไลน์",
            "กำหนดส่ง",
            "ส่งงาน",
            "สัมภาษณ์",
            "สอบ",
            "เรียน",
        ]
        return any(k in t for k in keywords)

    async def _extract_events_from_single_message(self, text: str) -> list[dict]:
        try:
            extracted = await date_extraction_service.extract_events_from_messages(
                [text], max_events=3
            )
            return [evt.to_dict() for evt in extracted]
        except Exception as exc:
            logger.error(f"❌ Live extraction failed: {exc}", exc_info=True)
            return []

    def _is_skip_command(self, text: str) -> bool:
        return text.lower().strip() in SKIP_KEYWORDS

    def _is_cancel_command(self, text: str) -> bool:
        return text.lower().strip() in CANCEL_KEYWORDS

    def _is_live_stop_command(self, text: str) -> bool:
        return text.lower().strip() in LIVE_STOP_KEYWORDS

    async def _is_friend(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            return False

        cached = self._friend_cache.get(user_id)
        if cached:
            is_friend, cached_at = cached
            age = (datetime.now() - cached_at).total_seconds()
            if age < 300:
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

    def _parse_date(self, text: str) -> Optional[date]:
        text = text.strip().lower()
        today = datetime.now(BANGKOK_TZ).date()

        if text in ["today", "วันนี้"]:
            return today
        if text in ["tomorrow", "พรุ่งนี้"]:
            return today + timedelta(days=1)
        if text in ["next week", "สัปดาห์หน้า"]:
            return today + timedelta(weeks=1)

        match = re.match(r"in\s+(\d+)\s+days?", text)
        if match:
            days = int(match.group(1))
            return today + timedelta(days=days)

        try:
            from dateutil import parser as date_parser
            from dateutil.parser import ParserError

            try:
                default_dt = datetime.now(BANGKOK_TZ)
                parsed = date_parser.parse(text, dayfirst=True, fuzzy=True, default=default_dt)
                return parsed.date()
            except (ParserError, ValueError):
                pass
        except ImportError:
            pass

        try:
            return datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            pass

        try:
            return datetime.strptime(text, "%d/%m/%Y").date()
        except ValueError:
            pass

        try:
            return datetime.strptime(text, "%m/%d/%Y").date()
        except ValueError:
            pass

        try:
            return datetime.strptime(text, "%b %d, %Y").date()
        except ValueError:
            pass

        return None

    def _get_chat_id(self, event: MessageEvent) -> str:
        if event.source and getattr(event.source, "group_id", None):
            return f"group_{getattr(event.source, 'group_id')}"
        if event.source and getattr(event.source, "room_id", None):
            return f"room_{getattr(event.source, 'room_id')}"
        if event.source and getattr(event.source, "user_id", None):
            return f"user_{getattr(event.source, 'user_id')}"
        return "user_unknown"
