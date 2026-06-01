"""Registry-backed remove handler that delegates to the hardened RemoveFlow."""

import logging
import re
from typing import Optional

from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

from ..base_handler import CalendarHandler
from ..remove_flow import RemoveFlow
from src.services.bot_identity_service import get_bot_identity_service
from src.services.calendar_session_manager import (
    calendar_session_manager,
    CalendarState,
)
from src.services.calendar_service import CalendarService

logger = logging.getLogger(__name__)

TRIGGERS_REMOVE = [
    "zeus remove event",
    "zeus delete event",
    "zeus calendar remove",
    "zeus remove reminder",
    "zeus delete reminder",
    "remove event",
    "delete event",
]
REMOVE_SELECTION_PATTERN = re.compile(r"^\d+(?:\s*,\s*\d+)*$")
REMOVE_DELETE_PATTERN = re.compile(r"^delete\s+[a-z0-9]{8,32}$")
CANCEL_KEYWORDS = {"cancel", "nevermind", "never mind", "ยกเลิก", "exit", "quit"}


class RemoveHandler(CalendarHandler):
    """Handler for removing calendar events with multi-select."""

    def __init__(self) -> None:
        super().__init__(
            name="RemoveHandler",
            description="Removes calendar events with multi-select",
        )
        self._remove_flow = RemoveFlow()

    def get_triggers(self) -> list:
        return TRIGGERS_REMOVE

    def _is_explicit_remove_trigger(self, text: str) -> bool:
        text_lower = re.sub(r"\s+", " ", text.lower().strip())
        identity_service = get_bot_identity_service()

        for trigger in TRIGGERS_REMOVE:
            for variant in identity_service.expand_prefixed_trigger(trigger):
                if text_lower.startswith(variant):
                    return True
        return False

    def _is_remove_selection_command(self, text: str) -> bool:
        text_lower = text.lower().strip()
        return text_lower in {"all", "none", "done"} or bool(
            REMOVE_SELECTION_PATTERN.fullmatch(text_lower)
        )

    def _is_remove_confirmation_command(self, text: str) -> bool:
        text_lower = text.lower().strip()
        return text_lower in CANCEL_KEYWORDS or bool(REMOVE_DELETE_PATTERN.fullmatch(text_lower))

    def _is_remove_preview_followup(self, text: str) -> bool:
        return text.lower().strip() in {
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

    def _is_remove_reselection_command(self, text: str) -> bool:
        text_lower = text.lower().strip()
        return text_lower in {"all", "none"} or bool(REMOVE_SELECTION_PATTERN.fullmatch(text_lower))

    def _looks_like_remove_selection_attempt(self, text: str) -> bool:
        normalized = text.lower().strip()
        if "," not in normalized:
            return False
        parts = [part.strip() for part in normalized.split(",") if part.strip()]
        if not parts or not any(part.isdigit() for part in parts):
            return False
        keyword_starters = {"all", "none", "done", "cancel", "delete", "yes", "no", "confirm", "keep"}
        for part in parts:
            if part.isdigit():
                continue
            if re.fullmatch(r"[a-z0-9]+", part):
                return True
            leading_word = re.match(r"([a-z]+)", part)
            if leading_word and leading_word.group(1) in keyword_starters:
                return True
        return False

    def _can_continue_remove_session(self, text: str, state: CalendarState) -> bool:
        if state == CalendarState.AWAITING_REMOVAL_SELECTION:
            return (
                self._is_remove_confirmation_command(text)
                or self._is_remove_selection_command(text)
                or self._looks_like_remove_selection_attempt(text)
            )
        if state == CalendarState.CONFIRMING_REMOVAL:
            return (
                self._is_remove_reselection_command(text)
                or self._is_remove_confirmation_command(text)
                or self._is_remove_preview_followup(text)
                or self._looks_like_remove_selection_attempt(text)
            )
        return False

    def _is_stale_remove_followup(self, text: str) -> bool:
        text_lower = text.lower().strip()
        return (
            text_lower in {"all", "none", "done"}
            or bool(REMOVE_DELETE_PATTERN.fullmatch(text_lower))
            or ("," in text_lower and bool(REMOVE_SELECTION_PATTERN.fullmatch(text_lower)))
            or self._looks_like_remove_selection_attempt(text)
        )

    def _flow(self, calendar_service: Optional[CalendarService]) -> RemoveFlow:
        self._remove_flow._calendar_service = calendar_service
        return self._remove_flow

    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        chat_id = self._get_chat_id(event)
        session = calendar_session_manager.get_session(chat_id)
        if session and session.state in (
            CalendarState.AWAITING_REMOVAL_SELECTION,
            CalendarState.CONFIRMING_REMOVAL,
        ):
            return self._is_explicit_remove_trigger(text) or self._can_continue_remove_session(text, session.state)

        if calendar_session_manager.had_recent_remove_flow(chat_id, getattr(getattr(event, "source", None), "user_id", None)) and (
            REMOVE_DELETE_PATTERN.fullmatch(text.lower().strip())
            or self._is_stale_remove_followup(text)
        ):
            return True

        return self._is_explicit_remove_trigger(text)

    async def handle(
        self,
        event: MessageEvent,
        text: str,
        line_bot_api: MessagingApi,
        chat_id: str,
        user_id: Optional[str],
        context: dict,
    ) -> bool:
        calendar_service = context.get("calendar_service")
        session = calendar_session_manager.get_session(chat_id)
        flow = self._flow(calendar_service)

        if session and not calendar_session_manager.is_session_owner(chat_id, user_id):
            if session.state in (
                CalendarState.AWAITING_REMOVAL_SELECTION,
                CalendarState.CONFIRMING_REMOVAL,
            ) and (
                self._is_explicit_remove_trigger(text)
                or self._can_continue_remove_session(text, session.state)
            ):
                await flow.send_message(
                    event,
                    line_bot_api,
                    "❌ Only the person who started this removal flow can change or confirm it.",
                )
                return True
            return False

        if self._is_explicit_remove_trigger(text):
            return await flow.start_remove_flow(
                event, line_bot_api, chat_id, user_id
            )

        if not session:
            if calendar_session_manager.had_recent_remove_flow(chat_id, user_id) and (
                REMOVE_DELETE_PATTERN.fullmatch(text.lower().strip())
                or self._is_stale_remove_followup(text)
            ):
                await flow.send_message(
                    event,
                    line_bot_api,
                    "❌ This remove flow is stale or expired. Start the remove flow again.",
                )
                return True
            return False

        if session.state == CalendarState.AWAITING_REMOVAL_SELECTION:
            if text.lower().strip() in CANCEL_KEYWORDS or self._is_remove_confirmation_command(text):
                return await flow.handle_removal_confirmation(
                    event, text, line_bot_api, chat_id, user_id
                )
            if not self._can_continue_remove_session(text, session.state):
                return False
            return await flow.handle_removal_selection(
                event, text, line_bot_api, chat_id, user_id
            )

        if session.state == CalendarState.CONFIRMING_REMOVAL:
            if self._is_remove_reselection_command(text) or self._looks_like_remove_selection_attempt(text):
                return await flow.handle_removal_selection(
                    event, text, line_bot_api, chat_id, user_id
                )
            if not (
                self._is_remove_confirmation_command(text)
                or self._is_remove_preview_followup(text)
            ):
                return False
            return await flow.handle_removal_confirmation(
                event, text, line_bot_api, chat_id, user_id
            )

        return False

    def _get_chat_id(self, event: MessageEvent) -> str:
        if event.source and getattr(event.source, "group_id", None):
            return f"group_{getattr(event.source, 'group_id')}"
        if event.source and getattr(event.source, "room_id", None):
            return f"room_{getattr(event.source, 'room_id')}"
        if event.source and getattr(event.source, "user_id", None):
            return f"user_{getattr(event.source, 'user_id')}"
        return "user_unknown"
