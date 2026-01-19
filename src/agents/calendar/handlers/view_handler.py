"""
View Handler - Displays calendar events for the current chat.

This handler is responsible for showing calendar events with privacy isolation.
It's lazy-loaded only when view triggers are matched.
"""
import logging
from typing import Optional
from datetime import datetime
from zoneinfo import ZoneInfo
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi

from ..base_handler import CalendarHandler
from src.services.calendar_access_control import calendar_access_control
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import rate_limiter
from src.services.history_log_service import EventType, LogLevel, get_history_log

logger = logging.getLogger(__name__)

# Bangkok timezone
BANGKOK_TZ = ZoneInfo("Asia/Bangkok")

# View triggers
TRIGGERS_VIEW = [
    "zeus calendar",
    "zeus my calendar",
    "my events",
    "my reminders",
    "zeus events",
    "zeus reminders",
]


class ViewHandler(CalendarHandler):
    """
    Handler for viewing calendar events.
    
    Features:
    - Privacy-isolated event display (group vs. private)
    - Access control validation
    - Rate limiting
    - Event formatting with time calculations
    """
    
    def __init__(self):
        """Initialize the ViewHandler."""
        super().__init__(
            name="ViewHandler",
            description="Displays calendar events for the current chat"
        )
    
    def get_triggers(self) -> list:
        """Return view-related trigger phrases."""
        return TRIGGERS_VIEW
    
    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        """Check if this is a view events request."""
        return self._is_trigger(text, TRIGGERS_VIEW)
    
    async def handle(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        context: dict
    ) -> bool:
        """
        Display calendar events for the current chat.
        
        Args:
            event: LINE message event
            text: Message text
            line_bot_api: LINE messaging API
            chat_id: Chat identifier
            user_id: User identifier
            context: Shared context (must contain 'calendar_service')
            
        Returns:
            True if handled successfully
        """
        calendar_service = context.get("calendar_service")
        
        if not calendar_service or not user_id:
            await self._send_message(
                event, line_bot_api,
                "❌ Calendar service not available."
            )
            return True

        # Check access control
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
                    message="Access denied: attempted to view events",
                    level=LogLevel.WARNING,
                    chat_id=chat_id,
                    user_id=user_id,
                    agent_name=self.name,
                    metadata={"operation": "view_events"},
                )
            
            await self._send_message(
                event, line_bot_api,
                "❌ You don't have permission to view events in this chat."
            )
            return True

        # Check rate limiting
        is_admin = privilege_service.is_admin(user_id)
        if not rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin):
            await self._send_message(
                event, line_bot_api,
                "⏳ Calendar rate limit exceeded. Please try again later."
            )
            return True

        # CRITICAL PRIVACY: Use get_chat_events() to ensure isolation
        # Group events stay in that group, private entries stay in DMs
        events = calendar_service.get_chat_events(chat_id, requesting_user_id=user_id)

        if not events:
            # Determine chat context for messaging
            is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
            context_msg = "this group" if is_group else "your private calendar"
            
            await self._send_message(
                event, line_bot_api,
                f"📅 No events in {context_msg} yet!\n\n"
                "Say 'zeus add event' to create one.\n\n"
                "คุณยังไม่มีกิจกรรมในปฏิทิน\n"
                "พิมพ์ 'zeus add event' เพื่อเพิ่มกิจกรรม"
            )
            return True

        # Determine chat context for title
        is_group = chat_id.startswith("group_") or chat_id.startswith("room_")
        title = "Group Calendar" if is_group else "Your Calendar"
        
        # Format events list
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
            
            reminder_str = ", ".join([
                f"{d}d" for d in sorted(evt.reminder_days, reverse=True)
            ])
            
            msg_lines.append(f"{i}. {evt.title}")
            msg_lines.append(f"   📆 {date_str} {time_str}")
            msg_lines.append(f"   ⏰ Reminders: {reminder_str}")
            msg_lines.append("")

        if len(events) > 10:
            msg_lines.append(f"... and {len(events) - 10} more events")

        msg_lines.append("")
        msg_lines.append("💡 Say 'zeus remove event' to delete events")

        await self._send_message(event, line_bot_api, "\n".join(msg_lines))
        
        logger.info(f"✅ View events successful for {user_id} in {chat_id}")
        return True
