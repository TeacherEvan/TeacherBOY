"""
Scrape Handler - Extracts dates from recent chat messages.

This handler scans recent messages to find event-like content and proposes
adding them to the calendar.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from linebot.v3.messaging import MessageAction, MessagingApi, QuickReply, QuickReplyItem
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.calendar_access_control import calendar_access_control
from src.services.calendar_service import CalendarService
from src.services.calendar_session_manager import (
    CalendarState,
    calendar_session_manager,
)
from src.services.date_extraction_service import date_extraction_service
from src.services.history_log_service import EventType, LogLevel, get_history_log
from src.services.message_buffer_service import message_buffer_service
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter

from ..base_handler import CalendarHandler

logger = logging.getLogger(__name__)

TRIGGERS_SCRAPE = [
    "zeus scrape",
    "zeus scan",
    "zeus scan messages",
]


class ScrapeHandler(CalendarHandler):
    """Handler for scraping calendar events from recent messages."""

    def __init__(self) -> None:
        super().__init__(
            name="ScrapeHandler",
            description="Scrapes calendar events from recent messages",
        )
        self._friend_cache: dict[str, tuple[bool, Any]] = {}

    def get_triggers(self) -> list:
        return TRIGGERS_SCRAPE

    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)
        session = calendar_session_manager.get_session(chat_id)
        if session and session.state in (
            CalendarState.SCRAPE_REVIEWING,
            CalendarState.SCRAPE_REMINDER_DAYS,
        ):
            return True

        return self._is_trigger(text, TRIGGERS_SCRAPE)

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

        if self._is_trigger(text, TRIGGERS_SCRAPE):
            return await self._handle_scrape_trigger(event, line_bot_api, chat_id, user_id)

        if not session:
            return False

        if session.state == CalendarState.SCRAPE_REVIEWING:
            return await self._handle_scrape_review_response(event, text, line_bot_api, chat_id, user_id)

        if session.state == CalendarState.SCRAPE_REMINDER_DAYS:
            return await self._handle_scrape_reminder_response(event, text, line_bot_api, chat_id, user_id, calendar_service)

        return False

    async def _handle_scrape_trigger(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
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
                    message="Access denied: attempted to scrape events",
                    level=LogLevel.WARNING,
                    chat_id=chat_id,
                    user_id=user_id,
                    agent_name=self.name,
                    metadata={"operation": "scrape_events"},
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

        messages = message_buffer_service.get_message_texts(chat_id, limit=10)
        if not messages:
            await self._send_message(
                event,
                line_bot_api,
                "📭 No recent messages found to scan.\n\n"
                "I can only scan messages that arrived while I was active.\n\n"
                "ไม่พบข้อความล่าสุดที่จะสแกน\n"
                "ฉันสามารถสแกนเฉพาะข้อความที่มาถึงขณะที่ฉันทำงานอยู่",
            )
            return True

        logger.info(f"🔍 Scanning {len(messages)} messages for chat {chat_id}")

        is_friend = await self._is_friend(event, line_bot_api)
        calendar_session_manager.start_scrape_flow(chat_id, user_id, messages, is_friend)

        try:
            events = await date_extraction_service.extract_events_from_messages(messages)
        except Exception as e:
            logger.error(f"❌ Date extraction failed: {e}", exc_info=True)
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event,
                line_bot_api,
                "❌ Failed to scan messages. Please try again.\n\nสแกนข้อความไม่สำเร็จ กรุณาลองใหม่",
            )
            return True

        if not events:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event,
                line_bot_api,
                "📭 No dates or events found in recent messages.\n\n"
                "ไม่พบวันที่หรือกิจกรรมในข้อความล่าสุด\n\n"
                "💡 Try 'Ms. Green add [date] [title]' to add directly.",
            )
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
                header=(
                    f"🔍 Scanned {len(messages)} messages - found {len(events_data)} event(s)!\n"
                    f"สแกน {len(messages)} ข้อความ - พบ {len(events_data)} กิจกรรม!\n\n"
                ),
            )
        else:
            await self._send_message(
                event,
                line_bot_api,
                f"✅ Found {len(events_data)} event(s) but couldn't load first one.",
            )

        return True

    async def _prompt_scraped_event(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        event_data: dict[str, Any],
        current: int,
        total: int,
        header: str = "",
    ) -> None:
        date_obj = event_data.get("date")
        title = event_data.get("title", "Event")
        source = event_data.get("source_text", "")
        confidence = event_data.get("confidence", "medium")

        date_str = date_obj.strftime("%B %d, %Y") if date_obj else "Unknown"
        msg = header + (f"📅 Event {current}/{total}:\n\n📌 {title}\n📆 {date_str}\n")

        if source:
            source_preview = source[:50] + "..." if len(source) > 50 else source
            msg += f'📝 From: "{source_preview}"\n'

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

    async def _handle_scrape_review_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
    ) -> bool:
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "ใช่", "ok"]:
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
            has_more = calendar_session_manager.skip_scraped_event(chat_id)
            if has_more:
                next_event = calendar_session_manager.get_current_scraped_event(chat_id)
                if next_event:
                    current, total = calendar_session_manager.get_scrape_progress(chat_id)
                    await self._prompt_scraped_event(event, line_bot_api, next_event, current, total)
            else:
                calendar_session_manager.end_session(chat_id)
                await self._send_message(
                    event,
                    line_bot_api,
                    "✅ Finished processing scraped events.\n\nเสร็จสิ้นการประมวลผลกิจกรรมที่สแกน",
                )
            return True

        if text_lower in ["done", "skip all", "finish", "เสร็จ"]:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(event, line_bot_api, "✅ Scrape session ended.\n\nเสร็จสิ้นการสแกน")
            return True

        return False

    async def _handle_scrape_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
        calendar_service: CalendarService | None,
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

        event_data = calendar_session_manager.set_scrape_reminder_days(chat_id, reminder_days)

        added_title = ""
        if event_data and calendar_service and user_id:
            calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data["description"],
                reminder_days=event_data["reminder_days"],
                is_friend=event_data["is_friend"],
            )
            added_title = event_data["title"]

        has_more = calendar_session_manager.advance_scrape_index(chat_id)
        if has_more:
            next_event = calendar_session_manager.get_current_scraped_event(chat_id)
            if next_event:
                current, total = calendar_session_manager.get_scrape_progress(chat_id)
                header = f"✅ Added: {added_title}\nเพิ่มแล้ว: {added_title}\n\n" if added_title else ""
                await self._prompt_scraped_event(event, line_bot_api, next_event, current, total, header=header)
            else:
                await self._send_message(
                    event,
                    line_bot_api,
                    f"✅ Added: {added_title}\n\nเพิ่มแล้ว: {added_title}" if added_title else "✅ Done",
                )
        else:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event,
                line_bot_api,
                (
                    f"✅ Added: {added_title}\n\nเพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว!\nFinished adding all scraped events!"
                    if added_title
                    else "✅ Finished adding all scraped events!\n\nเพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว"
                ),
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
