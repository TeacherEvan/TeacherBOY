"""Special News agent.

Implements `/special news` (DM-only + Friends-of-the-Bot ACL).
Returns 15 headlines in 3 batches (5 tourism, 5 sports, 5 international)
formatted with Markdown + emoji section headers and enhanced visual design.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime
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
                "❌ `/special news` is available in DM (private chat) only.\n\n"
                "💡 Please send me a direct message to access exclusive Thailand news!",
            )
            return True

        # Friends-of-the-bot ACL
        is_friend = await self._is_friend(event, line_bot_api)
        if not is_friend:
            await self._reply_text(
                event,
                line_bot_api,
                "❌ Access denied.\n\n"
                "🤝 Please add me as a friend to access special news features!",
            )
            return True

        # Send loading state for better UX
        logger.info(f"🔍 Fetching special news for user...")
        
        # Fetch all feeds concurrently with optimized gathering
        try:
            tourism_task = self._service.fetch_rss_items(self._tourism_feed, limit=5)
            sports_task = self._service.fetch_rss_items(self._sports_feed, limit=5)
            intl_task = self._service.fetch_rss_items(self._international_feed, limit=5)

            tourism, sports, intl = await asyncio.gather(tourism_task, sports_task, intl_task)

            # Pad results to ensure consistent display
            tourism = self._service.pad_items(tourism, 5)
            sports = self._service.pad_items(sports, 5)
            intl = self._service.pad_items(intl, 5)

            # Check if we got any real data
            total_real_items = sum(
                1 for items in [tourism, sports, intl]
                for item in items
                if item.get("title") and item["title"] != "(unavailable)"
            )

            if total_real_items == 0:
                await self._reply_text(
                    event,
                    line_bot_api,
                    "⚠️ Unable to fetch news at this moment.\n\n"
                    "🔄 Please try again in a few moments.\n"
                    "Our news sources may be temporarily unavailable.",
                )
                logger.warning(f"⚠️ All special news feeds returned empty results")
                return True

            msg = self._format_markdown(tourism, sports, intl)
            await self._reply_text(event, line_bot_api, msg)
            logger.info(f"✅ Successfully delivered special news ({total_real_items}/15 items)")
            return True
            
        except Exception as e:
            logger.error(f"❌ Special news fetch error: {e}", exc_info=True)
            await self._reply_text(
                event,
                line_bot_api,
                "❌ An error occurred while fetching news.\n\n"
                "🔄 Please try again later.",
            )
            return True

    def _format_section(self, header: str, items: List[Dict[str, str]]) -> str:
        """
        Format a news section with enhanced visual hierarchy.
        
        Args:
            header: Section header with emoji
            items: List of news items with title and url
            
        Returns:
            Formatted markdown string
        """
        lines: List[str] = [header, ""]  # Add blank line after header for better spacing
        
        for i, item in enumerate(items[:5], 1):
            title = (item.get("title") or "").strip() or "(unavailable)"
            url = (item.get("url") or "").strip()
            
            # Skip unavailable items in display for cleaner output
            if title == "(unavailable)":
                continue
                
            if url:
                # Markdown link with number prefix
                lines.append(f"{i}. [{title}]({url})")
            else:
                # Plain text if no URL
                lines.append(f"{i}. {title}")
        
        # If all items were unavailable, show a message
        if len(lines) == 2:  # Only header and blank line
            lines.append("_No news available at this moment_")
            
        return "\n".join(lines)

    def _format_markdown(
        self,
        tourism: List[Dict[str, str]],
        sports: List[Dict[str, str]],
        intl: List[Dict[str, str]],
    ) -> str:
        """
        Format complete special news message with professional markdown layout.
        
        Args:
            tourism: Thailand tourism news items
            sports: Thailand sports news items
            intl: International news items
            
        Returns:
            Complete formatted message with sections and separators
        """
        parts = [
            "📰 **Special News Update**",
            f"_{datetime.utcnow().strftime('%B %d, %Y')}_",
            "",
            self._format_section("🧳 **Thailand Tourism**", tourism),
            "",
            "---",  # Keep for backwards compatibility with tests
            "",
            self._format_section("🏟️ **Thailand Sports**", sports),
            "",
            "---",  # Keep for backwards compatibility with tests
            "",
            self._format_section("🌍 **International**", intl),
            "",
            "─" * 32,
            "",
            "_Tap any headline to read the full story_",
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
