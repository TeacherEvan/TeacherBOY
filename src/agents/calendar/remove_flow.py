"""
Calendar Remove Flow - Handler for removing calendar events.
Extracted from calendar_agent.py for modular architecture.
"""

import logging
import re
from typing import Any
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    MessagingApi,
)
from linebot.v3.webhooks import MessageEvent

from src.services.calendar_access_control import calendar_access_control
from src.services.calendar_session_manager import calendar_session_manager
from src.services.history_log_service import EventType, LogLevel, get_history_log
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter

from .base_flow import CalendarFlowBase

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class RemoveFlow(CalendarFlowBase):
    """Handler for removing calendar events (privacy-isolated by chat)."""

    _DELETE_COMMAND_PATTERN = re.compile(r"^delete\s+([a-z0-9]{8,32})$")
    _CANCEL_ALIASES = {"cancel", "nevermind", "never mind", "ยกเลิก", "exit", "quit"}
    _LEGACY_PREVIEW_RESPONSES = {
        "yes",
        "y",
        "no",
        "n",
        "confirm",
        "keep",
        "ใช่",
        "ไม่",
        "done",
    }

    async def start_remove_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
    ) -> bool:
        """
        Start the remove event flow.

        Args:
            event: LINE message event
            line_bot_api: LINE Messaging API client
            chat_id: Normalized chat ID
            user_id: User ID making the request

        Returns:
            True if handled successfully
        """
        if not self._calendar_service or not user_id:
            await self.send_message(event, line_bot_api, "❌ Calendar service not available.")
            return True

        # Check access control
        can_view = await calendar_access_control.can_view_events(user_id, chat_id, line_bot_api)
        if not can_view:
            logger.warning(f"❌ Access denied: {user_id} cannot view events in {chat_id}")
            await self._log_access_denied(chat_id, user_id, "remove_events")
            await self.send_message(event, line_bot_api, "❌ You don't have permission to view events in this chat.")
            return True

        # Check rate limiting
        is_admin = privilege_service.is_admin(user_id)
        if not rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin):
            await self.send_message(event, line_bot_api, "⏳ Calendar rate limit exceeded. Please try again later.")
            return True

        # CRITICAL PRIVACY: Use get_chat_events() for isolation
        events = await self._calendar_service.get_chat_events_async(chat_id, requesting_user_id=user_id)

        removable_events = [evt for evt in events if getattr(evt, "user_id", None) == user_id]

        if not removable_events:
            is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
            if is_group:
                message = "📅 No events you can remove in this group.\n\nคุณไม่มีกิจกรรมของตัวเองในกลุ่มนี้ให้ลบ"
            else:
                message = "📅 No events in your calendar to remove.\n\nคุณไม่มีกิจกรรมที่จะลบ"

            await self.send_message(
                event,
                line_bot_api,
                message,
            )
            return True

        # Start removal flow with events
        events_data = [
            {
                "event_id": evt.event_id,
                "title": evt.title,
                "date": evt.event_date.strftime("%b %d"),
            }
            for evt in removable_events[:10]  # Max 10 for removal
        ]

        calendar_session_manager.start_removal_flow(chat_id, user_id, events_data)

        # Format and send selection message
        msg = self._format_removal_selection(events_data)
        await self.send_message(event, line_bot_api, msg)
        return True

    async def handle_removal_selection(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
    ) -> bool:
        """
        Handle event selection for removal.

        Args:
            event: LINE message event
            text: User's selection input
            line_bot_api: LINE Messaging API client
            chat_id: Normalized chat ID

        Returns:
            True if handled successfully
        """
        session = calendar_session_manager.get_session(chat_id)
        if not session:
            return False

        if not calendar_session_manager.is_session_owner(chat_id, user_id):
            await self.send_message(
                event,
                line_bot_api,
                "❌ Only the person who started this removal flow can change it.",
            )
            return True

        text_lower = text.lower().strip()

        if text_lower == "done":
            preview = calendar_session_manager.finalize_remove_selection(chat_id)
            if not preview:
                await self.send_message(
                    event,
                    line_bot_api,
                    "❌ Select at least one event before using 'done'.",
                )
                return True

            msg = self._format_removal_preview(preview["items"])
            actions = [
                {"label": "🗑️ Delete selected", "text": f"delete {preview['code']}"},
                {"label": "❌ Cancel", "text": "cancel"},
            ]
            await self.send_message_with_quick_reply(event, line_bot_api, msg, actions)
            return True

        updated_session = calendar_session_manager.apply_remove_selection(chat_id, text_lower)
        if updated_session is None:
            await self.send_message(
                event,
                line_bot_api,
                "❌ Invalid selection. Use exact commands: all, none, done, cancel, or numbers like 1,3.\n\n"
                "กรุณาใช้คำสั่งที่รองรับเท่านั้น เช่น all, none, done, cancel หรือ 1,3",
            )
            return True

        count = len(updated_session.selected_event_ids)
        msg = (
            f"🗂️ Selected {count} event{'s' if count != 1 else ''}.\n\n"
            + self._format_selected_items(updated_session)
            + "\n\nUse all, none, numbers like 1,3, done, or cancel."
        )
        await self.send_message(event, line_bot_api, msg)
        return True

    async def handle_removal_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: str | None,
    ) -> bool:
        """
        Handle removal confirmation.

        Args:
            event: LINE message event
            text: User's confirmation input
            line_bot_api: LINE Messaging API client
            chat_id: Normalized chat ID
            user_id: User ID making the request

        Returns:
            True if handled successfully
        """
        text_lower = text.lower().strip()

        if text_lower in self._CANCEL_ALIASES:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(event, line_bot_api, "✅ No events were removed.\n\nไม่มีกิจกรรมถูกลบ")
            return True

        if text_lower in self._LEGACY_PREVIEW_RESPONSES:
            await self.send_message(
                event, line_bot_api, "Reply with the preview action 'delete <code>' to confirm, or 'cancel' to stop."
            )
            return True

        match = self._DELETE_COMMAND_PATTERN.fullmatch(text_lower)
        if not match:
            await self.send_message(event, line_bot_api, "Reply with the preview action 'delete <code>' or 'cancel'.")
            return True

        confirmation = calendar_session_manager.validate_remove_confirmation(
            chat_id,
            user_id,
            match.group(1),
        )
        if not confirmation.get("ok"):
            reason = confirmation.get("reason")
            if reason == "wrong_owner":
                message = "❌ Only the person who started this removal flow can confirm it."
            elif reason in {"stale_revision", "invalid_state"}:
                message = "❌ This delete preview is stale or expired. Use the latest preview or start the remove flow again."
            else:
                message = "❌ This removal session is no longer valid. Start the remove flow again."
                calendar_session_manager.end_session(chat_id)
            await self.send_message(event, line_bot_api, message)
            return True

        if not self._calendar_service or not user_id:
            await self.send_message(
                event,
                line_bot_api,
                "❌ Something went wrong. Please try again.",
            )
            calendar_session_manager.end_session(chat_id)
            return True

        removed_count, failed_count = await self._calendar_service.remove_events_by_ids_async(
            confirmation["event_ids"],
            user_id,
        )

        calendar_session_manager.end_session(chat_id)

        msg = (
            f"✅ Removed {removed_count} event{'s' if removed_count != 1 else ''}!"
            + ("" if failed_count == 0 else f" (Failed: {failed_count})")
            + "\n\n"
            f"ลบ {removed_count} กิจกรรมเรียบร้อยแล้ว"
        )

        await self.send_message(event, line_bot_api, msg)
        return True

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _log_access_denied(self, chat_id: str, user_id: str, operation: str) -> None:
        """Log access denied event."""
        history_log = get_history_log()
        if history_log:
            await history_log.log(
                event_type=EventType.CALENDAR_ACCESS_DENIED,
                message=f"Access denied: attempted to {operation}",
                level=LogLevel.WARNING,
                chat_id=chat_id,
                user_id=user_id,
                agent_name="CalendarAgent",
                metadata={"operation": operation},
            )

    def _format_removal_selection(self, events_data: list[dict[str, Any]]) -> str:
        """Format the removal selection message."""
        msg_lines = [
            "🗑️ Select events to remove:",
            "",
        ]

        for i, evt in enumerate(events_data, 1):
            msg_lines.append(f"{i}. {evt['title']} ({evt['date']})")

        msg_lines.extend(
            [
                "",
                "Use numbers like 1,3 to select events.",
                "Commands: all, none, done, cancel.",
                "",
                "พิมพ์เลขที่ต้องการลบ เช่น 1,3",
                "คำสั่งที่รองรับ: all, none, done, cancel",
                "",
                "💡 Say 'cancel' to stop",
            ]
        )

        return "\n".join(msg_lines)

    def _format_selected_items(self, session: Any) -> str:
        selected = {event_id for event_id in session.selected_event_ids}
        if not selected:
            return "No events selected yet."

        lines = ["Selected:"]
        for index, event in enumerate(session.events_for_removal, start=1):
            if event["event_id"] in selected:
                lines.append(f"{index}. {event['title']} ({event['date']})")
        return "\n".join(lines)

    def _format_removal_preview(self, items: list[dict[str, Any]]) -> str:
        lines = [
            f"⚠️ Review the {len(items)} event{'s' if len(items) != 1 else ''} selected for deletion:",
            "",
        ]
        for index, item in enumerate(items, start=1):
            lines.append(f"{index}. {item['title']} ({item['date']})")
        lines.extend(
            [
                "",
                "Reply with the Delete button to remove exactly these events, or Cancel to keep them.",
            ]
        )
        return "\n".join(lines)


# Lazy loader for on-demand instantiation
_remove_flow_instance: RemoveFlow | None = None


def get_remove_flow(calendar_service: Any) -> RemoveFlow:
    """
    Get or create RemoveFlow instance (lazy loading).

    Args:
        calendar_service: CalendarService instance

    Returns:
        RemoveFlow handler instance
    """
    global _remove_flow_instance
    if _remove_flow_instance is None:
        _remove_flow_instance = RemoveFlow(calendar_service)
        logger.debug("📅 RemoveFlow initialized (lazy)")
    return _remove_flow_instance
