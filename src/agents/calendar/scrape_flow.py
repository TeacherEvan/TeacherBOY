"""Scrape flow handler for calendar agent.

Handles the "zeus scrape" flow for extracting dates from chat messages:
- Message buffer retrieval
- AI date extraction
- Event review and confirmation
- Bulk add functionality

Uses lazy loading pattern for on-demand instantiation.
"""

import re
import logging
from datetime import datetime, date
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
from src.services.message_buffer_service import message_buffer_service

if TYPE_CHECKING:
    from src.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

# Lazy singleton
_scrape_flow_instance: Optional["ScrapeFlow"] = None


def get_scrape_flow() -> "ScrapeFlow":
    """Get or create the ScrapeFlow singleton (lazy loading)."""
    global _scrape_flow_instance
    if _scrape_flow_instance is None:
        _scrape_flow_instance = ScrapeFlow()
    return _scrape_flow_instance


class ScrapeFlow(CalendarFlowBase):
    """Handler for extracting dates from recent chat messages."""

    async def handle_scrape_trigger(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """
        Handle "zeus scrape" trigger.
        
        Retrieves recent messages from buffer, extracts dates using AI,
        and guides user through adding events.
        """
        from src.services.date_extraction_service import date_extraction_service

        if not user_id:
            await self.send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        # Parse optional scan depth parameter (e.g., "zeus scrape 20")
        scan_limit = 10  # Default
        text_lower = text.lower().strip()
        match = re.match(r"zeus\s+(?:scrape|scan)(?:\s+(\d+))?", text_lower)
        if match and match.group(1):
            try:
                requested_limit = int(match.group(1))
                scan_limit = max(1, min(requested_limit, 50))  # Clamp to 1-50
                logger.info(f"📊 User requested scan depth: {scan_limit}")
            except ValueError:
                pass

        # Get recent messages from buffer
        messages = message_buffer_service.get_message_texts(chat_id, limit=scan_limit)

        if not messages:
            await self.send_message(
                event, line_bot_api,
                "📭 No recent messages found to scan.\n\n"
                "💡 I can only scan messages from the last 24 hours.\n"
                "ฉันสามารถสแกนเฉพาะข้อความจาก 24 ชั่วโมงที่ผ่านมา\n\n"
                "Try 'zeus add [date] [title]' to add events directly."
            )
            return True

        logger.info(f"🔍 Scanning {len(messages)} messages for chat {chat_id}")

        # Check friendship status
        is_friend = await self._check_is_friend(event, line_bot_api)

        # Start scrape flow
        calendar_session_manager.start_scrape_flow(
            chat_id, user_id, messages, is_friend
        )

        # Extract dates using AI
        try:
            events = await date_extraction_service.extract_events_from_messages(messages)
        except Exception as e:
            logger.error(f"❌ Date extraction failed: {e}", exc_info=True)
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "❌ Failed to scan messages. Please try again.\n\n"
                "สแกนข้อความไม่สำเร็จ กรุณาลองใหม่"
            )
            return True

        if not events:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "📭 No dates or events found in recent messages.\n\n"
                "ไม่พบวันที่หรือกิจกรรมในข้อความล่าสุด\n\n"
                "💡 Try 'zeus add [date] [title]' to add directly."
            )
            return True

        # Convert ExtractedEvent objects to dicts
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

        # Store extracted events and move to review state
        calendar_session_manager.set_scraped_events(chat_id, events_data)

        # Prompt for first event
        first_event = calendar_session_manager.get_current_scraped_event(chat_id)
        if first_event:
            await self.prompt_scraped_event(
                event, line_bot_api, first_event, 1, len(events_data),
                header=f"🔍 Scanned {len(messages)} messages - found {len(events_data)} event(s)!\nสแกน {len(messages)} ข้อความ - พบ {len(events_data)} กิจกรรม!\n\n"
            )
        else:
            await self.send_message(
                event, line_bot_api,
                f"✅ Found {len(events_data)} event(s) but couldn't load first one."
            )

        return True

    async def prompt_scraped_event(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        event_data: Dict[str, Any],
        current: int,
        total: int,
        header: str = ""
    ) -> None:
        """Prompt user about a scraped event."""
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

        # Visual confidence indicator
        confidence_emoji = "🟢" if confidence == "high" else "🟡" if confidence == "medium" else "🔴"
        msg += f"{confidence_emoji} Confidence: {confidence.title()}\n\n"
        msg += "Add this to calendar? (yes/no/add all/skip all)"

        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="✅ Yes", text="yes")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="⏭️ Skip", text="no")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="➕ Add All", text="add all")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="🚫 Skip All", text="done")),
        ])

        await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)

    async def handle_scrape_review_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """Handle user response during scrape review."""
        text_lower = text.lower().strip()

        if text_lower in ["yes", "y", "ใช่", "ok"]:
            # Accept this event, ask for reminder days
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

                quick_reply = QuickReply(items=[
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="7 days", text="7")),
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="3 days", text="3")),
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="1 day", text="1")),
                    QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="All", text="all")),
                ])

                await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
            return True

        elif text_lower in ["no", "n", "ไม่", "skip"]:
            # Skip this event, move to next
            has_more = calendar_session_manager.skip_scraped_event(chat_id)
            if has_more:
                next_event = calendar_session_manager.get_current_scraped_event(chat_id)
                if next_event:
                    current, total = calendar_session_manager.get_scrape_progress(chat_id)
                    await self.prompt_scraped_event(
                        event, line_bot_api, next_event, current, total
                    )
            else:
                calendar_session_manager.end_session(chat_id)
                await self.send_message(
                    event, line_bot_api,
                    "✅ Finished processing scraped events.\n\n"
                    "เสร็จสิ้นการประมวลผลกิจกรรมที่สแกน"
                )
            return True

        elif text_lower in ["done", "skip all", "finish", "เสร็จ"]:
            # End scrape flow
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                "✅ Scrape session ended.\n\nเสร็จสิ้นการสแกน"
            )
            return True

        elif text_lower in ["add all", "all", "ทั้งหมด"]:
            # Add all remaining events with default reminder settings
            await self.handle_add_all_scraped_events(event, line_bot_api, chat_id, user_id)
            return True

        return False

    async def handle_scrape_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional["CalendarService"] = None,
    ) -> bool:
        """Handle reminder days selection for scraped event."""
        text_lower = text.lower().strip()

        # Parse reminder days
        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 3, 1, 0]  # Always include all reminders
        elif text_lower in ["3", "3 days"]:
            reminder_days = [7, 3, 1, 0]  # Always include all reminders
        elif text_lower in ["1", "1 day"]:
            reminder_days = [7, 3, 1, 0]  # Always include all reminders
        else:
            await self.send_message(
                event, line_bot_api,
                "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                "กรุณาเลือก 7, 3, 1 หรือ all"
            )
            return True

        # Get event data with reminder days
        event_data = calendar_session_manager.set_scrape_reminder_days(chat_id, reminder_days)

        added_title = ""
        if event_data and calendar_service and user_id:
            # Create the event
            calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=event_data["title"],
                event_date=event_data["date"],
                description=event_data["description"],
                reminder_days=event_data["reminder_days"],
                is_friend=event_data["is_friend"]
            )
            added_title = event_data["title"]

        # Move to next event
        has_more = calendar_session_manager.advance_scrape_index(chat_id)
        if has_more:
            next_event = calendar_session_manager.get_current_scraped_event(chat_id)
            if next_event:
                current, total = calendar_session_manager.get_scrape_progress(chat_id)
                header = f"✅ Added: {added_title}\nเพิ่มแล้ว: {added_title}\n\n" if added_title else ""
                await self.prompt_scraped_event(
                    event, line_bot_api, next_event, current, total, header=header
                )
            else:
                await self.send_message(
                    event, line_bot_api,
                    f"✅ Added: {added_title}\n\nเพิ่มแล้ว: {added_title}" if added_title else "✅ Done"
                )
        else:
            calendar_session_manager.end_session(chat_id)
            await self.send_message(
                event, line_bot_api,
                f"✅ Added: {added_title}\n\n"
                f"เพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว!\n"
                "Finished adding all scraped events!" if added_title else
                "✅ Finished adding all scraped events!\n\n"
                "เพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว"
            )

        return True

    async def handle_add_all_scraped_events(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional["CalendarService"] = None,
    ) -> None:
        """Add all remaining scraped events with default reminder settings."""
        # Get calendar service from import if not provided
        if not calendar_service:
            from src.services.calendar_service import calendar_service as cal_svc
            calendar_service = cal_svc

        if not user_id or not calendar_service:
            await self.send_message(
                event, line_bot_api,
                "❌ Cannot add events - service unavailable."
            )
            calendar_session_manager.end_session(chat_id)
            return

        session = calendar_session_manager.get_session(chat_id)
        if not session or not session.scraped_events:
            await self.send_message(
                event, line_bot_api,
                "❌ No events to add."
            )
            calendar_session_manager.end_session(chat_id)
            return

        is_friend = getattr(session, "is_friend", False)
        default_reminder_days = [7, 3, 1, 0]  # 7, 3, 1 days before + day-of (strictly enforced)

        # Get all remaining events
        remaining_events = session.scraped_events[session.current_scrape_index:]
        added_count = 0
        failed_count = 0

        for event_data in remaining_events:
            try:
                event_date = event_data.get("date")
                if not isinstance(event_date, date):
                    raise ValueError("Missing or invalid event date")

                calendar_service.add_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    title=str(event_data.get("title", "Event")),
                    event_date=event_date,
                    description=str(event_data.get("description", "")),
                    reminder_days=default_reminder_days,
                    is_friend=is_friend
                )
                added_count += 1
                logger.info(f"✅ Batch added: {event_data.get('title')} on {event_data.get('date')}")
            except Exception as e:
                logger.error(f"❌ Failed to add event {event_data.get('title')}: {e}")
                failed_count += 1

        # End session
        calendar_session_manager.end_session(chat_id)

        # Send confirmation
        if added_count > 0:
            msg = (
                f"✅ Added {added_count} event(s) to calendar!\n"
                f"เพิ่ม {added_count} กิจกรรมแล้ว!\n\n"
                f"📌 Default reminders: 7, 3, 1 days before + day-of\n"
                f"📌 การแจ้งเตือน: 7, 3, 1 วันก่อน + วันนั้น"
            )
            if failed_count > 0:
                msg += f"\n\n⚠️ {failed_count} event(s) failed to add."
        else:
            msg = "❌ No events were added."

        await self.send_message(event, line_bot_api, msg)

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
