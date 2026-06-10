"""Special News agent.

Implements `/special news` (DM-only + Friends-of-the-Bot ACL).
Returns 15 headlines in 3 batches (5 tourism, 5 sports, 5 international)
formatted with Markdown + emoji section headers and enhanced visual design.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, datetime
from typing import Any

from linebot.v3.messaging import FlexContainer, FlexMessage, MessagingApi, ReplyMessageRequest, TextMessage
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.privilege_service import privilege_service
from src.services.special_news_service import SpecialNewsService

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)


class SpecialNewsAgent(BaseAgent):
    """DM-only special news command."""

    def __init__(self, news_service: SpecialNewsService):
        super().__init__(
            name="SpecialNewsAgent",
            description="/special news (DM-only) - 15 headlines in 3 sections",
        )
        self._service = news_service

        # Cache friendship checks to reduce LINE API calls
        # {user_id: (is_friend, cached_at_utc)}
        self._friend_cache: dict[str, tuple[bool, datetime]] = {}

        # Feeds
        # Note: TAT News (tatnews.org) returns 403, using Bangkok Post Travel instead
        self._tourism_feed = "https://www.bangkokpost.com/rss/data/travel.xml"
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

        cached = self._friend_cache.get(user_id)
        if cached:
            is_friend, cached_at = cached
            age = (datetime.now(UTC) - cached_at).total_seconds()
            if age < settings.friend_cache_ttl_seconds:
                return is_friend

        try:
            # LINE returns error for non-friends.
            await asyncio.to_thread(line_bot_api.get_profile, user_id)
            self._friend_cache[user_id] = (True, datetime.now(UTC))
            return True
        except ApiException:
            self._friend_cache[user_id] = (False, datetime.now(UTC))
            return False
        except Exception:
            return False

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        if not self._is_special_news_command(text):
            return False

        user_id = getattr(event.source, "user_id", None) if event.source else None

        # Privileged users can run it anywhere.
        if privilege_service.is_privileged(user_id):
            return True

        # Regular users must use DM.
        return self._is_private_chat(event)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        if not self._is_special_news_command(text):
            return False

        user_id = getattr(event.source, "user_id", None) if event.source else None
        is_privileged = privilege_service.is_privileged(user_id)

        # Regular users: DM-only
        if not is_privileged and not self._is_private_chat(event):
            await self._reply_text(
                event,
                line_bot_api,
                "❌ `/special news` is available in DM (private chat) only.\n\n"
                "💡 Please send me a direct message to access exclusive Thailand news!",
            )
            return True

        # Friends-of-the-bot ACL (bypass for privileged users)
        if not is_privileged:
            is_friend = await self._is_friend(event, line_bot_api)
        else:
            is_friend = True

        if not is_friend:
            await self._reply_text(
                event,
                line_bot_api,
                "❌ Access denied.\n\n🤝 Please add me as a friend to access special news features!",
            )
            return True

        # Send loading state for better UX
        logger.info("🔍 Fetching special news for user...")

        # Fetch all feeds concurrently with optimized gathering
        try:
            tourism_task = self._service.fetch_rss_items(self._tourism_feed, limit=5)
            sports_task = self._service.fetch_rss_items(self._sports_feed, limit=5)
            intl_task = self._service.fetch_rss_items(self._international_feed, limit=5)

            tourism, sports, intl = await asyncio.gather(tourism_task, sports_task, intl_task)

            # Log what we got
            logger.info(f"📊 Fetched: Tourism={len(tourism)}, Sports={len(sports)}, Intl={len(intl)}")

            # Check if we got any real data (don't pad yet)
            real_tourism = [item for item in tourism if item.get("title") and item["title"] != "(unavailable)"]
            real_sports = [item for item in sports if item.get("title") and item["title"] != "(unavailable)"]
            real_intl = [item for item in intl if item.get("title") and item["title"] != "(unavailable)"]

            total_real_items = len(real_tourism) + len(real_sports) + len(real_intl)
            logger.info(
                f"📈 Real items: Tourism={len(real_tourism)}, Sports={len(real_sports)}, Intl={len(real_intl)}, Total={total_real_items}"
            )

            if total_real_items == 0:
                await self._reply_text(
                    event,
                    line_bot_api,
                    "⚠️ Unable to fetch news at this moment.\n\n"
                    "🔄 Please try again in a few moments.\n\n"
                    "Our news sources may be temporarily unavailable.\n"
                    "This could be due to:\n"
                    "• Network connectivity issues\n"
                    "• RSS feed maintenance\n"
                    "• Temporary server downtime",
                )
                logger.warning("⚠️ All special news feeds returned empty results")
                return True

            # Try Flex message for enhanced visual experience
            flex_dict = self._create_special_news_flex(tourism, sports, intl)
            if flex_dict:
                flex_container = FlexContainer.from_dict(flex_dict)
                flex_message = FlexMessage(  # type: ignore[call-arg]
                    altText=f"Special News - {total_real_items} headlines", contents=flex_container
                )
                await self._reply_flex(event, line_bot_api, flex_message)
                logger.info(f"✅ Successfully delivered special news as Flex ({total_real_items} items)")
            else:
                # Fallback to text
                msg = self._format_markdown(tourism, sports, intl)
                await self._reply_text(event, line_bot_api, msg)
                logger.info(f"✅ Successfully delivered special news as text ({total_real_items} items)")
            return True

        except Exception as e:
            logger.error(f"❌ Special news fetch error: {e}", exc_info=True)
            await self._reply_text(
                event,
                line_bot_api,
                "❌ An error occurred while fetching news.\n\n🔄 Please try again later.",
            )
            return True

    def _format_section(self, header: str, items: list[dict[str, str]]) -> str:
        """
        Format a news section with enhanced visual hierarchy.

        Args:
            header: Section header with emoji
            items: List of news items with title and url

        Returns:
            Formatted markdown string
        """
        lines: list[str] = [header, ""]  # Add blank line after header for better spacing

        valid_count = 0
        for _i, item in enumerate(items[:5], 1):
            title = (item.get("title") or "").strip()
            url = (item.get("url") or "").strip()

            # Skip unavailable/empty items completely - don't show them
            if not title or title == "(unavailable)":
                continue

            valid_count += 1
            if url:
                # Markdown link with number prefix
                lines.append(f"{valid_count}. [{title}]({url})")
            else:
                # Plain text if no URL (with warning)
                lines.append(f"{valid_count}. {title} ⚠️")

        # If no valid items were found, show a message
        if valid_count == 0:
            lines.append("_No news available at this moment_")

        return "\n".join(lines)

    def _format_markdown(
        self,
        tourism: list[dict[str, str]],
        sports: list[dict[str, str]],
        intl: list[dict[str, str]],
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
            f"_{datetime.now(UTC).strftime('%B %d, %Y')}_",
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

    def _create_special_news_flex(
        self,
        tourism: list[dict[str, str]],
        sports: list[dict[str, str]],
        intl: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        """Create a Flex carousel for special news with enhanced visuals."""
        try:
            bubbles = []

            # Tourism section
            tourism_bubble = self._create_section_bubble("🧳 Tourism News", tourism, "#0D8186")
            if tourism_bubble:
                bubbles.append(tourism_bubble)

            # Sports section
            sports_bubble = self._create_section_bubble("🏟️ Sports News", sports, "#FF6B35")
            if sports_bubble:
                bubbles.append(sports_bubble)

            # International section
            intl_bubble = self._create_section_bubble("🌍 International News", intl, "#2E8B57")
            if intl_bubble:
                bubbles.append(intl_bubble)

            if not bubbles:
                return None

            return {"type": "carousel", "contents": bubbles}
        except Exception as e:
            logger.error(f"Error creating special news flex: {e}")
            return None

    def _create_section_bubble(self, title: str, items: list[dict[str, str]], accent_color: str) -> dict[str, Any] | None:
        """Create a single bubble for a news section."""
        valid_items = [item for item in items[:5] if item.get("title") and item["title"] != "(unavailable)"]
        if not valid_items:
            # Always return a bubble so the carousel consistently shows 3 sections.
            return {
                "type": "bubble",
                "size": "giga",
                "header": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": title,
                            "weight": "bold",
                            "size": "lg",
                            "color": accent_color,
                        }
                    ],
                    "backgroundColor": "#F8F8F8",
                    "paddingAll": "lg",
                },
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "No news available right now.",
                            "size": "sm",
                            "color": "#666666",
                            "wrap": True,
                        }
                    ],
                    "spacing": "md",
                },
                "footer": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "Try again later",
                            "size": "xs",
                            "color": "#888888",
                            "align": "center",
                        }
                    ],
                    "paddingTop": "sm",
                },
            }

        box_contents = []
        for i, item in enumerate(valid_items, 1):
            title_text = item.get("title", "").strip()
            url = item.get("url", "").strip()

            # Truncate title if too long
            if len(title_text) > 40:
                title_text = title_text[:37] + "..."

            content_box = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": f"{i}. {title_text}",
                        "size": "sm",
                        "color": "#333333",
                        "wrap": True,
                        "action": {"type": "uri", "label": "Read", "uri": url} if url else None,
                    }
                ],
                "spacing": "sm",
                "margin": "md",
            }
            box_contents.append(content_box)

        return {
            "type": "bubble",
            "size": "giga",
            "header": {
                "type": "box",
                "layout": "vertical",
                "contents": [{"type": "text", "text": title, "weight": "bold", "size": "lg", "color": accent_color}],
                "backgroundColor": "#F8F8F8",
                "paddingAll": "lg",
            },
            "body": {"type": "box", "layout": "vertical", "contents": box_contents, "spacing": "md"},
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "Tap headline to read full story",
                        "size": "xs",
                        "color": "#888888",
                        "align": "center",
                    }
                ],
                "paddingTop": "sm",
            },
        }

    async def _reply_flex(self, event: MessageEvent, line_bot_api: MessagingApi, flex_message: FlexMessage) -> None:
        """Reply with Flex message."""
        if not event.reply_token:
            return
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[flex_message],
                notificationDisabled=False,
            ),
        )

    async def _reply_text(self, event: MessageEvent, line_bot_api: MessagingApi, text: str) -> None:
        if not event.reply_token:
            return
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                notificationDisabled=False,
            ),
        )
