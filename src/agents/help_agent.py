"""Help Agent - Provides comprehensive, contextual help for Zeus LINE Bot."""

import asyncio
import logging
import re
from typing import Optional, Dict, List, Any
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from .base_agent import BaseAgent
from src.services.bot_identity_service import get_bot_identity_service
from src.services.privilege_service import privilege_service
from src.config import settings
from src.utils.tracing import get_tracer

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
        text_lower = text.lower().strip()

        # Standard help patterns
        help_patterns = [
            r"^/?help\s*$",  # /help or help
        ]

        if any(re.match(pattern, text_lower) for pattern in help_patterns):
            return True

        identity_pattern = "|".join(
            sorted(
                (re.escape(alias) for alias in get_bot_identity_service().get_profile().aliases),
                key=len,
                reverse=True,
            )
        )
        return bool(
            re.match(rf"^/?(?:{identity_pattern})\s+(?:--help|help)\s*$", text_lower)
            or re.match(rf"^dear\s+(?:{identity_pattern})\s+(?:--help|help)\s*$", text_lower)
        )

    def _get_command_categories(
        self,
        is_admin: bool,
        chat_type: str,
        zeus_available: bool,
        search_available: bool,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Get categorized command list based on user permissions and context."""
        categories = {
            "Core Commands": [
                {
                    "command": "help",
                    "description": "Show this help menu",
                    "examples": ["help", "/help", "Dear Zeus help"],
                    "available": True
                },
                {
                    "command": "Dear Zeus",
                    "description": "Wake the bot from sleep mode",
                    "examples": ["Dear Zeus"],
                    "available": True
                },
                {
                    "command": "amen",
                    "description": "Put the bot to sleep for 24 hours",
                    "examples": ["amen"],
                    "available": True
                }
            ],
            "Translation": [
                {
                    "command": "Thai text",
                    "description": "Auto-translate Thai to English",
                    "examples": ["สวัสดีครับ", "ขอบคุณมาก"],
                    "available": True
                },
                {
                    "command": "English text",
                    "description": "Auto-translate English to Thai",
                    "examples": ["Hello", "Thank you"],
                    "available": True
                }
            ],
            "AI & Search": [
                {
                    "command": "Zeus <question>",
                    "description": "Ask Zeus AI general questions",
                    "examples": ["Zeus what is the weather?", "Zeus tell me a joke"],
                    "available": zeus_available
                },
                {
                    "command": "Zeus search <query>",
                    "description": "Search the web for information",
                    "examples": ["Zeus search Python tutorials"],
                    "available": search_available
                }
            ],
            "News & Information": [
                {
                    "command": "news",
                    "description": "Get latest news headlines",
                    "examples": ["news", "ข่าว"],
                    "available": True
                },
                {
                    "command": "/special news",
                    "description": "Get specialized news (sports, tourism, etc.)",
                    "examples": ["/special news"],
                    "available": True
                }
            ],
            "Calendar & Reminders": [
                {
                    "command": "Zeus calendar",
                    "description": "View your upcoming events and reminders",
                    "examples": ["Zeus calendar", "my events", "my reminders"],
                    "available": settings.is_calendar_configured()
                },
                {
                    "command": "Zeus add event",
                    "description": "Create event with customizable reminders (7/3/1 days)",
                    "examples": ["Zeus add event", "Zeus remind me"],
                    "available": settings.is_calendar_configured()
                },
                {
                    "command": "Zeus add [date] [title]",
                    "description": "Quick add: Zeus add Jan 15 Birthday party",
                    "examples": ["Zeus add tomorrow Meeting", "Zeus add 15/01 Conference"],
                    "available": settings.is_calendar_configured()
                },
                {
                    "command": "Zeus scrape",
                    "description": "AI-powered date extraction from recent messages",
                    "examples": ["Zeus scrape", "Zeus scan messages"],
                    "available": settings.is_calendar_configured()
                },
                {
                    "command": "Zeus remove event",
                    "description": "Delete events with multi-select support",
                    "examples": ["Zeus remove event", "Zeus delete event"],
                    "available": settings.is_calendar_configured()
                }
            ],
            "Image Analysis": [
                {
                    "command": "Zeus profile",
                    "description": "Psychological profiling from photos using FBI/Ekman/Navarro frameworks",
                    "examples": ["Zeus profile", "Zeus analyze this photo"],
                    "rate_limit": "3 analyses/hour (admins unlimited)" if not is_admin else "Unlimited",
                    "available": settings.is_profiler_configured()
                },
                {
                    "command": "Zeus analyze this",
                    "description": "General image Q&A with GPT-4o vision",
                    "examples": ["Zeus analyze this", "analyze image", "examine this photo"],
                    "rate_limit": "5 analyses/hour (admins unlimited)" if not is_admin else "Unlimited",
                    "available": settings.is_github_models_configured()
                }
            ]
        }

        # Admin-only commands
        if is_admin:
            categories["Admin Commands"] = [
                {
                    "command": "/admin help",
                    "description": "Show admin command reference",
                    "examples": ["/admin help"],
                    "available": True
                },
                {
                    "command": "/admin stats",
                    "description": "View bot usage statistics",
                    "examples": ["/admin stats"],
                    "available": True
                },
                {
                    "command": "/admin leave",
                    "description": "Make bot leave current group/room",
                    "examples": ["/admin leave"],
                    "available": chat_type in ["group chat", "room chat"]
                },
                {
                    "command": "/admin purge",
                    "description": "Clear chat session data",
                    "examples": ["/admin purge"],
                    "available": True
                },
                {
                    "command": "/admin confirm <token>",
                    "description": "Confirm destructive admin actions",
                    "examples": ["/admin confirm ABC123"],
                    "available": True
                }
            ]

        return categories

    def _get_adaptive_tips(self, is_admin: bool, chat_type: str) -> List[str]:
        """Get contextual tips based on user status and chat type."""
        tips = []

        # Interactive tutorial prompts
        tips.append("📚 Try 'Zeus calendar' to explore the events feature")
        tips.append("🎓 Use 'Zeus scrape' to see AI date extraction in action")
        
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
        
        if settings.is_google_translate_configured():
            tips.append("⚡ Professional Google Translate is active")
        else:
            tips.append("🔄 Using LibreTranslate (free tier)")

        tips.append("😴 Bot sleeps after 24h of inactivity - wake with 'Dear Zeus'")
        
        # Advanced search tip
        if settings.is_brave_search_configured():
            tips.append("🔍 Advanced: 'Zeus search' for web results with AI summary")

        return tips

    def _create_help_flex_message(self, categories: Dict[str, List[Dict[str, Any]]],
                                tips: List[str], chat_type: str) -> FlexMessage:
        """Create a visually appealing Flex Message for help content."""
        # Build body contents
        body_contents = []

        # Header
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "🗡️ ZEUS HELP SYSTEM",
                    "weight": "bold",
                    "size": "xl",
                    "color": "#1F2937",
                    "align": "center"
                },
                {
                    "type": "text",
                    "text": f"God-King of Olympus • {chat_type.title()}",
                    "size": "sm",
                    "color": "#6B7280",
                    "align": "center",
                    "margin": "sm"
                }
            ],
            "backgroundColor": "#F3F4F6",
            "paddingAll": "16px",
            "cornerRadius": "8px",
            "margin": "none"
        })

        # Command categories
        for category_name, commands in categories.items():
            available_commands = [cmd for cmd in commands if cmd["available"]]

            if not available_commands:
                continue

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
                        "margin": "none"
                    }
                ],
                "backgroundColor": "#FFFFFF",
                "borderColor": "#E5E7EB",
                "borderWidth": "1px",
                "cornerRadius": "8px",
                "paddingAll": "12px",
                "margin": "md"
            }

            command_contents = []
            for cmd in available_commands:
                cmd_box_contents = [
                    {
                        "type": "text",
                        "text": f"• {cmd['command']}",
                        "weight": "bold",
                        "size": "sm",
                        "color": "#1F2937",
                        "wrap": True
                    },
                    {
                        "type": "text",
                        "text": cmd['description'],
                        "size": "xs",
                        "color": "#6B7280",
                        "wrap": True,
                        "margin": "xs"
                    }
                ]
                
                # Add rate limit info if available
                if 'rate_limit' in cmd and cmd['rate_limit']:
                    cmd_box_contents.append({
                        "type": "text",
                        "text": f"⏱️ {cmd['rate_limit']}",
                        "size": "xxs",
                        "color": "#DC2626",
                        "wrap": True,
                        "margin": "xs"
                    })
                
                cmd_box_contents.append({
                    "type": "text",
                    "text": f"Example: {cmd['examples'][0]}",
                    "size": "xxs",
                    "color": "#9CA3AF",
                    "wrap": True,
                    "margin": "xs"
                })
                
                command_contents.append({
                    "type": "box",
                    "layout": "vertical",
                    "contents": cmd_box_contents,
                    "margin": "sm"
                })

            category_box["contents"].extend(command_contents)
            body_contents.append(category_box)

        # Tips section
        if tips:
            tips_box = {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "💡 WISE COUNSEL FROM ZEUS",
                        "weight": "bold",
                        "size": "md",
                        "color": "#1F2937",
                        "margin": "none"
                    }
                ],
                "backgroundColor": "#FEF3C7",
                "borderColor": "#F59E0B",
                "borderWidth": "1px",
                "cornerRadius": "8px",
                "paddingAll": "12px",
                "margin": "md"
            }

            tip_contents = []
            for tip in tips[:3]:  # Limit to 3 tips
                tip_contents.append({
                    "type": "text",
                    "text": tip,
                    "size": "xs",
                    "color": "#92400E",
                    "wrap": True,
                    "margin": "xs"
                })

            tips_box["contents"].extend(tip_contents)
            body_contents.append(tips_box)

        # Footer
        body_contents.append({
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "separator",
                    "color": "#E5E7EB",
                    "margin": "md"
                },
                {
                    "type": "text",
                    "text": "⚡ Powered by Zeus • Ruler of Olympus",
                    "size": "xxs",
                    "color": "#9CA3AF",
                    "align": "center"
                }
            ],
            "paddingAll": "8px"
        })

        flex_dict = {
            "type": "bubble",
            "size": "giga",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": body_contents,
                "spacing": "none",
                "paddingAll": "16px"
            },
            "styles": {
                "body": {
                    "backgroundColor": "#FAFAFA"
                }
            }
        }

        return FlexMessage(
            altText="Zeus Help System - Command Reference",
            contents=FlexContainer.from_dict(flex_dict),
            quickReply=None,
        )

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Handle if text is a help command."""
        return self._is_help_command(text)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Provide comprehensive help with contextual information."""
        user_id = getattr(event.source, "user_id", None) if event.source else None
        is_admin = privilege_service.is_admin(user_id)
        chat_type = self._get_chat_type(event)

        # Availability is contextual.
        # - Private chats: Zeus AI/search are allowed (if configured)
        # - Groups/rooms: obey Zeus group rules for non-admins (admins bypass)
        source = getattr(event, "source", None)
        group_id = getattr(source, "group_id", None) if source else None
        room_id = getattr(source, "room_id", None) if source else None

        if chat_type == "private chat":
            zeus_available = True
            search_available = settings.is_brave_search_configured()
        else:
            zeus_available = settings.is_zeus_allowed_in_group(
                group_id, room_id, user_is_admin=is_admin
            )
            search_available = settings.is_brave_search_configured() and zeus_available

        with tracer.start_as_current_span("help_agent.handle") as span:
            span.set_attribute("help.user_id", user_id or "unknown")
            span.set_attribute("help.is_admin", is_admin)
            span.set_attribute("help.chat_type", chat_type)

            try:
                # Get contextual command categories and tips
                categories = self._get_command_categories(
                    is_admin, chat_type, zeus_available, search_available
                )
                tips = self._get_adaptive_tips(is_admin, chat_type)

                # Create help message
                help_message = self._create_help_flex_message(categories, tips, chat_type)

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
                        text="🗡️ ZEUS HELP SYSTEM\n\n"
                             "Available commands:\n"
                             "• help - Show this menu\n"
                             "• Dear Zeus - Wake from sleep\n"
                             "• amen - Sleep for 24h\n"
                             "• Thai/English text - Auto-translate\n\n"
                             "For admin commands: /admin help",
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