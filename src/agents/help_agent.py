"""Help Agent - Provides comprehensive, contextual help for the Ms. Green LINE bot."""

import asyncio
import logging
import re
from typing import Any

from linebot.v3.messaging import (
    FlexContainer,
    FlexMessage,
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.bot_identity_service import get_bot_identity_service
from src.services.privilege_service import privilege_service
from src.utils.tracing import get_tracer

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class HelpAgent(BaseAgent):
    """Agent for providing comprehensive, contextual help with industry-standard features."""

    def __init__(self):
        super().__init__(
            name="HelpAgent",
            description="Comprehensive help system with command directories and contextual guidance",
        )

    def get_priority(self) -> int:
        """Highest priority to ensure help commands are handled first."""
        return 5

    def _is_private_chat(self, event: MessageEvent) -> bool:
        """Check if chat is private (1-on-1)."""
        return event.source is not None and event.source.type == "user"

    def _get_chat_type(self, event: MessageEvent) -> str:
        """Get human-readable chat type."""
        if self._is_private_chat(event):
            return "private chat"
        if event.source and getattr(event.source, "group_id", None):
            return "group chat"
        if event.source and getattr(event.source, "room_id", None):
            return "room chat"
        return "unknown chat"

    def _is_help_command(self, text: str) -> bool:
        """Check if text is a help command."""
        return self._extract_help_topic(text) is not None or bool(re.match(r"^/?help\s*$", text.lower().strip()))

    def _extract_help_topic(self, text: str) -> str | None:
        """Extract a help topic from commands like 'help calendar' or '/help admin'."""
        text_lower = text.lower().strip()
        match = re.match(r"^/?help(?:\s+(?P<topic>.+?))?\s*$", text_lower)
        if match and match.group("topic"):
            topic = match.group("topic").strip()
            return topic if topic else None

        identity_pattern = "|".join(
            sorted(
                (re.escape(alias) for alias in get_bot_identity_service().get_profile().aliases),
                key=len,
                reverse=True,
            )
        )
        match = re.match(rf"^/?(?:{identity_pattern})\s+(?:--help|help)(?:\s+(?P<topic>.+?))?\s*$", text_lower)
        if match and match.group("topic"):
            topic = match.group("topic").strip()
            return topic if topic else None

        match = re.match(rf"^dear\s+(?:{identity_pattern})\s+(?:--help|help)(?:\s+(?P<topic>.+?))?\s*$", text_lower)
        if match and match.group("topic"):
            topic = match.group("topic").strip()
            return topic if topic else None

        return None

    def _get_command_categories(
        self,
        is_admin: bool,
        chat_type: str,
        zeus_available: bool,
        search_available: bool,
    ) -> dict[str, list[dict[str, Any]]]:
        """Get categorized command list based on user permissions and context."""
        display_name = get_bot_identity_service().get_profile().display_name
        categories = {
            "Core Commands": [
                {
                    "command": "help",
                    "description": "Show this help menu",
                    "examples": ["help", "/help", f"{display_name} help"],
                    "available": True,
                },
                {
                    "command": display_name,
                    "description": "Wake the bot from sleep mode",
                    "examples": [display_name],
                    "available": True,
                },
                {
                    "command": "Thanks Ms Green!",
                    "description": "Put the bot to sleep for 24 hours",
                    "examples": ["Thanks Ms Green!"],
                    "available": True,
                },
            ],
            "Translation": [
                {
                    "command": "Thai text",
                    "description": "Auto-translate Thai to English",
                    "examples": ["สวัสดีครับ", "ขอบคุณมาก"],
                    "available": True,
                },
                {
                    "command": "English text",
                    "description": "Auto-translate English to Thai",
                    "examples": ["Hello", "Thank you"],
                    "available": True,
                },
            ],
            "AI & Search": [
                {
                    "command": f"{display_name} <question>",
                    "description": f"Ask {display_name} AI general questions",
                    "examples": [f"{display_name} what is the weather?", f"{display_name} tell me a joke"],
                    "available": zeus_available,
                },
                {
                    "command": f"{display_name} search <query>",
                    "description": "Search the web for information",
                    "examples": [f"{display_name} search Python tutorials"],
                    "available": search_available,
                },
            ],
            "News & Information": [
                {
                    "command": "news",
                    "description": "Get latest news headlines",
                    "examples": ["news", "ข่าว"],
                    "available": True,
                },
                {
                    "command": "/special news",
                    "description": "Get specialized news (sports, tourism, etc.)",
                    "examples": ["/special news"],
                    "available": True,
                },
            ],
            "Calendar & Reminders": [
                {
                    "command": f"{display_name} calendar",
                    "description": "View your upcoming events and reminders",
                    "examples": [f"{display_name} calendar", "my events", "my reminders"],
                    "available": settings.is_calendar_configured(),
                },
                {
                    "command": f"{display_name} add event",
                    "description": "Create event with customizable reminders (7/3/1 days)",
                    "examples": [f"{display_name} add event", f"{display_name} remind me"],
                    "available": settings.is_calendar_configured(),
                },
                {
                    "command": f"{display_name} add [date] [title]",
                    "description": f"Quick add: {display_name} add Jan 15 Birthday party",
                    "examples": [f"{display_name} add tomorrow Meeting", f"{display_name} add 15/01 Conference"],
                    "available": settings.is_calendar_configured(),
                },
                {
                    "command": f"{display_name} scrape",
                    "description": "AI-powered date extraction from recent messages",
                    "examples": [f"{display_name} scrape", f"{display_name} scan messages"],
                    "available": settings.is_calendar_configured(),
                },
                {
                    "command": f"{display_name} remove event",
                    "description": "Delete events with multi-select support",
                    "examples": [f"{display_name} remove event", f"{display_name} delete event"],
                    "available": settings.is_calendar_configured(),
                },
            ],
            "Image Analysis": [
                {
                    "command": f"{display_name} profile",
                    "description": "Psychological profiling from photos using FBI/Ekman/Navarro frameworks",
                    "examples": [f"{display_name} profile", f"{display_name} analyze this photo"],
                    "rate_limit": "3 analyses/hour (admins unlimited)" if not is_admin else "Unlimited",
                    "available": settings.is_profiler_configured(),
                },
                {
                    "command": f"{display_name} analyze this",
                    "description": "General image Q&A with GPT-4o vision",
                    "examples": [f"{display_name} analyze this", "analyze image", "examine this photo"],
                    "rate_limit": "5 analyses/hour (admins unlimited)" if not is_admin else "Unlimited",
                    "available": settings.is_github_models_configured(),
                },
            ],
        }

        # Admin-only commands
        if is_admin:
            categories["Admin Commands"] = [
                {
                    "command": "/admin help",
                    "description": "Show admin command reference",
                    "examples": ["/admin help"],
                    "available": True,
                },
                {
                    "command": "/admin stats",
                    "description": "View bot usage statistics",
                    "examples": ["/admin stats"],
                    "available": True,
                },
                {
                    "command": "/admin groups",
                    "description": "List all groups/rooms bot is in (emergency exit)",
                    "examples": ["/admin groups"],
                    "available": True,
                },
                {
                    "command": "/admin leave",
                    "description": "Make bot leave current group/room",
                    "examples": ["/admin leave"],
                    "available": chat_type in ["group chat", "room chat"],
                },
                {
                    "command": "/admin purge",
                    "description": "Clear chat session data",
                    "examples": ["/admin purge"],
                    "available": True,
                },
                {
                    "command": "/admin confirm <token>",
                    "description": "Confirm destructive admin actions",
                    "examples": ["/admin confirm ABC123"],
                    "available": True,
                },
            ]

        return categories

    def _get_adaptive_tips(self, is_admin: bool, chat_type: str) -> list[str]:
        """Get contextual tips based on user status and chat type."""
        tips = []
        display_name = get_bot_identity_service().get_profile().display_name

        # Interactive tutorial prompts
        tips.append(f"📚 Try '{display_name} calendar' to explore the events feature")
        tips.append(f"🎓 Use '{display_name} scrape' to see AI date extraction in action")

        if chat_type == "private chat":
            tips.append("💡 In private chats, you can use simple 'help' command")
            if is_admin:
                tips.append("🔧 Admin commands work in both private and group chats")
        else:
            tips.append("💡 For private help, message the bot directly")

        if not is_admin:
            tips.append("🔒 Some features require admin privileges")
            tips.append("📞 Contact admin to request premium access")
            tips.append("⭐ Premium: Unlimited rate limits + priority features")
        else:
            tips.append("👑 Admin perks: No rate limits, all features unlocked")

        # Customization options
        if settings.is_calendar_configured():
            tips.append("⚙️ Customize reminder timing: 7/3/1 days or all")

        tips.append("⚡ AI translation is active")

        tips.append(f"😴 Bot sleeps after 24h of inactivity - wake with '{display_name}'")

        # Advanced search tip
        if settings.is_brave_search_configured():
            tips.append(f"🔍 Advanced: '{display_name} search' for web results with AI summary")

        return tips

    def _build_quick_reply(self, display_name: str):
        """Build quick reply shortcuts for common help actions."""
        return QuickReply(
            items=[
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="Help menu", text="help")),
                QuickReplyItem(
                    type="action", imageUrl=None, action=MessageAction(label="Calendar help", text=f"{display_name} calendar")
                ),
                QuickReplyItem(
                    type="action", imageUrl=None, action=MessageAction(label="Search help", text=f"{display_name} search")
                ),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="News help", text="help news")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="Image help", text="help image")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="Admin help", text="/admin help")),
                QuickReplyItem(type="action", imageUrl=None, action=MessageAction(label="Wake bot", text=display_name)),
            ]
        )

    def _topic_aliases(self) -> dict[str, str]:
        """Map natural help topics to canonical help sections."""
        display_name = get_bot_identity_service().get_profile().display_name.lower()
        return {
            "help": "Core Commands",
            "commands": "Core Commands",
            "core": "Core Commands",
            "wake": "Core Commands",
            "sleep": "Core Commands",
            "translate": "Translation",
            "translation": "Translation",
            "news": "News & Information",
            "calendar": "Calendar & Reminders",
            "event": "Calendar & Reminders",
            "events": "Calendar & Reminders",
            "reminder": "Calendar & Reminders",
            "reminders": "Calendar & Reminders",
            "search": "AI & Search",
            "ai": "AI & Search",
            "image": "Image Analysis",
            "photo": "Image Analysis",
            "profile": "Image Analysis",
            "admin": "Admin Commands",
            display_name: "Core Commands",
        }

    def _resolve_help_topic(self, topic: str | None, categories: dict[str, list[dict[str, Any]]]) -> str | None:
        """Normalize a help topic to a known category name."""
        if not topic:
            return None

        normalized = topic.lower().strip()
        canonical = self._topic_aliases().get(normalized)
        if canonical and canonical in categories:
            return canonical

        for category_name, commands in categories.items():
            haystack = " ".join(
                [category_name] + [cmd["command"] for cmd in commands] + [" ".join(cmd["examples"]) for cmd in commands]
            ).lower()
            if normalized in haystack:
                return category_name

        return None

    def _get_supported_sections(self, categories: dict[str, list[dict[str, Any]]]) -> list[str]:
        """Build a compact list of all available help sections."""
        section_order = [
            "Core Commands",
            "Translation",
            "AI & Search",
            "News & Information",
            "Calendar & Reminders",
            "Image Analysis",
            "Admin Commands",
        ]
        return [
            section
            for section in section_order
            if section in categories and any(cmd["available"] for cmd in categories[section])
        ]

    def _build_category_box(self, category_name: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
        """Build one category card."""
        category_box = {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": f"⚡ {category_name.upper()}",
                    "weight": "bold",
                    "size": "md",
                    "color": "#1F2937",
                    "margin": "none",
                }
            ],
            "backgroundColor": "#FFFFFF",
            "borderColor": "#E5E7EB",
            "borderWidth": "1px",
            "cornerRadius": "8px",
            "paddingAll": "12px",
            "margin": "md",
        }

        command_contents: list[dict[str, Any]] = []
        for cmd in commands:
            cmd_box_contents = [
                {
                    "type": "text",
                    "text": f"• {cmd['command']}",
                    "weight": "bold",
                    "size": "sm",
                    "color": "#1F2937",
                    "wrap": True,
                },
                {"type": "text", "text": cmd["description"], "size": "xs", "color": "#6B7280", "wrap": True, "margin": "xs"},
            ]

            if "rate_limit" in cmd and cmd["rate_limit"]:
                cmd_box_contents.append(
                    {
                        "type": "text",
                        "text": f"⏱️ {cmd['rate_limit']}",
                        "size": "xxs",
                        "color": "#DC2626",
                        "wrap": True,
                        "margin": "xs",
                    }
                )

            cmd_box_contents.append(
                {
                    "type": "text",
                    "text": f"Example: {cmd['examples'][0]}",
                    "size": "xxs",
                    "color": "#9CA3AF",
                    "wrap": True,
                    "margin": "xs",
                }
            )

            command_contents.append({"type": "box", "layout": "vertical", "contents": cmd_box_contents, "margin": "sm"})

        category_box["contents"].extend(command_contents)  # type: ignore[attr-defined]
        return category_box

    def _create_help_cards(
        self,
        categories: dict[str, list[dict[str, Any]]],
        tips: list[str],
        chat_type: str,
        topic: str | None = None,
        quick_reply: QuickReply | None = None,
    ) -> list[FlexMessage]:
        """Create 1-3 help cards to keep LINE messages readable."""
        display_name = get_bot_identity_service().get_profile().display_name
        if quick_reply is None:
            quick_reply = self._build_quick_reply(display_name)

        topic = topic or None
        sections = self._get_supported_sections(categories)
        if topic and topic in categories:
            sections = [topic]

        cards = []
        chunks = [sections[i : i + 2] for i in range(0, len(sections), 2)] if not topic else [sections]
        for idx, chunk in enumerate(chunks, start=1):
            body_contents = []
            body_contents.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "🗡️ MS. GREEN HELP SYSTEM",
                            "weight": "bold",
                            "size": "xl",
                            "color": "#1F2937",
                            "align": "center",
                        },
                        {
                            "type": "text",
                            "text": f"{('Focused help: ' + topic) if topic else 'Full feature menu'} • {chat_type.title()}",
                            "size": "sm",
                            "color": "#6B7280",
                            "align": "center",
                            "margin": "sm",
                        },
                        {
                            "type": "text",
                            "text": f"Part {idx}/{len(chunks)}",
                            "size": "xxs",
                            "color": "#6B7280",
                            "align": "center",
                            "margin": "xs",
                        },
                    ],
                    "backgroundColor": "#F3F4F6",
                    "paddingAll": "16px",
                    "cornerRadius": "8px",
                    "margin": "none",
                }
            )

            if not topic and idx == 1:
                body_contents.append(
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "All features in one place. Tap a shortcut below or ask for a topic like help calendar.",
                                "size": "xs",
                                "color": "#374151",
                                "wrap": True,
                                "align": "center",
                            },
                            {
                                "type": "text",
                                "text": f"Sections: {', '.join(sections)}",
                                "size": "xxs",
                                "color": "#6B7280",
                                "wrap": True,
                                "align": "center",
                                "margin": "xs",
                            },
                        ],
                        "backgroundColor": "#EFF6FF",
                        "borderColor": "#BFDBFE",
                        "borderWidth": "1px",
                        "cornerRadius": "8px",
                        "paddingAll": "12px",
                        "margin": "md",
                    }
                )

            for category_name in chunk:
                commands = categories[category_name]
                available_commands = [cmd for cmd in commands if cmd["available"]]
                if not available_commands:
                    continue
                body_contents.append(self._build_category_box(category_name, available_commands))

            if tips and idx == len(chunks):
                tips_box = {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {
                            "type": "text",
                            "text": "💡 HELPFUL NOTES FROM MS. GREEN",
                            "weight": "bold",
                            "size": "md",
                            "color": "#1F2937",
                            "margin": "none",
                        }
                    ],
                    "backgroundColor": "#FEF3C7",
                    "borderColor": "#F59E0B",
                    "borderWidth": "1px",
                    "cornerRadius": "8px",
                    "paddingAll": "12px",
                    "margin": "md",
                }
                tip_contents = []
                for tip in tips[:3]:
                    tip_contents.append(
                        {"type": "text", "text": tip, "size": "xs", "color": "#92400E", "wrap": True, "margin": "xs"}
                    )
                tips_box["contents"].extend(tip_contents)  # type: ignore[attr-defined]
                body_contents.append(tips_box)

            body_contents.append(
                {
                    "type": "box",
                    "layout": "vertical",
                    "contents": [
                        {"type": "separator", "color": "#E5E7EB", "margin": "md"},
                        {
                            "type": "text",
                            "text": "⚡ Powered by Ms. Green • Assistant",
                            "size": "xxs",
                            "color": "#9CA3AF",
                            "align": "center",
                        },
                    ],
                    "paddingAll": "8px",
                }
            )

            flex_dict = {
                "type": "bubble",
                "size": "giga",
                "body": {
                    "type": "box",
                    "layout": "vertical",
                    "contents": body_contents,
                    "spacing": "none",
                    "paddingAll": "16px",
                },
                "styles": {"body": {"backgroundColor": "#FAFAFA"}},
            }
            cards.append(
                FlexMessage(
                    altText="Ms. Green Help System - Command Reference",
                    contents=FlexContainer.from_dict(flex_dict),
                    quickReply=quick_reply if idx == 1 else None,
                )
            )

        return cards

    def _create_help_flex_message(
        self,
        categories: dict[str, list[dict[str, Any]]],
        tips: list[str],
        chat_type: str,
        topic: str | None = None,
        quick_reply: QuickReply | None = None,
    ) -> FlexMessage:
        """Create a visually appealing Flex Message for help content."""
        display_name = get_bot_identity_service().get_profile().display_name
        if quick_reply is None:
            quick_reply = self._build_quick_reply(display_name)

        cards = self._create_help_cards(categories, tips, chat_type, topic=topic, quick_reply=quick_reply)
        if len(cards) == 1:
            return cards[0]

        carousel_dict = {
            "type": "carousel",
            "contents": [card.contents.to_dict() for card in cards],
        }
        return FlexMessage(
            altText="Ms. Green Help System - Command Reference",
            contents=FlexContainer.from_dict(carousel_dict),
            quickReply=quick_reply,
        )

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Handle if text is a help command."""
        if not self._is_help_command(text):
            return False

        chat_type = self._get_chat_type(event)
        is_group_or_room = chat_type in ("group chat", "room chat")
        user_id = getattr(event.source, "user_id", None) if getattr(event, "source", None) else None

        # Normal users in groups cannot trigger the help menu
        if is_group_or_room and not privilege_service.is_privileged(user_id):
            return False

        return True

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Provide comprehensive help with contextual information."""
        user_id = getattr(event.source, "user_id", None) if event.source else None
        is_admin = privilege_service.is_admin(user_id)
        chat_type = self._get_chat_type(event)

        # Availability is contextual.
        # - Private chats: AI/search are allowed (if configured)
        # - Groups/rooms: obey group access rules for non-admins (admins bypass)
        source = getattr(event, "source", None)
        group_id = getattr(source, "group_id", None) if source else None
        room_id = getattr(source, "room_id", None) if source else None

        if chat_type == "private chat":
            zeus_available = True
            search_available = settings.is_brave_search_configured()
        else:
            zeus_available = settings.is_zeus_allowed_in_group(group_id, room_id, user_is_admin=is_admin)
            search_available = settings.is_brave_search_configured() and zeus_available

        with tracer.start_as_current_span("help_agent.handle") as span:
            span.set_attribute("help.user_id", user_id or "unknown")
            span.set_attribute("help.is_admin", is_admin)
            span.set_attribute("help.chat_type", chat_type)

            try:
                # Get contextual command categories and tips
                categories = self._get_command_categories(is_admin, chat_type, zeus_available, search_available)
                tips = self._get_adaptive_tips(is_admin, chat_type)
                display_name = get_bot_identity_service().get_profile().display_name
                quick_reply = self._build_quick_reply(display_name)
                help_topic = self._resolve_help_topic(self._extract_help_topic(text), categories)

                # Create help message
                help_message = self._create_help_flex_message(
                    categories,
                    tips,
                    chat_type,
                    topic=help_topic,
                    quick_reply=quick_reply,
                )

                # Send reply
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[help_message],
                            notificationDisabled=False,
                        ),
                    )

                logger.info(f"✅ Sent comprehensive help to user {user_id} in {chat_type}")
                span.set_attribute("help.success", True)
                return True

            except Exception as e:
                logger.error(f"❌ Help agent error: {e}", exc_info=True)
                span.set_attribute("help.error", True)

                # Fallback to simple text message
                try:
                    fallback_message = TextMessage(
                        text=(
                            "🗡️ MS. GREEN HELP SYSTEM\n\n"
                            "Available commands:\n"
                            "• help - Show this menu\n"
                            "• Ms. Green - Wake from sleep\n"
                            "• Thanks Ms Green! - Sleep for 24h\n"
                            "• Thai/English text - Auto-translate\n\n"
                            "For admin commands: /admin help"
                        ),
                        quickReply=None,
                        quoteToken=None,
                    )

                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[fallback_message],
                                notificationDisabled=False,
                            ),
                        )
                    return True

                except Exception:
                    return False
