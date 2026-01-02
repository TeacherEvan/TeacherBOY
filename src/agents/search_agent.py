"""Search Agent - Handles web search requests."""

import asyncio
import logging
import re
from typing import Optional
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

from .base_agent import BaseAgent
from src.services.brave_search_service import brave_search_service
from src.utils.tracing import get_tracer
from src.services.privilege_service import privilege_service

from src.config import settings

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class SearchAgent(BaseAgent):
    """Agent for handling web search requests using Brave Search."""

    def __init__(self):
        super().__init__(
            name="SearchAgent",
            description="Web search using Brave Search API",
        )
        self.search_service = brave_search_service
        # Keep a cached list for performance and for tests that monkeypatch this field.
        self._admin_user_ids = settings.get_admin_user_ids()

    def get_priority(self) -> int:
        """
        Priority 8: Runs before LLMAgent (9) and TranslationAgent (10).
        Ensures 'Zeus search' is handled here, not by LLMAgent.
        """
        return 8

    def _is_admin(self, user_id: Optional[str]) -> bool:
        """Check if user is an admin."""
        if privilege_service.is_claimed_admin(user_id):
            return True
        return user_id in self._admin_user_ids if user_id else False

    def _is_private_chat(self, event: MessageEvent) -> bool:
        """Check if chat is private (1-on-1)."""
        return event.source is not None and event.source.type == "user"

    def _get_group_room_ids(self, event: MessageEvent) -> tuple[Optional[str], Optional[str]]:
        """Return (group_id, room_id) from event source."""
        source = getattr(event, "source", None)
        group_id = getattr(source, "group_id", None) if source else None
        room_id = getattr(source, "room_id", None) if source else None
        return group_id, room_id

    def _parse_search_command(self, text: str) -> Optional[str]:
        """
        Parse search command.
        Trigger: 'Zeus search <query>'
        Returns query string or None.
        """
        # Regex for trigger: "Zeus search" followed by query.
        # Accept optional leading slash and common typo "Zues".
        match = re.match(r"^/?(?:Zeus|Zues)\s+search\s+(.+)$", text.strip(), re.IGNORECASE)
        if match:
            return match.group(1).strip()
        return None

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Text starts with 'Zeus search'
        """
        if not self._parse_search_command(text):
            return False

        # Access control at routing time:
        # - Admins can search anywhere
        # - Private chats always allowed
        # - Group/room obeys Zeus group rules (allowlist/denylist)
        user_id = getattr(event.source, "user_id", None)
        if self._is_admin(user_id):
            return True

        if self._is_private_chat(event):
            return True

        group_id, room_id = self._get_group_room_ids(event)
        return settings.is_zeus_allowed_in_group(group_id, room_id, user_is_admin=False)

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """Process search request."""
        query = self._parse_search_command(text)
        if not query:
            return False

        user_id = getattr(event.source, "user_id", None)
        is_private = self._is_private_chat(event)
        logger.info(f"🔍 Zeus search from {user_id} ({'DM' if is_private else 'group'}): {query[:50]}...")

        # Access control: admins anywhere; private chats always; group/room per Zeus rules.
        if not self._is_admin(user_id) and not is_private:
            group_id, room_id = self._get_group_room_ids(event)
            if not settings.is_zeus_allowed_in_group(
                group_id, room_id, user_is_admin=False
            ):
                logger.info(
                    f"🔒 Zeus search denied for non-admin user_id={user_id} in group chat"
                )
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[
                            TextMessage(
                                text=("🔒 Zeus search is not enabled in this group."),
                                quickReply=None,
                                quoteToken=None,
                            )
                        ],
                        notificationDisabled=False,
                    ),
                )
                return True

        with tracer.start_as_current_span("search_agent.handle") as span:
            span.set_attribute("search.query", query)
            
            try:
                if not self.search_service.is_configured():
                    await self._send_error(event, line_bot_api, "Search is not configured (missing API key).")
                    return True

                # Perform search
                results = await self.search_service.search(query, count=5)
                
                if not results:
                    await self._send_error(event, line_bot_api, f"❌ No results: {query}")
                    return True

                # Format results
                # Terse, robotic output: one emoji per line.
                message_text = f"🔍 {query}\n"
                for i, result in enumerate(results, 1):
                    title = result.get('title', 'No title')
                    url = result.get('url', '#')
                    message_text += f"🔗 {i}. {title} {url}\n"

                # Send response
                reply_message = TextMessage(text=message_text, quickReply=None, quoteToken=None)
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[reply_message],
                            notificationDisabled=False,
                        ),
                    )
                
                logger.info(f"✅ Sent search results for '{query}'")
                return True

            except Exception as e:
                logger.error(f"❌ Search agent error: {e}", exc_info=True)
                await self._send_error(event, line_bot_api, "❌ Search error")
                return True

    async def _send_error(self, event: MessageEvent, line_bot_api: MessagingApi, message: str):
        """Send error message."""
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[TextMessage(text=message, quickReply=None, quoteToken=None)],
                    notificationDisabled=False,
                ),
            )
