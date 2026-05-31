from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional

from linebot.v3.messaging import (
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

from src.agents.base_agent import BaseAgent
from src.services.ai_review_service import (
    ai_review_service as default_ai_review_service,
)
from src.services.bot_identity_service import get_bot_identity_service
from src.services.calendar_service import calendar_service
from src.services.message_buffer_service import (
    BufferedMessage,
    message_buffer_service,
)
from src.services.staff_memory_service import StaffMemoryService

logger = logging.getLogger(__name__)

SAVE_OPTIONS = {"calendar", "memory", "both", "neither"}
STAFF_ANSWER = (
    "I am purely a hardworking assistant and at the service of all KPS "
    "employees."
)
PENDING_REVIEW_MESSAGE = (
    "Please finish the pending review in your DM before starting a new one."
)
IMPORTANT_THIS_WEEK_COMMANDS = {
    "whats important this week?",
    "whats important this week",
    "what's important this week?",
    "what's important this week",
    "important this week",
}
MEMORY_SAVE_FAILED_MESSAGE = (
    "I couldn't save that to memory right now. Please try again."
)


@dataclass
class PendingReview:
    original_text: str
    summary: str
    source_chat_id: str


class ReviewAgent(BaseAgent):
    def __init__(
        self,
        ai_review_service: Optional[Any] = None,
        message_buffer: Optional[Any] = None,
        staff_memory_service: Optional[StaffMemoryService] = None,
        calendar_service_instance: Optional[Any] = None,
        bot_user_id: Optional[str] = None,
    ):
        super().__init__(
            name="ReviewAgent",
            description="Explicit AI review and requester DM follow-up",
        )
        self._ai_review_service = (
            ai_review_service or default_ai_review_service
        )
        self._message_buffer = message_buffer or message_buffer_service
        self._staff_memory = staff_memory_service or StaffMemoryService(
            Path("./data/staff_memory/staff_memory.json")
        )
        self._calendar_service = calendar_service_instance or calendar_service
        self._bot_user_id = bot_user_id
        self._pending_reviews: dict[str, PendingReview] = {}

    def get_priority(self) -> int:
        return 8

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        user_id = getattr(getattr(event, "source", None), "user_id", None)
        if user_id and self._is_pending_save_response(event, text, user_id):
            return True

        command = self._parse_prefixed_command(text)
        return command in {
            "review",
            "who do you work for?",
            "who do you work for",
            *IMPORTANT_THIS_WEEK_COMMANDS,
        }

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        user_id = getattr(getattr(event, "source", None), "user_id", None)
        if not user_id:
            return False

        if self._is_pending_save_response(event, text, user_id):
            return await self._handle_pending_save_response(
                event, text, user_id, line_bot_api
            )

        command = self._parse_prefixed_command(text)
        if command == "review":
            if user_id in self._pending_reviews:
                await self._send_reply(
                    event,
                    line_bot_api,
                    PENDING_REVIEW_MESSAGE,
                )
                return True
            return await self._handle_review(
                event,
                text,
                line_bot_api,
                user_id,
            )

        if command in IMPORTANT_THIS_WEEK_COMMANDS:
            return await self._handle_important_this_week(
                event, line_bot_api, user_id
            )

        if command in {"who do you work for?", "who do you work for"}:
            await self._send_reply(event, line_bot_api, STAFF_ANSWER)
            return True

        return False

    def _parse_prefixed_command(self, text: str) -> str | None:
        prefix, rest = get_bot_identity_service().split_command_prefix(text)
        if not prefix:
            return None
        return rest.strip().lower()

    def _is_pending_save_response(
        self, event: MessageEvent, text: str, user_id: str
    ) -> bool:
        source = getattr(event, "source", None)
        if getattr(source, "type", None) != "user":
            return False
        return (
            user_id in self._pending_reviews
            and text.strip().lower() in SAVE_OPTIONS
        )

    async def _handle_review(
        self,
        event: MessageEvent,
        current_text: str,
        line_bot_api: MessagingApi,
        user_id: str,
    ) -> bool:
        chat_id = self._get_chat_id(event)
        last_message = self._get_last_non_english_message(
            chat_id,
            current_text,
        )
        if not last_message:
            await self._send_reply(
                event,
                line_bot_api,
                "I couldn't find a recent non-English message to review.",
            )
            return True

        summary = await self._ai_review_service.translate_and_summarize(
            last_message.text
        )
        if not summary:
            await self._send_reply(
                event,
                line_bot_api,
                "I couldn't complete the review right now.",
            )
            return True

        self._pending_reviews[user_id] = PendingReview(
            original_text=last_message.text,
            summary=summary,
            source_chat_id=chat_id,
        )

        await self._send_reply(
            event,
            line_bot_api,
            "I sent the review to your DM.",
        )
        await self._push_message(
            line_bot_api,
            user_id,
            (
                summary
                + "\n\nWould you like to add this to the calendar, memory, "
                "both, or neither?"
            ),
        )
        return True

    async def _handle_pending_save_response(
        self,
        event: MessageEvent,
        text: str,
        user_id: str,
        line_bot_api: MessagingApi,
    ) -> bool:
        choice = text.strip().lower()
        pending = self._pending_reviews.get(user_id)
        if not pending:
            return False

        notes: list[str] = []
        if choice in {"memory", "both"}:
            try:
                await self._staff_memory.add_item_async(
                    title=self._build_memory_title(pending.summary),
                    summary=pending.summary,
                    priority="P1",
                    due_date=None,
                    source_chat_id=pending.source_chat_id,
                    created_by=user_id,
                )
            except Exception as error:
                logger.warning("⚠️ Failed to save review summary to memory: %s", error)
                await self._send_reply(
                    event,
                    line_bot_api,
                    MEMORY_SAVE_FAILED_MESSAGE,
                )
                return True
            notes.append("saved to memory")

        if choice in {"calendar", "both"}:
            created = await self._try_add_calendar_event(user_id, pending)
            notes.append(created)

        if choice == "neither":
            notes.append("not saved")

        self._pending_reviews.pop(user_id, None)
        await self._send_reply(
            event,
            line_bot_api,
            f"Review update: {', '.join(notes)}.",
        )
        return True

    async def _handle_important_this_week(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        user_id: str,
    ) -> bool:
        today = date.today()
        week_end = today + timedelta(days=6)

        calendar_items = []
        for calendar_event in await self._calendar_service.get_user_events_async(user_id):
            if today <= calendar_event.event_date <= week_end:
                calendar_items.append(
                    (
                        "P2",
                        calendar_event.title,
                        calendar_event.event_date.isoformat(),
                    )
                )

        memory_records = await self._staff_memory.get_items_for_week_async(today)
        memory_items = [
            (item.priority, item.title, item.due_date or "")
            for item in memory_records
        ]

        combined = memory_items + calendar_items
        combined.sort(
            key=lambda item: (item[0], item[2] or "9999-12-31", item[1])
        )

        if combined:
            lines = [
                f"{priority} - {title}"
                for priority, title, _ in combined[:5]
            ]
            message = "Important this week:\n" + "\n".join(lines)
        else:
            message = "Nothing critical is recorded for this week."

        await self._send_reply(event, line_bot_api, message)
        return True

    async def _try_add_calendar_event(
        self, user_id: str, pending: PendingReview
    ) -> str:
        response = await self._ai_review_service.extract_calendar_candidates(
            [pending.original_text]
        )
        if not response:
            return "no calendar date found"

        try:
            candidates = json.loads(response)
        except json.JSONDecodeError:
            return "no calendar date found"

        if not isinstance(candidates, list) or not candidates:
            return "no calendar date found"

        candidate = candidates[0]
        event_date_raw = (
            candidate.get("date") if isinstance(candidate, dict) else None
        )
        title = candidate.get("title") if isinstance(candidate, dict) else None
        if not event_date_raw or not title:
            return "no calendar date found"

        try:
            event_date = date.fromisoformat(str(event_date_raw))
            await self._calendar_service.add_event_async(
                user_id=user_id,
                chat_id=pending.source_chat_id,
                title=str(title),
                event_date=event_date,
                description=pending.summary,
                reminder_days=[1, 0],
                is_friend=True,
            )
        except Exception:
            logger.warning(
                "ReviewAgent could not persist calendar event",
                exc_info=True,
            )
            return "no calendar date found"

        return "saved to calendar"

    def _build_memory_title(self, summary: str) -> str:
        first_line = (
            summary.strip().splitlines()[0]
            if summary.strip()
            else "Reviewed item"
        )
        return first_line[:50]

    def _get_last_non_english_message(
        self, chat_id: str, current_text: str
    ) -> BufferedMessage | None:
        recent_messages = self._message_buffer.get_recent_messages(
            chat_id,
            limit=20,
            exclude_user_id=self._bot_user_id,
        )
        for message in reversed(recent_messages):
            normalized = message.text.strip().lower()
            if normalized == current_text.strip().lower():
                continue
            if self._is_non_english_text(message.text):
                return message
        return None

    def _is_non_english_text(self, text: str) -> bool:
        if re.search(r"[\u0E00-\u0E7F]", text):
            return True
        return any(ord(char) > 127 and char.isalpha() for char in text)

    def _get_chat_id(self, event: MessageEvent) -> str:
        source = getattr(event, "source", None)
        if source is None:
            return "user_unknown"
        if getattr(source, "group_id", None):
            return f"group_{source.group_id}"
        if getattr(source, "room_id", None):
            return f"room_{source.room_id}"
        return f"user_{getattr(source, 'user_id', 'unknown')}"

    async def _send_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        message: str,
    ) -> None:
        if not getattr(event, "reply_token", None):
            return
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[
                    TextMessage(text=message, quickReply=None, quoteToken=None)
                ],
                notificationDisabled=False,
            ),
        )

    async def _push_message(
        self, line_bot_api: MessagingApi, user_id: str, message: str
    ) -> None:
        await asyncio.to_thread(
            line_bot_api.push_message,
            PushMessageRequest(
                to=user_id,
                messages=[
                    TextMessage(text=message, quickReply=None, quoteToken=None)
                ],
                notificationDisabled=False,
                customAggregationUnits=None,
            ),
        )
