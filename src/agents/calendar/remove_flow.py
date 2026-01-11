"""
Calendar Remove Flow - Handler for removing calendar events.
Extracted from calendar_agent.py for modular architecture.
"""

import logging
import re
from datetime import datetime
from typing import Optional, Any, List, Dict
from zoneinfo import ZoneInfo

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)

from .base_flow import CalendarFlowBase
from src.services.calendar_session_manager import calendar_session_manager
from src.services.calendar_access_control import calendar_access_control
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter
from src.services.history_log_service import EventType, LogLevel, get_history_log

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class RemoveFlow(CalendarFlowBase):
    """Handler for removing calendar events (privacy-isolated by chat)."""

    async def start_remove_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
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
            await self.send_message(
                event, line_bot_api,
                "❌ Calendar service not available."
            )
            return True

        # Check access control
        can_view = await calendar_access_control.can_view_events(
            user_id, chat_id, line_bot_api
        )
        if not can_view:
            logger.warning(f"❌ Access denied: {user_id} cannot view events in {chat_id}")
            await self._log_access_denied(chat_id, user_id, "remove_events")
            await self.send_message(
                event, line_bot_api,
                "❌ You don't have permission to view events in this chat."
            )
            return True

        # Check rate limiting
        is_admin = privilege_service.is_admin(user_id)
        if not rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin):
            await self.send_message(
                event, line_bot_api,
                "⏳ Calendar rate limit exceeded. Please try again later."
            )
            return True

        # CRITICAL PRIVACY: Use get_chat_events() for isolation
        events = self._calendar_service.get_chat_events(
            chat_id, requesting_user_id=user_id
        )

        if not events:
            is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
            context = "this group" if is_group else "your calendar"

            await self.send_message(
                event, line_bot_api,
                f"📅 No events in {context} to remove.\n\n"
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

        events_for_removal = session.events_for_removal
        text_lower = text.lower().strip()

        selected_ids = self._parse_selection(text_lower, events_for_removal)

        if not selected_ids:
            await self.send_message(
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

        actions = [
            {"label": "✅ Yes, delete", "text": "yes"},
            {"label": "❌ No, keep", "text": "no"},
        ]
        await self.send_message_with_quick_reply(event, line_bot_api, msg, actions)
        return True

    async def handle_removal_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
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

        if text_lower in ["yes", "y", "ใช่", "delete", "confirm"]:
            event_ids = calendar_session_manager.get_removal_event_ids(chat_id)
            if not event_ids or not self._calendar_service or not user_id:
                await self.send_message(
                    event, line_bot_api,
                    "❌ Something went wrong. Please try again."
                )
                calendar_session_manager.end_session(chat_id)
                return True

            # Remove events
            removed_count, failed_count = self._calendar_service.remove_events_by_ids(
                event_ids, user_id
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

        elif text_lower in ["no", "n", "ไม่", "keep"]:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "✅ No events were removed.\n\nไม่มีกิจกรรมถูกลบ"
            )
            return True
        else:
            await self.send_message(
                event, line_bot_api,
                "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no"
            )
            return True

    # =========================================================================
    # Private Helpers
    # =========================================================================

    async def _log_access_denied(
        self, chat_id: str, user_id: str, operation: str
    ) -> None:
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

    def _format_removal_selection(self, events_data: List[Dict[str, Any]]) -> str:
        """Format the removal selection message."""
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

        return "\n".join(msg_lines)

    def _parse_selection(
        self,
        text: str,
        events_for_removal: List[Dict[str, Any]],
    ) -> List[str]:
        """
        Parse user's selection input.

        Args:
            text: Lowercased, stripped user input
            events_for_removal: List of event dicts with event_id

        Returns:
            List of selected event IDs
        """
        if text == "all":
            return [e["event_id"] for e in events_for_removal]

        selected_ids = []
        try:
            parts = re.split(r"[,\s]+", text)
            for part in parts:
                if part.isdigit():
                    idx = int(part) - 1  # Convert to 0-based
                    if 0 <= idx < len(events_for_removal):
                        selected_ids.append(events_for_removal[idx]["event_id"])
        except Exception:
            pass

        return selected_ids


# Lazy loader for on-demand instantiation
_remove_flow_instance: Optional[RemoveFlow] = None


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
