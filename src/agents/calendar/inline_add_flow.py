"""
Calendar Inline Add Flow - Handler for "zeus add [date] [title]" syntax.
Extracted from calendar_agent.py for modular architecture.
"""

import logging
from datetime import datetime, date
from typing import Optional, Any, Dict
from zoneinfo import ZoneInfo

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi

from .base_flow import CalendarFlowBase
from src.services.calendar_session_manager import calendar_session_manager
from src.services.calendar_access_control import calendar_access_control
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter
from src.services.history_log_service import EventType, LogLevel, get_history_log

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")


class InlineAddFlow(CalendarFlowBase):
    """
    Handler for inline add syntax: "zeus add [date] [title]".
    
    This flow skips the interactive date/title prompts since both
    are provided in the command. Only asks for reminder preference.
    """

    async def handle_inline_add_trigger(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        parsed_data: Dict[str, Any],
    ) -> bool:
        """
        Handle "zeus add [date] [title]" inline trigger.

        Args:
            event: LINE message event
            line_bot_api: LINE Messaging API client
            chat_id: Normalized chat ID
            user_id: User ID making the request
            parsed_data: Dict with 'date' (date object) and 'title' (str)

        Returns:
            True if handled successfully
        """
        if not user_id:
            await self.send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        # Check access control
        can_create = await calendar_access_control.can_create_event(
            user_id, chat_id, line_bot_api
        )
        if not can_create:
            logger.warning(f"❌ Access denied: {user_id} cannot create events in {chat_id}")
            await self._log_access_denied(chat_id, user_id, "create_event_inline")
            await self.send_message(
                event, line_bot_api,
                "❌ You don't have permission to create events in this chat."
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

        event_date: date = parsed_data["date"]
        title: str = parsed_data["title"]

        # Validate date is in the future
        today = datetime.now(BANGKOK_TZ).date()
        if event_date < today:
            await self.send_message(
                event, line_bot_api,
                "❌ That date is in the past!\n\n"
                "Please use a future date.\n\n"
                "วันที่ที่ระบุผ่านไปแล้ว กรุณาใส่วันที่ในอนาคต"
            )
            return True

        # Check friendship status (for reminder delivery)
        is_friend = await self._check_friendship(event, line_bot_api)

        # Start inline add flow (skips date/title input)
        calendar_session_manager.start_inline_add_flow(
            chat_id=chat_id,
            user_id=user_id,
            event_date=event_date,
            title=title,
            description="",
            is_friend=is_friend,
        )

        # Prompt for reminder selection
        await self._prompt_reminder_selection(event, line_bot_api, title, event_date)
        return True

    async def handle_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """
        Handle reminder days selection for inline add.

        Args:
            event: LINE message event
            text: User's selection input
            line_bot_api: LINE Messaging API client
            chat_id: Normalized chat ID
            user_id: User ID making the request

        Returns:
            True if handled successfully
        """
        text_lower = text.lower().strip()

        # Parse reminder days
        reminder_days = self._parse_reminder_selection(text_lower)
        if reminder_days is None:
            await self.send_message(
                event, line_bot_api,
                "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                "กรุณาเลือก 7, 3, 1 หรือ all"
            )
            return True

        # Store reminder days (moves to CONFIRMING state)
        event_data = calendar_session_manager.set_inline_reminder_days(
            chat_id, reminder_days
        )

        if not event_data:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "❌ Something went wrong. Please try again."
            )
            return True

        # Show confirmation prompt
        await self._prompt_confirmation(event, line_bot_api, event_data)
        return True

    async def handle_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """
        Handle confirmation for inline add.

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

        if text_lower in ["yes", "y", "ใช่", "ok", "confirm"]:
            return await self._create_event(event, line_bot_api, chat_id, user_id)

        elif text_lower in ["no", "n", "ไม่"]:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "❌ Event creation cancelled.\n\n"
                "Say 'zeus add [date] [title]' to try again.\n\n"
                "ยกเลิกแล้ว"
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

    async def _check_friendship(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Check if user is a friend of the bot."""
        from linebot.v3.messaging.exceptions import ApiException
        import asyncio

        user_id = self.get_user_id(event)
        if not user_id:
            return False

        try:
            await asyncio.to_thread(line_bot_api.get_profile, user_id)
            return True
        except ApiException:
            return False
        except Exception:
            return False

    async def _prompt_reminder_selection(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        title: str,
        event_date: date,
    ) -> None:
        """Send reminder selection prompt."""
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

        actions = [
            {"label": "7 days", "text": "7"},
            {"label": "3 days", "text": "3"},
            {"label": "1 day", "text": "1"},
            {"label": "All", "text": "all"},
        ]
        await self.send_message_with_quick_reply(event, line_bot_api, msg, actions)

    def _parse_reminder_selection(self, text: str) -> Optional[list[int]]:
        """
        Parse reminder days from user input.

        Args:
            text: Lowercased, stripped user input

        Returns:
            List of reminder days, or None if invalid
        """
        if text == "all":
            return [7, 3, 1, 0]
        elif text in ["7", "7 days"]:
            return [7, 3, 1, 0]  # Always include all reminders
        elif text in ["3", "3 days"]:
            return [7, 3, 1, 0]  # Always include all reminders
        elif text in ["1", "1 day"]:
            return [7, 3, 1, 0]  # Always include all reminders
        else:
            return None

    async def _prompt_confirmation(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        event_data: Dict[str, Any],
    ) -> None:
        """Send confirmation prompt."""
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

        actions = self.get_yes_no_quick_replies()
        await self.send_message_with_quick_reply(event, line_bot_api, msg, actions)

    async def _create_event(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """Create the calendar event."""
        session = calendar_session_manager.get_session(chat_id)

        if (
            not session
            or not session.inline_event_data
            or not self._calendar_service
            or not user_id
        ):
            await self.send_message(
                event, line_bot_api,
                "❌ Something went wrong. Please try again."
            )
            calendar_session_manager.end_session(chat_id)
            return True

        # Create the event
        new_event = await self._calendar_service.add_event_async(
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

        await self.send_message(event, line_bot_api, msg)
        return True


# Lazy loader for on-demand instantiation
_inline_add_flow_instance: Optional[InlineAddFlow] = None


def get_inline_add_flow(calendar_service: Any) -> InlineAddFlow:
    """
    Get or create InlineAddFlow instance (lazy loading).

    Args:
        calendar_service: CalendarService instance

    Returns:
        InlineAddFlow handler instance
    """
    global _inline_add_flow_instance
    if _inline_add_flow_instance is None:
        _inline_add_flow_instance = InlineAddFlow(calendar_service)
        logger.debug("📅 InlineAddFlow initialized (lazy)")
    return _inline_add_flow_instance
