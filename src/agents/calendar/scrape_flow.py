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
from src.services.bot_identity_service import get_bot_identity_service
from src.services.calendar_session_manager import CalendarState, calendar_session_manager
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

    @staticmethod
    def _normalize_followup_text(text: str) -> str:
        """Normalize prefixed follow-up commands to bare scrape tokens."""
        normalized = (text or "").strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(normalized)
        return rest.lower().strip() if prefix else normalized.lower().strip()

    @staticmethod
    def _parse_scan_limit(text: str) -> int:
        """Parse an optional scrape depth from the current runtime command prefix."""
        scan_limit = 10
        normalized = (text or "").strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(normalized)
        candidate = rest if prefix else normalized
        match = re.match(r"^(?:scrape|scan)(?:\s+messages)?(?:\s+(\d+))?$", candidate.lower().strip())
        if match and match.group(1):
            try:
                requested_limit = int(match.group(1))
                scan_limit = max(1, min(requested_limit, 50))
                logger.info(f"📊 User requested scan depth: {scan_limit}")
            except ValueError:
                pass
        return scan_limit

    @staticmethod
    def _is_explicit_scrape_selection_followup(text: str) -> bool:
        normalized = ScrapeFlow._normalize_followup_text(text)
        return normalized in {"all", "none", "done", "cancel"} or bool(
            re.fullmatch(r"\d+(?:\s*,\s*\d+)*", normalized)
        )

    @staticmethod
    def _is_explicit_scrape_reminder_followup(text: str) -> bool:
        normalized = ScrapeFlow._normalize_followup_text(text)
        return normalized in {"all", "7", "3", "1", "7 days", "3 days", "1 day"}

    async def handle_scrape_trigger(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        discrete_mode: bool = False,
    ) -> bool:
        """
        Handle "zeus scrape" trigger.
        
        Retrieves recent messages from buffer, extracts dates using AI,
        and guides user through adding events.
        
        Args:
            event: LINE message event
            text: Message text
            line_bot_api: LINE Messaging API client
            chat_id: Chat ID (may be group for discrete scrape)
            user_id: User ID
            discrete_mode: If True, send all confirmations to user's DM instead of group
        """
        from src.services.date_extraction_service import date_extraction_service

        if not user_id:
            await self.send_message(
                event, line_bot_api,
                "❌ Cannot identify user."
            )
            return True

        scan_limit = self._parse_scan_limit(text)

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
        if discrete_mode and user_id:
            calendar_session_manager.set_discrete_scrape_target(chat_id, user_id)

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

        discrete_target = calendar_session_manager.get_discrete_scrape_target(chat_id)
        if events_data:
            await self.prompt_scrape_selection(
                event,
                line_bot_api,
                chat_id,
                header=(
                    f"🔍 Scanned {len(messages)} messages - found {len(events_data)} event(s)!\n"
                    f"สแกน {len(messages)} ข้อความ - พบ {len(events_data)} กิจกรรม!\n\n"
                ),
                discrete_target_user_id=discrete_target,
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
        header: str = "",
        discrete_target_user_id: Optional[str] = None,
        show_add_all: bool = False,
    ) -> None:
        """
        Prompt user about a scraped event.
        
        Args:
            event: LINE message event
            line_bot_api: LINE Messaging API client
            event_data: Event data dictionary
            current: Current event number
            total: Total events
            header: Optional header text
            discrete_target_user_id: If provided, send via push message to this user instead of replying
        """
        import asyncio
        from linebot.v3.messaging import PushMessageRequest, TextMessage as TextMsg
        
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
        
        # Send via push message if discrete mode, otherwise reply
        if discrete_target_user_id:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=discrete_target_user_id,
                        messages=[TextMsg(text=msg, quickReply=quick_reply, quoteToken=None)],
                        notificationDisabled=False,
                    )
                )
                logger.info(f"📨 Sent discrete scrape prompt to user {discrete_target_user_id}")
            except Exception as e:
                logger.error(f"❌ Failed to send discrete scrape push message: {e}", exc_info=True)
                await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        else:
            await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)

    async def prompt_scrape_selection(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        chat_id: str,
        header: str = "",
        discrete_target_user_id: Optional[str] = None,
    ) -> None:
        """Prompt the user to batch-select scraped events with explicit commands."""
        import asyncio
        from linebot.v3.messaging import PushMessageRequest, TextMessage as TextMsg

        session = calendar_session_manager.get_session(chat_id)
        if not session:
            await self.send_message(
                event,
                line_bot_api,
                "❌ This scrape session is no longer available. Start 'zeus scrape' again.",
            )
            return

        msg = self._format_scrape_selection(session, header)
        quick_reply = QuickReply(items=[
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="All", text="all")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="None", text="none")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="Done", text="done")),
            QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="Cancel", text="cancel")),
        ])

        if discrete_target_user_id:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=discrete_target_user_id,
                        messages=[TextMsg(text=msg, quickReply=quick_reply, quoteToken=None)],
                        notificationDisabled=False,
                    ),
                )
                logger.info(f"📨 Sent discrete scrape selection prompt to user {discrete_target_user_id}")
            except Exception as e:
                logger.error(f"❌ Failed to send discrete scrape selection push message: {e}", exc_info=True)
                await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
        else:
            await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)

    def _format_scrape_selection(self, session: Any, header: str = "") -> str:
        """Render the numbered scrape candidates and current selection state."""
        lines: List[str] = []
        if header:
            lines.append(header.rstrip())
        lines.extend([
            "🗂️ Select events to add:",
            "",
        ])

        for index, item in enumerate(session.scraped_events, start=1):
            date_obj = item.get("date") or item.get("event_date")
            date_text = self.format_date_display(date_obj) if isinstance(date_obj, date) else "Unknown date"
            marker = "✅" if index - 1 in session.selected_scraped_indices else "▫️"
            lines.append(f"{marker} {index}. {item.get('title', 'Event')} ({date_text})")

        selected_numbers = ", ".join(str(index + 1) for index in session.selected_scraped_indices)
        lines.extend([
            "",
            f"Selected: {selected_numbers if selected_numbers else 'none'}",
            "Use numbers like 1,3 to toggle events.",
            "Commands: all, none, done, cancel.",
        ])
        return "\n".join(lines)

    def _format_selected_scrape_preview(self, items: List[Dict[str, Any]]) -> str:
        """Render the exact selected scrape batch before the shared reminder choice."""
        lines = [
            "✅ Selected events to add:",
            "",
        ]

        for index, item in enumerate(items, start=1):
            date_obj = item.get("date") or item.get("event_date")
            date_text = self.format_date_display(date_obj) if isinstance(date_obj, date) else "Unknown date"
            lines.append(f"{index}. {item.get('title', 'Event')} ({date_text})")

        lines.extend([
            "",
            "When should I remind you for this batch?",
            "",
            "• 7 - 7 days before",
            "• 3 - 3 days before",
            "• 1 - 1 day before",
            "• all - All of the above",
            "",
            "(Day-of reminder is always included)",
        ])
        return "\n".join(lines)

    async def handle_scrape_review_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
    ) -> bool:
        """Handle user response during scrape batch selection."""
        active_chat_id = calendar_session_manager.resolve_discrete_scrape_chat_id(chat_id, user_id)
        session = calendar_session_manager.get_session(active_chat_id)
        if not session or session.state != CalendarState.SCRAPE_SELECTING:
            if (
                calendar_session_manager.had_recent_scrape_flow(chat_id, user_id)
                and self._is_explicit_scrape_selection_followup(text)
            ):
                await self.send_message(
                    event,
                    line_bot_api,
                    "❌ This scrape flow is stale or expired. Start 'zeus scrape' again.",
                )
                return True
            return False

        if not calendar_session_manager.is_session_owner(active_chat_id, user_id):
            await self.send_message(
                event,
                line_bot_api,
                "❌ Only the person who started this scrape flow can change it.",
            )
            return True

        text_lower = self._normalize_followup_text(text)

        if text_lower == "cancel":
            calendar_session_manager.end_session(active_chat_id)
            await self.send_message(
                event,
                line_bot_api,
                "✅ Scrape session canceled.\n\nยกเลิกการสแกนแล้ว",
            )
            return True

        if text_lower == "done":
            preview = calendar_session_manager.finalize_scrape_selection(active_chat_id)
            if not preview:
                await self.send_message(
                    event,
                    line_bot_api,
                    "❌ Select at least one event before using 'done'.",
                )
                return True

            msg = self._format_selected_scrape_preview(preview["items"])
            quick_reply = QuickReply(items=[
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="7 days", text="7")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="3 days", text="3")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="1 day", text="1")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="All", text="all")),
            ])
            await self.send_message_with_quick_reply(event, line_bot_api, msg, quick_reply)
            return True

        updated_session = calendar_session_manager.apply_scrape_selection(active_chat_id, text_lower)
        if updated_session is None:
            await self.send_message(
                event,
                line_bot_api,
                "❌ Invalid selection. Use exact commands: all, none, done, cancel, or numbers like 1,3.\n\n"
                "กรุณาใช้คำสั่งที่รองรับเท่านั้น เช่น all, none, done, cancel หรือ 1,3"
            )
            return True

        count = len(updated_session.selected_scraped_indices)
        header = (
            f"🗂️ Selected {count} event{'s' if count != 1 else ''}.\n\n"
            if count
            else "🗂️ No events selected yet.\n\n"
        )
        await self.prompt_scrape_selection(event, line_bot_api, active_chat_id, header=header)
        return True

    async def handle_scrape_reminder_response(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        calendar_service: Optional["CalendarService"] = None,
    ) -> bool:
        """Handle the shared reminder choice for the selected scrape batch."""
        text_lower = self._normalize_followup_text(text)
        active_chat_id = calendar_session_manager.resolve_discrete_scrape_chat_id(chat_id, user_id)
        calendar_service = calendar_service or self._calendar_service

        # Parse reminder days
        if text_lower == "all":
            reminder_days = [7, 3, 1, 0]
        elif text_lower in ["7", "7 days"]:
            reminder_days = [7, 0]
        elif text_lower in ["3", "3 days"]:
            reminder_days = [3, 0]
        elif text_lower in ["1", "1 day"]:
            reminder_days = [1, 0]
        else:
            await self.send_message(
                event, line_bot_api,
                "❌ Invalid selection. Please choose 7, 3, 1, or all.\n\n"
                "กรุณาเลือก 7, 3, 1 หรือ all"
            )
            return True

        confirmation = calendar_session_manager.validate_scrape_batch_confirmation(
            active_chat_id,
            user_id,
        )
        if not confirmation.get("ok"):
            reason = confirmation.get("reason")
            if reason == "wrong_owner":
                message = "❌ Only the person who started this scrape flow can confirm it."
            elif (
                reason == "missing_session"
                and calendar_session_manager.had_recent_scrape_flow(chat_id, user_id)
                and self._is_explicit_scrape_reminder_followup(text)
            ):
                message = "❌ This scrape preview is stale or expired. Start the scrape flow again."
            elif reason in {"stale_revision", "invalid_state"}:
                message = "❌ This scrape preview is stale or expired. Start the scrape flow again."
            elif reason == "no_selection":
                message = "❌ Select at least one event before choosing reminders."
            else:
                message = "❌ This scrape session is no longer valid. Start 'zeus scrape' again."
            await self.send_message(event, line_bot_api, message)
            return True

        if not calendar_service or not user_id:
            await self.send_message(
                event,
                line_bot_api,
                "❌ Cannot add events - service unavailable.",
            )
            calendar_session_manager.end_session(active_chat_id)
            return True

        notification_target_user_id = calendar_session_manager.get_discrete_scrape_target(active_chat_id)
        added_count = 0
        failed_count = 0

        for item in confirmation["items"]:
            event_date = item.get("date") or item.get("event_date")
            if not isinstance(event_date, date):
                failed_count += 1
                continue

            try:
                await calendar_service.add_event_async(
                    user_id=user_id,
                    chat_id=active_chat_id,
                    title=str(item.get("title", "Event from chat")),
                    event_date=event_date,
                    description=str(item.get("description", "")),
                    reminder_days=list(reminder_days),
                    is_friend=bool(confirmation.get("is_friend")),
                    notification_target_user_id=notification_target_user_id,
                )
                added_count += 1
            except Exception:
                logger.exception("❌ Failed to add scraped batch event")
                failed_count += 1

        calendar_session_manager.end_session(active_chat_id)

        if added_count > 0:
            await self.send_message(
                event, line_bot_api,
                f"✅ Added {added_count} selected event(s) to calendar!"
                + ("" if failed_count == 0 else f" (Failed: {failed_count})")
                + "\n\nเพิ่มกิจกรรมที่เลือกเรียบร้อยแล้ว"
            )
        else:
            await self.send_message(
                event,
                line_bot_api,
                "❌ No selected events were added.",
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

                notification_target_user_id = calendar_session_manager.get_discrete_scrape_target(chat_id)
                await calendar_service.add_event_async(
                    user_id=user_id,
                    chat_id=chat_id,
                    title=str(event_data.get("title", "Event")),
                    event_date=event_date,
                    description=str(event_data.get("description", "")),
                    reminder_days=default_reminder_days,
                    is_friend=is_friend,
                    notification_target_user_id=notification_target_user_id,
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
