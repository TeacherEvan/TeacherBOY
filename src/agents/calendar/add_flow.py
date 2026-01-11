"""Add flow handler for calendar agent.

Handles the multi-step event creation flow:
- Date input with smart bulk detection
- Title input
- Description input
- Reminder days selection
- Confirmation

Uses lazy loading pattern for on-demand instantiation.
"""

import re
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List, TYPE_CHECKING

from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)

from .base_flow import CalendarFlowBase
from .states import CalendarState
from src.services.calendar_session_manager import calendar_session_manager

if TYPE_CHECKING:
    from src.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

# Lazy singleton
_add_flow_instance: Optional["AddFlow"] = None


def get_add_flow() -> "AddFlow":
    """Get or create the AddFlow singleton (lazy loading)."""
    global _add_flow_instance
    if _add_flow_instance is None:
        _add_flow_instance = AddFlow()
    return _add_flow_instance


class AddFlow(CalendarFlowBase):
    """Handler for multi-step event creation flow."""

    async def start_add_flow(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional["CalendarService"] = None,
    ) -> bool:
        """Start the manual add event flow."""
        if not user_id:
            await self.send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        # Start session in AWAITING_DATE state
        is_friend = await self._check_is_friend(event, line_bot_api)
        calendar_session_manager.start_add_flow(chat_id, user_id, is_friend)

        msg = (
            "📅 Add New Event\n\n"
            "Step 1/4: Enter the event date\n\n"
            "Supported formats:\n"
            "• Jan 15, 2026\n"
            "• 15/01/2026\n"
            "• 2026-01-15\n"
            "• tomorrow\n"
            "• next week\n\n"
            "💡 TIP: Paste multiple events and I'll extract them automatically!\n\n"
            "กรุณาใส่วันที่ของกิจกรรม"
        )

        await self.send_message(event, line_bot_api, msg)
        return True

    async def handle_date_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        """Handle date input with intelligent bulk detection."""
        from src.services.date_extraction_service import date_extraction_service

        # Check if this looks like bulk date paste
        if self._looks_like_bulk_dates(text):
            logger.info("🔍 Detected bulk date input, switching to extraction flow")
            session = calendar_session_manager.get_session(chat_id)
            if not session:
                return False
            user_id = session.user_id

            # End current session
            calendar_session_manager.end_session(chat_id)

            # Start extraction flow
            is_friend = getattr(session, "is_friend", False)
            calendar_session_manager.start_scrape_flow(
                chat_id, user_id, [text], is_friend
            )

            # Extract dates using AI
            try:
                events = await date_extraction_service.extract_events_from_messages([text])

                if not events:
                    await self.send_message(
                        event, line_bot_api,
                        "🤔 I see you pasted event details, but I couldn't extract any dates.\n\n"
                        "Please try using 'zeus scrape' or enter a single date.\n\n"
                        "ฉันเห็นว่าคุณวางรายละเอียดกิจกรรม แต่ไม่สามารถดึงวันที่ได้"
                    )
                    calendar_session_manager.end_session(chat_id)
                    return True

                # Convert to dicts and store
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

                # Import scrape flow to prompt
                from .scrape_flow import get_scrape_flow
                scrape_flow = get_scrape_flow()

                first_event = calendar_session_manager.get_current_scraped_event(chat_id)
                if first_event:
                    await scrape_flow.prompt_scraped_event(
                        event, line_bot_api, first_event, 1, len(events_data),
                        header=f"✨ I extracted {len(events_data)} event(s) from your input!\n\n"
                    )
                return True

            except Exception as e:
                logger.error(f"❌ Bulk date extraction failed: {e}", exc_info=True)
                await self.send_message(
                    event, line_bot_api,
                    "❌ Failed to process bulk dates. Please try 'zeus scrape' or enter one date at a time."
                )
                calendar_session_manager.end_session(chat_id)
                return True

        # Standard single date parsing
        parsed_date = self.parse_date(text)

        if not parsed_date:
            await self.send_message(
                event, line_bot_api,
                "❌ I couldn't understand that date.\n\n"
                "Try formats like:\n"
                "• Jan 15, 2025\n"
                "• 15/01/2025\n"
                "• 2025-01-15\n"
                "• tomorrow\n"
                "• next week\n\n"
                "💡 TIP: Paste multiple events? I'll extract them automatically!\n\n"
                "ไม่เข้าใจวันที่ กรุณาลองอีกครั้ง"
            )
            return True

        # Check if date is in the past
        if not self.validate_future_date(parsed_date):
            await self.send_message(
                event, line_bot_api,
                "❌ That date is in the past!\n\n"
                "Please enter a future date.\n\n"
                "วันที่ที่ระบุผ่านไปแล้ว กรุณาใส่วันที่ในอนาคต"
            )
            return True

        # Update session
        calendar_session_manager.set_pending_date(chat_id, parsed_date)

        date_str = parsed_date.strftime("%B %d, %Y")
        msg = (
            f"✅ Date: {date_str}\n\n"
            "Step 2/4: What's the event title?\n\n"
            "Enter a short title (e.g., 'Doctor appointment')\n\n"
            "พิมพ์ชื่อกิจกรรม"
        )

        await self.send_message(event, line_bot_api, msg)
        return True

    async def handle_title_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        """Handle title input."""
        title = text.strip()[:100]  # Max 100 chars

        if len(title) < 2:
            await self.send_message(
                event, line_bot_api,
                "❌ Title is too short. Please enter at least 2 characters.\n\n"
                "ชื่อสั้นเกินไป กรุณาใส่อย่างน้อย 2 ตัวอักษร"
            )
            return True

        calendar_session_manager.set_pending_title(chat_id, title)

        msg = (
            f"✅ Title: {title}\n\n"
            "Step 3/4: Add a description (optional)\n\n"
            "Enter details or say 'skip' to continue.\n\n"
            "ใส่รายละเอียดเพิ่มเติม หรือพิมพ์ 'skip' เพื่อข้าม"
        )

        await self.send_message(event, line_bot_api, msg)
        return True

    async def handle_description_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        """Handle description input."""
        description = "" if self.is_skip_command(text) else text.strip()[:500]

        calendar_session_manager.set_pending_description(chat_id, description)

        # Show reminder options with Quick Reply
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

        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="7 days", text="7")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="3 days", text="3")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="1 day", text="1")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="All", text="all")),
        ])

        await self.send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )
        return True

    async def handle_reminder_days_input(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
    ) -> bool:
        """Handle reminder days selection."""
        text_lower = text.lower().strip()

        reminder_days = []

        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 0]
        elif text_lower in ["3", "3 days"]:
            reminder_days = [3, 0]
        elif text_lower in ["1", "1 day"]:
            reminder_days = [1, 0]
        else:
            # Try to parse custom input like "7,3,1"
            try:
                parts = re.split(r"[,\s]+", text_lower)
                for part in parts:
                    if part.isdigit():
                        day = int(part)
                        if 0 <= day <= 30:
                            reminder_days.append(day)
            except:
                pass

            if not reminder_days:
                await self.send_message(
                    event, line_bot_api,
                    "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                    "กรุณาเลือก 7, 3, 1 หรือ all"
                )
                return True

        # Ensure 0 (day-of) is always included
        if 0 not in reminder_days:
            reminder_days.append(0)

        calendar_session_manager.set_pending_reminder_days(chat_id, reminder_days)

        # Get full event data for confirmation
        session = calendar_session_manager.get_session(chat_id)
        if not session:
            return False

        date_str = session.pending_date.strftime("%B %d, %Y") if session.pending_date else "N/A"
        reminder_str = ", ".join([f"{d} days" if d > 0 else "day-of" for d in sorted(reminder_days, reverse=True)])

        msg = (
            "📝 Please confirm your event:\n\n"
            f"📆 Date: {date_str}\n"
            f"📌 Title: {session.pending_title}\n"
            f"📝 Description: {session.pending_description or '(none)'}\n"
            f"⏰ Reminders: {reminder_str}\n\n"
            "Is this correct? (yes/no)\n\n"
            "ข้อมูลถูกต้องไหม? (yes/no)"
        )

        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="✅ Yes", text="yes")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="❌ No", text="no")),
        ])

        await self.send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )
        return True

    async def handle_add_confirmation(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional["CalendarService"] = None,
    ) -> bool:
        """Handle event creation confirmation."""
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "ใช่", "ok", "confirm"]:
            # Get event data
            event_data = calendar_session_manager.get_pending_event_data(chat_id)
            if not event_data or not calendar_service or not user_id:
                await self.send_message(
                    event, line_bot_api,
                    "❌ Something went wrong. Please try again."
                )
                calendar_session_manager.end_session(chat_id)
                return True

            # Create the event
            new_event = calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data["description"],
                reminder_days=event_data["reminder_days"],
                is_friend=event_data["is_friend"]
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

            await self.send_message(event, line_bot_api, msg)
            return True

        elif text_lower in ["no", "n", "ไม่"]:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "❌ Event creation cancelled.\n\n"
                "Say 'zeus add event' to try again.\n\n"
                "ยกเลิกแล้ว พิมพ์ 'zeus add event' เพื่อลองใหม่"
            )
            return True
        else:
            await self.send_message(
                event, line_bot_api,
                "Please answer yes or no.\n\nกรุณาตอบ yes หรือ no"
            )
            return True

    def _looks_like_bulk_dates(self, text: str) -> bool:
        """
        Detect if text looks like bulk date paste.
        
        Patterns detected:
        - Multiple lines with dates
        - "ZEUS OBSERVES" AI analysis output
        - Multiple date patterns in one message
        """
        lines = text.strip().split('\n')

        # Multiple lines is a strong indicator
        if len(lines) >= 3:
            return True

        # Check for Zeus analysis output
        if "ZEUS OBSERVES" in text.upper() or "DETECTED DATES" in text.upper():
            return True

        # Count date-like patterns
        date_pattern = re.compile(
            r'\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|'  # DD/MM/YYYY, MM/DD/YYYY
            r'\d{4}[/-]\d{1,2}[/-]\d{1,2}|'  # YYYY-MM-DD
            r'(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2}|'  # Jan 15
            r'\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*)\b',  # 15 Jan
            re.IGNORECASE
        )
        matches = date_pattern.findall(text)
        if len(matches) >= 2:
            return True

        return False

    async def _check_is_friend(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Check if user is a friend of the bot."""
        import asyncio
        from linebot.v3.messaging.exceptions import ApiException

        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            return False

        try:
            await asyncio.to_thread(line_bot_api.get_profile, user_id)
            return True
        except ApiException:
            return False
        except Exception:
            return False
