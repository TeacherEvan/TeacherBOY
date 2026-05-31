"""
Calendar View Flow - Handler for viewing calendar events.
Extracted from calendar_agent.py for modular architecture.
"""

import logging
from datetime import datetime
from typing import Optional, Any
from zoneinfo import ZoneInfo

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi

from .base_flow import CalendarFlowBase
from src.services.calendar_access_control import calendar_access_control
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter
from src.services.history_log_service import EventType, LogLevel, get_history_log

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class ViewFlow(CalendarFlowBase):
    """Handler for viewing calendar events (privacy-isolated by chat)."""

    async def handle_view_events(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """
        Show calendar events for current chat only (privacy-isolated).

        Group events stay in that group, private entries stay in DMs.

        Args:
            event: LINE message event
            text: Original message text
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
            await self._log_access_denied(chat_id, user_id, "view_events")
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

        # CRITICAL PRIVACY: Use get_chat_events() to ensure isolation
        events = await self._calendar_service.get_chat_events_async(
            chat_id, requesting_user_id=user_id
        )

        if not events:
            return await self._send_empty_calendar_message(
                event, line_bot_api, chat_id
            )

        # Format and send events list
        msg = self._format_events_list(events, chat_id)
        await self.send_message(event, line_bot_api, msg)
        return True

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

    async def _send_empty_calendar_message(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        """Send message when calendar is empty."""
        is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
        context_msg = "this group" if is_group else "your private calendar"

        await self.send_message(
            event, line_bot_api,
            f"📅 No events in {context_msg} yet!\n\n"
            "Say 'zeus add event' to create one.\n\n"
            "คุณยังไม่มีกิจกรรมในปฏิทิน\n"
            "พิมพ์ 'zeus add event' เพื่อเพิ่มกิจกรรม"
        )
        return True

    def _format_events_list(self, events: list, chat_id: str) -> str:
        """
        Format events list for display.

        Args:
            events: List of CalendarEvent objects
            chat_id: Chat ID for context

        Returns:
            Formatted message string
        """
        is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
        title = "Group Calendar" if is_group else "Your Calendar"

        msg_lines = [
            f"📅 {title} ({len(events)} event{'s' if len(events) != 1 else ''})",
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

            reminder_str = ", ".join(
                [f"{d}d" for d in sorted(evt.reminder_days, reverse=True)]
            )

            msg_lines.append(f"{i}. {evt.title}")
            msg_lines.append(f"   📆 {date_str} {time_str}")
            msg_lines.append(f"   ⏰ Reminders: {reminder_str}")
            msg_lines.append("")

        if len(events) > 10:
            msg_lines.append(f"... and {len(events) - 10} more events")

        msg_lines.append("")
        msg_lines.append("💡 Say 'zeus remove event' to delete events")

        return "\n".join(msg_lines)


# Lazy loader for on-demand instantiation
_view_flow_instance: Optional[ViewFlow] = None


def get_view_flow(calendar_service: Any) -> ViewFlow:
    """
    Get or create ViewFlow instance (lazy loading).

    Args:
        calendar_service: CalendarService instance

    Returns:
        ViewFlow handler instance
    """
    global _view_flow_instance
    if _view_flow_instance is None:
        _view_flow_instance = ViewFlow(calendar_service)
        logger.debug("📅 ViewFlow initialized (lazy)")
    return _view_flow_instance
