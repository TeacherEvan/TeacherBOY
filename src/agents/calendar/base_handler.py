"""
Base Handler - Abstract base class for calendar operation handlers.

This module provides the foundation for the modular calendar handler architecture,
enabling lazy loading and loose coupling between handlers.
"""

import asyncio
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, cast

from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

from src.services.bot_identity_service import get_bot_identity_service

logger = logging.getLogger(__name__)


class CalendarHandler(ABC):
    """
    Abstract base class for calendar operation handlers.

    Each handler is responsible for a specific calendar operation (view, add, remove, etc.).
    Handlers are lazy-loaded only when their triggers are matched, optimizing memory usage.

    Design Pattern: Strategy Pattern + Handler Chain
    """

    def __init__(self, name: str, description: str):
        """
        Initialize handler.

        Args:
            name: Handler name (e.g., "ViewHandler", "AddHandler")
            description: Brief description of handler's responsibility
        """
        self.name = name
        self.description = description
        self._logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    def get_triggers(self) -> list[str]:
        """
        Return list of trigger phrases that activate this handler.

        Returns:
            List of trigger strings (e.g., ["zeus calendar", "my events"])
        """
        pass

    @abstractmethod
    async def can_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Determine if this handler can handle the given message.

        Args:
            event: LINE message event
            text: Message text content

        Returns:
            True if this handler should process the message
        """
        pass

    @abstractmethod
    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi, chat_id: str, user_id: str | None, context: dict
    ) -> bool:
        """
        Process the calendar operation.

        Args:
            event: LINE message event
            text: Message text content
            line_bot_api: LINE messaging API
            chat_id: Chat identifier
            user_id: User identifier
            context: Shared context dictionary (calendar_service, sessions, etc.)

        Returns:
            True if message was handled successfully
        """
        pass

    def _is_trigger(self, text: str, triggers: list[str]) -> bool:
        """Check if text starts with any trigger, expanding runtime identity aliases."""
        text_lower = re.sub(r"\s+", " ", text.lower().strip())
        identity_service = get_bot_identity_service()

        for trigger in triggers:
            for variant in identity_service.expand_prefixed_trigger(trigger):
                if text_lower.startswith(variant):
                    return True
        return False

    async def _send_message(self, event: MessageEvent, line_bot_api: MessagingApi, text: str) -> None:
        """Helper to send a text message."""
        from linebot.v3.messaging import ReplyMessageRequest, TextMessage

        if not getattr(event, "reply_token", None):
            return
        assert event.reply_token is not None
        try:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(  # type: ignore
                    replyToken=cast(str, event.reply_token),
                    messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                    notificationDisabled=False,
                ),
            )
        except Exception as e:
            self._logger.warning(f"Failed to send message (reply token may be expired): {e}")

    async def _send_message_with_quick_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
        quick_reply: Any,
    ) -> None:
        """Helper to send a text message with Quick Reply buttons."""
        from linebot.v3.messaging import ReplyMessageRequest, TextMessage

        if not getattr(event, "reply_token", None):
            return
        assert event.reply_token is not None
        try:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(  # type: ignore
                    replyToken=cast(str, event.reply_token),
                    messages=[TextMessage(text=text, quickReply=quick_reply, quoteToken=None)],
                    notificationDisabled=False,
                ),
            )
        except Exception as e:
            self._logger.error(f"Failed to send quick reply: {e}")

    async def _send_error_message(self, event: MessageEvent, line_bot_api: MessagingApi) -> None:
        """Send a generic error message."""
        error_msg = "❌ Sorry, something went wrong.\nPlease try again later.\n\nขออภัย เกิดข้อผิดพลาด"
        await self._send_message(event, line_bot_api, error_msg)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}')"
