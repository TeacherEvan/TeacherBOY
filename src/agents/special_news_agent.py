"""Special News agent.

Implements `/special news` (DM-only + Friends-of-the-Bot ACL).
Returns 15 headlines in 3 batches (5 tourism, 5 sports, 5 international)
formatted with Markdown + emoji section headers and `---` separators.
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Dict, List, Optional

from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent

from .base_agent import BaseAgent
from src.services.special_news_service import SpecialNewsService

logger = logging.getLogger(__name__)


class SpecialNewsAgent(BaseAgent):
    """DM-only special news command."""

    def __init__(self, news_service: SpecialNewsService):
        super().__init__(
            name="SpecialNewsAgent",
            description="/special news (DM-only) - 15 headlines in 3 sections",
        )
        self._service = news_service

        # Feeds
        self._tourism_feed = "https://www.tatnews.org/feed/"
        self._sports_feed = "https://www.bangkokpost.com/rss/data/sports.xml"
        self._international_feed = "https://www.bangkokpost.com/rss/data/world.xml"

    def get_priority(self) -> int:
        # Runs after Admin (5) and Translation (10), before NewsAgent (15)
        return 12

    def _is_private_chat(self, event: MessageEvent) -> bool:
        if event.source:
            group_id = getattr(event.source, "group_id", None)
            if isinstance(group_id, str) and group_id.strip():
                return False
            room_id = getattr(event.source, "room_id", None)
            if isinstance(room_id, str) and room_id.strip():
                return False
        return True

    def _is_special_news_command(self, text: str) -> bool:
        text_clean = re.sub(r"\s+", " ", text.strip().lower())
        return text_clean == "/special news"

    async def _is_friend(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            return False

        try:
            # LINE returns error for non-friends.
            line_bot_api.get_profile(user_id)
            return True
        except ApiException:
            return False
        except Exception:
            return False

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        return self._is_special_news_command(text)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        if not self._is_special_news_command(text):
            return False

        # Hard fail in groups/rooms (DM-only)
        if not self._is_private_chat(event):
            await self._reply_text(
                event,
                line_bot_api,
                "❌ `/special news` works in DM only.",
            )
            return True

        # Friends-of-the-bot ACL
        is_friend = await self._is_friend(event, line_bot_api)
        if not is_friend:
            await self._reply_text(
                event,
                line_bot_api,
                "❌ Access denied.",
            )
            return True

        tourism_task = self._service.fetch_rss_items(self._tourism_feed, limit=5)
        sports_task = self._service.fetch_rss_items(self._sports_feed, limit=5)
        intl_task = self._service.fetch_rss_items(self._international_feed, limit=5)

        tourism, sports, intl = await asyncio.gather(tourism_task, sports_task, intl_task)

        tourism = self._service.pad_items(tourism, 5)
        sports = self._service.pad_items(sports, 5)
        intl = self._service.pad_items(intl, 5)

        msg = self._format_markdown(tourism, sports, intl)
        await self._reply_text(event, line_bot_api, msg)
        return True

    def _format_section(self, header: str, items: List[Dict[str, str]]) -> str:
        lines: List[str] = [header]
        for i, item in enumerate(items[:5], 1):
            title = (item.get("title") or "").strip() or "(unavailable)"
            url = (item.get("url") or "").strip()
            if url:
                lines.append(f"{i}. [{title}]({url})")
            else:
                lines.append(f"{i}. {title}")
        return "\n".join(lines)

    def _format_markdown(
        self,
        tourism: List[Dict[str, str]],
        sports: List[Dict[str, str]],
        intl: List[Dict[str, str]],
    ) -> str:
        parts = [
            "📰 **Special News**",
            "",
            self._format_section("🧳 **Thailand Tourism**", tourism),
            "",
            "---",
            "",
            self._format_section("🏟️ **Thailand Sports**", sports),
            "",
            "---",
            "",
            self._format_section("🌍 **International**", intl),
        ]
        return "\n".join(parts)

    async def _reply_text(self, event: MessageEvent, line_bot_api: MessagingApi, text: str) -> None:
        if not event.reply_token:
            return
        line_bot_api.reply_message(
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                notificationDisabled=False,
            )
        )
