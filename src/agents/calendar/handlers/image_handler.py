"""
Image Handler - Processes calendar events from image analysis.

This handler integrates with ImageAnalyzerAgent to process dates extracted
from images and add them to the calendar.
"""
import logging
from typing import Optional, Dict, Any, List
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi, QuickReply, QuickReplyItem, MessageAction

from ..base_handler import CalendarHandler
from src.services.calendar_session_manager import (
    calendar_session_manager,
    CalendarState,
)
from src.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)


class ImageHandler(CalendarHandler):
    """Handler for image-extracted calendar events."""

    def __init__(self) -> None:
        super().__init__(
            name="ImageHandler",
            description="Processes calendar events from image analysis",
        )

    def get_triggers(self) -> list:
        return []

    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)
        session = calendar_session_manager.get_session(chat_id)
        return bool(session and session.state == CalendarState.PROCESSING_EXTRACTED_DATES)

    async def handle(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        context: dict,
    ) -> bool:
        calendar_service: Optional[CalendarService] = context.get("calendar_service")
        session = calendar_session_manager.get_session(chat_id)

        if not session or session.state != CalendarState.PROCESSING_EXTRACTED_DATES:
            return False

        return await self._handle_extracted_date_response(
            event, text, line_bot_api, chat_id, user_id, calendar_service
        )

    async def start_extraction_flow_from_image(
        self,
        chat_id: str,
        user_id: str,
        extracted_dates: List[Dict[str, Any]],
        is_friend: bool,
        event: Optional[MessageEvent] = None,
        line_bot_api: Optional[MessagingApi] = None,
    ) -> None:
        calendar_session_manager.start_extraction_flow(
            chat_id, user_id, extracted_dates, is_friend
        )

        if event and line_bot_api and extracted_dates:
            current_date = calendar_session_manager.get_current_extracted_date(chat_id)
            if current_date:
                await self._prompt_extracted_date(
                    event,
                    line_bot_api,
                    current_date,
                    current=1,
                    total=len(extracted_dates),
                )

    async def _handle_extracted_date_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional[CalendarService],
    ) -> bool:
        text_lower = text.lower().strip()
        session = calendar_session_manager.get_session(chat_id)

        if not session:
            return False

        current_date = calendar_session_manager.get_current_extracted_date(chat_id)
        if not current_date:
            calendar_session_manager.end_session(chat_id)
            return False

        if text_lower in ["add all", "all", "yes all", "save all", "ทั้งหมด"]:
            remaining_count = len(session.extracted_dates) - session.current_extraction_index
            msg = (
                f"📅 Adding ALL {remaining_count} remaining event(s)\n\n"
                "Select reminder timing for all events:\n"
                "• 7 - 7 days before\n"
                "• 3 - 3 days before\n"
                "• 1 - 1 day before\n"
                "• all - All of the above\n\n"
                "(Day-of reminder is always included)\n\n"
                f"เลือกการแจ้งเตือนสำหรับทั้ง {remaining_count} กิจกรรม"
            )

            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="7 days", text="bulk:7"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="3 days", text="bulk:3"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="1 day", text="bulk:1"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="All", text="bulk:all"),
                    ),
                ]
            )

            await self._send_message_with_quick_reply(
                event, line_bot_api, msg, quick_reply
            )
            return True

        if text_lower.startswith("bulk:"):
            reminder_choice = text_lower.split(":", 1)[1]
            if reminder_choice == "all":
                reminder_days = [7, 3, 1, 0]
            else:
                try:
                    reminder_days = [int(reminder_choice), 0]
                except ValueError:
                    return False

            added_count = 0
            skipped_count = 0
            added_titles = []

            while session.current_extraction_index < len(session.extracted_dates):
                date_info = session.extracted_dates[session.current_extraction_index]

                if calendar_service and user_id:
                    is_duplicate = calendar_service.has_duplicate_event(
                        user_id=user_id,
                        chat_id=chat_id,
                        title=date_info["title"],
                        event_date=date_info["date"],
                    )

                    if is_duplicate:
                        logger.info(
                            f"⏩ Skipping duplicate: {date_info['title']} on {date_info['date']}"
                        )
                        skipped_count += 1
                    else:
                        try:
                            calendar_service.add_event(
                                user_id=user_id,
                                chat_id=chat_id,
                                title=date_info["title"],
                                event_date=date_info["date"],
                                description=date_info.get("description", ""),
                                reminder_days=reminder_days,
                                is_friend=session.pending_is_friend,
                                skip_duplicate_check=True,
                            )
                            added_count += 1
                            added_titles.append(date_info["title"])
                        except ValueError as exc:
                            logger.error(f"❌ Failed to add event: {exc}")
                            skipped_count += 1

                session.current_extraction_index += 1

            calendar_session_manager.end_session(chat_id)

            summary = f"✅ Added {added_count} event(s) to calendar!"
            if skipped_count > 0:
                summary += f" (⏩ {skipped_count} duplicate(s) skipped)"
            summary += "\n\n"

            if added_count <= 5:
                for i, title in enumerate(added_titles, 1):
                    summary += f"{i}. {title}\n"
            else:
                for i in range(min(3, len(added_titles))):
                    summary += f"{i+1}. {added_titles[i]}\n"
                if len(added_titles) > 4:
                    summary += f"... ({len(added_titles) - 4} more) ...\n"
                if added_titles:
                    summary += f"{len(added_titles)}. {added_titles[-1]}\n"

            if reminder_days:
                summary += (
                    f"\n🔔 Reminders: {', '.join(str(d) for d in sorted([d for d in reminder_days if d > 0], reverse=True))} days + day-of\n"
                )
            summary += "\nเพิ่มกิจกรรมทั้งหมดสำเร็จแล้ว!"

            await self._send_message(event, line_bot_api, summary)
            return True

        if text_lower in ["yes", "y", "ใช่", "add"]:
            msg = (
                "Choose reminder timing:\n"
                "• 7 - 7 days before\n"
                "• 3 - 3 days before\n"
                "• 1 - 1 day before\n"
                "• all - All of the above"
            )

            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="7 days", text="7"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="3 days", text="3"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="1 day", text="1"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="All", text="all"),
                    ),
                ]
            )

            await self._send_message_with_quick_reply(
                event, line_bot_api, msg, quick_reply
            )
            return True

        if text_lower in ["no", "n", "ไม่", "skip"]:
            has_more = calendar_session_manager.advance_extraction_index(chat_id)
            if has_more:
                next_date = calendar_session_manager.get_current_extracted_date(chat_id)
                if next_date:
                    current_idx = session.current_extraction_index + 1
                    total = len(session.extracted_dates)
                    await self._prompt_extracted_date(
                        event,
                        line_bot_api,
                        next_date,
                        current=current_idx,
                        total=total,
                    )
            else:
                calendar_session_manager.end_session(chat_id)
                await self._send_message(
                    event,
                    line_bot_api,
                    "✅ Finished processing dates.\n\nเสร็จสิ้นการประมวลผลวันที่",
                )
            return True

        if text_lower in ["7", "3", "1", "all"]:
            if text_lower == "all":
                reminder_days = [7, 3, 1, 0]
            else:
                reminder_days = [int(text_lower), 0]

            event_data = calendar_session_manager.set_extraction_reminder_days(
                chat_id, reminder_days
            )

            if event_data and calendar_service and user_id:
                is_duplicate = calendar_service.has_duplicate_event(
                    user_id=user_id,
                    chat_id=chat_id,
                    title=event_data["title"],
                    event_date=event_data["date"],
                )

                if is_duplicate:
                    logger.info(
                        f"⏩ Duplicate detected: {event_data['title']} on {event_data['date']}"
                    )
                    await self._send_message(
                        event,
                        line_bot_api,
                        f"⏩ Skipped: {event_data['title']} (duplicate)",
                    )
                else:
                    try:
                        calendar_service.add_event(
                            user_id=user_id,
                            chat_id=chat_id,
                            title=event_data["title"],
                            event_date=event_data["date"],
                            description=event_data["description"],
                            reminder_days=event_data["reminder_days"],
                            is_friend=event_data["is_friend"],
                            skip_duplicate_check=True,
                        )

                        await self._send_message(
                            event,
                            line_bot_api,
                            f"✅ Added: {event_data['title']}",
                        )
                    except ValueError as exc:
                        logger.error(f"❌ Failed to add event: {exc}")
                        await self._send_message(
                            event,
                            line_bot_api,
                            f"❌ Failed: {event_data['title']} ({str(exc)})",
                        )

            has_more = calendar_session_manager.advance_extraction_index(chat_id)
            if has_more:
                next_date = calendar_session_manager.get_current_extracted_date(chat_id)
                if next_date:
                    current_idx = session.current_extraction_index + 1
                    total = len(session.extracted_dates)
                    await self._prompt_extracted_date(
                        event,
                        line_bot_api,
                        next_date,
                        current=current_idx,
                        total=total,
                    )
            else:
                calendar_session_manager.end_session(chat_id)
                await self._send_message(
                    event,
                    line_bot_api,
                    "✅ Finished processing all dates!\n\nเพิ่มกิจกรรมทั้งหมดเรียบร้อยแล้ว",
                )
            return True

        return False

    async def _prompt_extracted_date(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        date_info: Dict[str, Any],
        current: Optional[int] = None,
        total: Optional[int] = None,
    ) -> None:
        date_obj = date_info.get("date")
        title = date_info.get("title", "Event")
        description = date_info.get("description", "")

        date_str = date_obj.strftime("%B %d, %Y") if date_obj else "Unknown"

        if current and total:
            msg = f"📅 Event {current}/{total}:\n\n"
        else:
            msg = "📅 Found event in image:\n\n"

        msg += (
            f"📌 {title}\n"
            f"📆 {date_str}\n"
        )

        if description:
            msg += f"📝 {description}\n"

        msg += "\nAdd to calendar?"

        quick_reply_items = [
            QuickReplyItem(
                type="action",
                imageUrl=None,
                action=MessageAction(label="✅ Yes", text="yes"),
            ),
            QuickReplyItem(
                type="action",
                imageUrl=None,
                action=MessageAction(label="⏭️ Skip", text="no"),
            ),
        ]

        if total and current and (total - current) > 0:
            remaining = total - current + 1
            quick_reply_items.append(
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(
                        label=f"➕ Add All ({remaining})", text="add all"
                    ),
                )
            )

        quick_reply = QuickReply(items=quick_reply_items)

        await self._send_message_with_quick_reply(
            event, line_bot_api, msg, quick_reply
        )

    def _get_chat_id(self, event: MessageEvent) -> str:
        if event.source and getattr(event.source, "group_id", None):
            return f"group_{getattr(event.source, 'group_id')}"
        if event.source and getattr(event.source, "room_id", None):
            return f"room_{getattr(event.source, 'room_id')}"
        if event.source and getattr(event.source, "user_id", None):
            return f"user_{getattr(event.source, 'user_id')}"
        return "user_unknown"
