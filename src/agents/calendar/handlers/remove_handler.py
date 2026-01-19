"""
Remove Handler - Handles removing calendar events (multi-select).

This handler manages the removal of calendar events with multi-select capability.
"""
import logging
import re
from typing import Optional
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi, QuickReply, QuickReplyItem, MessageAction

from ..base_handler import CalendarHandler
from src.services.calendar_session_manager import (
    calendar_session_manager,
    CalendarState,
)
from src.services.calendar_service import CalendarService
from src.services.calendar_access_control import calendar_access_control
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter
from src.services.history_log_service import EventType, LogLevel, get_history_log

logger = logging.getLogger(__name__)

TRIGGERS_REMOVE = [
    "zeus remove event",
    "zeus delete event",
    "zeus remove reminder",
    "zeus delete reminder",
    "remove event",
    "delete event",
]


class RemoveHandler(CalendarHandler):
    """Handler for removing calendar events with multi-select."""

    def __init__(self) -> None:
        super().__init__(
            name="RemoveHandler",
            description="Removes calendar events with multi-select",
        )

    def get_triggers(self) -> list:
        return TRIGGERS_REMOVE

    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)
        session = calendar_session_manager.get_session(chat_id)
        if session and session.state in (
            CalendarState.AWAITING_REMOVAL_SELECTION,
            CalendarState.CONFIRMING_REMOVAL,
        ):
            return True

        return self._is_trigger(text, TRIGGERS_REMOVE)

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

        if self._is_trigger(text, TRIGGERS_REMOVE):
            return await self._start_remove_flow(
                event, line_bot_api, chat_id, user_id, calendar_service
            )

        if not session:
            return False

        if session.state == CalendarState.AWAITING_REMOVAL_SELECTION:
            return await self._handle_removal_selection(
                event, text, line_bot_api, chat_id
            )

        if session.state == CalendarState.CONFIRMING_REMOVAL:
            return await self._handle_removal_confirmation(
                event, text, line_bot_api, chat_id, user_id, calendar_service
            )

        return False

    async def _start_remove_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional[CalendarService],
    ) -> bool:
        if not calendar_service or not user_id:
            await self._send_message(
                event, line_bot_api, "❌ Calendar service not available."
            )
            return True

        can_view = await calendar_access_control.can_view_events(
            user_id, chat_id, line_bot_api
        )
        if not can_view:
            logger.warning(
                f"❌ Access denied: {user_id} cannot view events in {chat_id}"
            )
            history_log = get_history_log()
            if history_log:
                await history_log.log(
                    event_type=EventType.CALENDAR_ACCESS_DENIED,
                    message="Access denied: attempted to remove events",
                    level=LogLevel.WARNING,
                    chat_id=chat_id,
                    user_id=user_id,
                    agent_name=self.name,
                    metadata={"operation": "remove_events"},
                )
            await self._send_message(
                event,
                line_bot_api,
                "❌ You don't have permission to view events in this chat.",
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

        events = calendar_service.get_chat_events(chat_id, requesting_user_id=user_id)
        if not events:
            is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
            context = "this group" if is_group else "your calendar"
            await self._send_message(
                event,
                line_bot_api,
                f"📅 No events in {context} to remove.\n\n"
                "คุณไม่มีกิจกรรมที่จะลบ",
            )
            return True

        events_data = [
            {
                "event_id": evt.event_id,
                "title": evt.title,
                "date": evt.event_date.strftime("%b %d"),
            }
            for evt in events[:10]
        ]

        calendar_session_manager.start_removal_flow(chat_id, user_id, events_data)

        msg_lines = ["🗑️ Select events to remove:", ""]
        for i, evt in enumerate(events_data, 1):
            msg_lines.append(f"{i}. {evt['title']} ({evt['date']})")

        msg_lines.extend(
            [
                "",
                "Enter numbers separated by commas (e.g., 1,3,5)",
                "Or say 'all' to remove everything.",
                "",
                "พิมพ์เลขที่ต้องการลบ คั่นด้วยเครื่องหมาย ,",
                "หรือพิมพ์ 'all' เพื่อลบทั้งหมด",
                "",
                "💡 Say 'cancel' to stop",
            ]
        )

        await self._send_message(event, line_bot_api, "\n".join(msg_lines))
        return True

    async def _handle_removal_selection(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        session = calendar_session_manager.get_session(chat_id)
        if not session:
            return False

        events_for_removal = session.events_for_removal
        text_lower = text.lower().strip()
        selected_ids = []

        if text_lower == "all":
            selected_ids = [e["event_id"] for e in events_for_removal]
        else:
            try:
                parts = re.split(r"[,\s]+", text)
                for part in parts:
                    if part.isdigit():
                        idx = int(part) - 1
                        if 0 <= idx < len(events_for_removal):
                            selected_ids.append(events_for_removal[idx]["event_id"])
            except Exception:
                pass

            if not selected_ids:
                await self._send_message(
                    event,
                    line_bot_api,
                    "❌ Invalid selection. Enter numbers (e.g., 1,3) or 'all'.\n\n"
                    "กรุณาใส่ตัวเลข (เช่น 1,3) หรือ 'all'",
                )
                return True

        calendar_session_manager.set_removal_selection(chat_id, selected_ids)

        count = len(selected_ids)
        msg = (
            f"⚠️ Remove {count} event{'s' if count > 1 else ''}?\n\n"
            "This cannot be undone!\n\n"
            "Are you sure? (yes/no)\n\n"
            f"ต้องการลบ {count} กิจกรรม? (yes/no)"
        )

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="✅ Yes, delete", text="yes"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="❌ No, keep", text="no"),
                ),
            ]
        )

        await self._send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        return True

    async def _handle_removal_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional[CalendarService],
    ) -> bool:
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "ใช่", "delete", "confirm"]:
            event_ids = calendar_session_manager.get_removal_event_ids(chat_id)
            if not event_ids or not calendar_service or not user_id:
                await self._send_message(
                    event, line_bot_api, "❌ Something went wrong. Please try again."
                )
                calendar_session_manager.end_session(chat_id)
                return True

            removed_count, failed_count = calendar_service.remove_events_by_ids(
                event_ids, user_id
            )
            calendar_session_manager.end_session(chat_id)

            msg = (
                f"✅ Removed {removed_count} event{'s' if removed_count != 1 else ''}!"
                + ("" if failed_count == 0 else f" (Failed: {failed_count})")
                + "\n\n"
                f"ลบ {removed_count} กิจกรรมเรียบร้อยแล้ว"
            )
            await self._send_message(event, line_bot_api, msg)
            return True

        if text_lower in ["no", "n", "ไม่", "keep"]:
            calendar_session_manager.end_session(chat_id)
            await self._send_message(
                event, line_bot_api, "✅ No events were removed.\n\nไม่มีกิจกรรมถูกลบ"
            )
            return True

        await self._send_message(
            event, line_bot_api, "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no"
        )
        return True

    def _get_chat_id(self, event: MessageEvent) -> str:
        if event.source and getattr(event.source, "group_id", None):
            return f"group_{getattr(event.source, 'group_id')}"
        if event.source and getattr(event.source, "room_id", None):
            return f"room_{getattr(event.source, 'room_id')}"
        if event.source and getattr(event.source, "user_id", None):
            return f"user_{getattr(event.source, 'user_id')}"
        return "user_unknown"
