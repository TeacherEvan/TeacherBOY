"""Translation agent - Handles Thai/English translation with session management."""

import logging
import re
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from .base_agent import BaseAgent
from src.services.translation_service import translation_service
from src.services.google_translation import google_translation_service
from src.services.session_manager import session_manager
from src.services.rate_limiter import rate_limiter

logger = logging.getLogger(__name__)


class TranslationAgent(BaseAgent):
    """Agent for handling Thai/English translation with smart session management."""

    def __init__(self):
        super().__init__(
            name="TranslationAgent",
            description="Thai/English translation with continuous session mode",
        )

    def get_priority(self) -> int:
        """Translation has high priority."""
        return 10

    def contains_thai(self, text: str) -> bool:
        """Check if text contains Thai characters."""
        return bool(re.search(r"[\u0E00-\u0E7F]", text))

    def is_sleep_command(self, text: str) -> bool:
        """
        Check if text is a sleep command (puts bot to sleep for 24 hours).

        Sleep patterns: "Thank you TeacherBoy", "Thanks TeacherBoy", etc.
        """
        text_lower = text.lower().strip()
        sleep_patterns = [
            r"^thanks?\s+teacherboy[\s.!]*$",
            r"^thank\s+you\s+teacherboy[\s.!]*$",
            r"^thx\s+teacherboy[\s.!]*$",
            r"^ty\s+teacherboy[\s.!]*$",
            r"^ขอบคุณ\s*teacherboy[\s.!]*$",
            r"^ขอบใจ\s*teacherboy[\s.!]*$",
        ]
        return any(re.search(pattern, text_lower) for pattern in sleep_patterns)

    def is_wake_command(self, text: str) -> bool:
        """
        Check if text is a wake command (wakes bot from sleep).

        Wake pattern: "TeacherBoy" alone (exact match, not among other text)
        """
        # Allow for case-insensitive "teacherboy" with optional trailing punctuation/whitespace
        return bool(re.match(r"^teacherboy[\s.!]*$", text.lower().strip()))

    def is_exit_command(self, text: str) -> bool:
        """Check if text is an exit command (ends session but doesn't sleep)."""
        # Sleep command is now the primary way to exit
        return self.is_sleep_command(text)

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Wake command when sleeping (to reactivate)
        2. Thai text detected (auto-start session)
        3. Session is active for this chat
        4. Sleep command (to properly put bot to sleep)
        """
        chat_id = self._get_chat_id(event)

        # Always handle wake command when sleeping
        if self.is_wake_command(text) and session_manager.is_sleeping(chat_id):
            return True

        # Don't handle anything else if sleeping
        if session_manager.is_sleeping(chat_id):
            return False

        # Always handle sleep commands if session is active
        if self.is_sleep_command(text):
            return session_manager.is_session_active(chat_id)

        # Handle if Thai detected or session is active
        return self.contains_thai(text) or session_manager.is_session_active(chat_id)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process translation request."""
        chat_id = self._get_chat_id(event)
        user_id = event.source.user_id

        try:
            # Handle wake command (when sleeping)
            if self.is_wake_command(text) and session_manager.is_sleeping(chat_id):
                session_manager.wake_chat(chat_id)
                wake_message = self._create_wake_message()
                line_bot_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[wake_message])
                )
                logger.info(f"☀️ Chat {chat_id} woken up by user")
                return True

            # Handle sleep command
            if self.is_sleep_command(text):
                session_manager.sleep_chat(chat_id, hours=24)
                sleep_message = self._create_sleep_message()
                line_bot_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[sleep_message])
                )
                logger.info(f"😴 Chat {chat_id} put to sleep for 24 hours")
                return True

            # Check for rate limiting
            if not rate_limiter.is_allowed(chat_id):
                reset_seconds = rate_limiter.get_reset_time(chat_id)
                rate_limit_message = self._create_rate_limit_message(reset_seconds)
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token, messages=[rate_limit_message]
                    )
                )
                logger.warning(f"⚠️  Rate limited chat {chat_id}")
                return True

            # Check for duplicate message
            if session_manager.is_duplicate_message(chat_id, text):
                logger.info(f"🔁 Skipping duplicate message in chat {chat_id}")
                # Silently skip duplicate - no need to reply
                return True

            # Start session if Thai detected
            if self.contains_thai(text):
                if not session_manager.is_session_active(chat_id):
                    session_manager.start_session(chat_id, user_id)
                    logger.info(f"🔥 Translation session started for chat {chat_id}")

            # Translate the message
            translated_text = await self._translate_message(text)

            if translated_text:
                # Send simple text message as requested
                text_message = TextMessage(text=translated_text)

                line_bot_api.reply_message(
                    ReplyMessageRequest(reply_token=event.reply_token, messages=[text_message])
                )
                logger.info(f"✅ Translation sent for chat {chat_id}")
                return True
            else:
                logger.error("Translation failed - no result")
                return False

        except Exception as e:
            logger.error(f"❌ Translation agent error: {e}", exc_info=True)
            return False

    async def _translate_message(self, text: str) -> str:
        """Translate using Google (primary) or LibreTranslate (fallback)."""
        # Try Google Translate first
        if google_translation_service.is_configured():
            result = await google_translation_service.auto_translate(text)
            if result:
                return result
            logger.warning("⚠️  Google Translate failed, trying LibreTranslate...")

        # Fallback to LibreTranslate
        if self.contains_thai(text):
            return await translation_service.translate(text, "th", "en")
        else:
            return await translation_service.translate(text, "en", "th")

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
        if hasattr(event.source, "group_id"):
            return f"group_{event.source.group_id}"
        elif hasattr(event.source, "room_id"):
            return f"room_{event.source.room_id}"
        else:
            return f"user_{event.source.user_id}"

    def _create_translation_flex(
        self, original_text: str, translated_text: str, source_lang: str, target_lang: str
    ) -> FlexMessage:
        """
        Create a visually stunning, modern Flex Message for translation results.

        Features:
        - Gradient-style hero section with brand colors
        - Clear visual hierarchy with proper spacing
        - Emoji indicators for language detection
        - Professional typography and layout
        - Accessible color contrast

        Args:
            original_text: Original message text
            translated_text: Translated message text
            source_lang: Source language name
            target_lang: Target language name

        Returns:
            FlexMessage with beautiful, responsive design
        """
        # Modern color palette
        primary_color = "#667EEA"  # Indigo
        secondary_color = "#764BA2"  # Purple
        success_color = "#10B981"  # Emerald
        text_primary = "#1F2937"  # Gray-800
        text_secondary = "#6B7280"  # Gray-500
        text_muted = "#9CA3AF"  # Gray-400

        # Language emoji mapping
        lang_emoji = {"Thai": "🇹🇭", "English": "🇬🇧"}

        flex_dict = {
            "type": "bubble",
            "size": "giga",
            "hero": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {
                                "type": "icon",
                                "url": "https://scdn.line-apps.com/n/channel_devcenter/img/fx/01_1_cafe.png",
                                "size": "sm",
                            },
                            {
                                "type": "text",
                                "text": "TeacherBOY Translate",
                                "weight": "bold",
                                "size": "lg",
                                "color": "#ffffff",
                                "margin": "md",
                                "flex": 0,
                            },
                        ],
                        "spacing": "sm",
                    },
                    {
                        "type": "box",
                        "layout": "baseline",
                        "contents": [
                            {"type": "text", "text": "⚡", "size": "sm"},
                            {
                                "type": "text",
                                "text": "Lightning Fast Translation",
                                "size": "xs",
                                "color": "#ffffff",
                                "opacity": "0.8",
                                "margin": "sm",
                                "flex": 0,
                            },
                        ],
                        "margin": "sm",
                    },
                ],
                "backgroundColor": primary_color,
                "paddingAll": "20px",
                "paddingBottom": "16px",
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    # Original Text Section
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": lang_emoji.get(source_lang, "🌐"),
                                        "size": "sm",
                                        "flex": 0,
                                    },
                                    {
                                        "type": "text",
                                        "text": source_lang.upper(),
                                        "size": "xs",
                                        "color": text_secondary,
                                        "weight": "bold",
                                        "margin": "sm",
                                        "flex": 0,
                                    },
                                ],
                                "margin": "none",
                            },
                            {
                                "type": "text",
                                "text": original_text,
                                "size": "md",
                                "wrap": True,
                                "color": text_primary,
                                "margin": "md",
                                "maxLines": 10,
                            },
                        ],
                        "backgroundColor": "#F9FAFB",
                        "cornerRadius": "8px",
                        "paddingAll": "16px",
                        "margin": "none",
                    },
                    # Arrow Indicator
                    {
                        "type": "box",
                        "layout": "horizontal",
                        "contents": [
                            {"type": "filler"},
                            {
                                "type": "box",
                                "layout": "vertical",
                                "contents": [
                                    {
                                        "type": "text",
                                        "text": "↓",
                                        "size": "xl",
                                        "color": success_color,
                                        "align": "center",
                                        "weight": "bold",
                                    }
                                ],
                                "flex": 0,
                            },
                            {"type": "filler"},
                        ],
                        "margin": "md",
                    },
                    # Translated Text Section
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "box",
                                "layout": "baseline",
                                "contents": [
                                    {"type": "text", "text": "✨", "size": "sm", "flex": 0},
                                    {
                                        "type": "text",
                                        "text": lang_emoji.get(target_lang, "🌐"),
                                        "size": "sm",
                                        "margin": "sm",
                                        "flex": 0,
                                    },
                                    {
                                        "type": "text",
                                        "text": target_lang.upper(),
                                        "size": "xs",
                                        "color": primary_color,
                                        "weight": "bold",
                                        "margin": "sm",
                                        "flex": 0,
                                    },
                                ],
                                "margin": "none",
                            },
                            {
                                "type": "text",
                                "text": translated_text,
                                "size": "md",
                                "wrap": True,
                                "color": text_primary,
                                "weight": "bold",
                                "margin": "md",
                                "maxLines": 10,
                            },
                        ],
                        "backgroundColor": "#EEF2FF",
                        "cornerRadius": "8px",
                        "paddingAll": "16px",
                        "margin": "md",
                        "borderColor": primary_color,
                        "borderWidth": "2px",
                    },
                ],
                "spacing": "none",
                "paddingAll": "20px",
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {"type": "separator", "color": "#E5E7EB"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": '💡 Tip: Say "Thank you TeacherBoy" to sleep for 24h',
                                "size": "xxs",
                                "color": text_muted,
                                "align": "center",
                                "wrap": True,
                            }
                        ],
                        "margin": "md",
                    },
                ],
                "paddingAll": "12px",
                "backgroundColor": "#FAFAFA",
            },
            "styles": {"footer": {"separator": False}},
        }

        return FlexMessage(
            alt_text=f"Translation: {original_text[:50]}...",
            contents=FlexContainer.from_dict(flex_dict),
        )

    def _create_goodbye_message(self) -> FlexMessage:
        """
        Create an engaging goodbye Flex Message with modern design.

        Features beautiful animations-ready design with clear
        call-to-action for re-engagement.

        Returns:
            FlexMessage with goodbye/session-end message
        """
        primary_color = "#667EEA"

        flex_dict = {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "👋", "size": "4xl", "align": "center"}
                        ],
                        "paddingBottom": "md",
                    },
                    {
                        "type": "text",
                        "text": "ลาก่อน",
                        "weight": "bold",
                        "size": "xxl",
                        "align": "center",
                        "color": primary_color,
                    },
                    {
                        "type": "text",
                        "text": "Goodbye!",
                        "size": "md",
                        "color": "#6B7280",
                        "align": "center",
                        "margin": "sm",
                    },
                    {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "Translation Mode",
                                "size": "xs",
                                "color": "#9CA3AF",
                                "align": "center",
                            },
                            {
                                "type": "text",
                                "text": "DEACTIVATED",
                                "size": "sm",
                                "weight": "bold",
                                "color": "#EF4444",
                                "align": "center",
                                "margin": "xs",
                            },
                        ],
                        "margin": "xl",
                        "backgroundColor": "#FEE2E2",
                        "cornerRadius": "8px",
                        "paddingAll": "12px",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🚀 Send Thai text anytime to start translating again!",
                                "size": "sm",
                                "color": "#374151",
                                "align": "center",
                                "wrap": True,
                                "weight": "bold",
                            }
                        ],
                        "margin": "xl",
                        "backgroundColor": "#F3F4F6",
                        "cornerRadius": "8px",
                        "paddingAll": "14px",
                    },
                ],
                "paddingAll": "24px",
                "spacing": "none",
            },
            "styles": {"body": {"backgroundColor": "#FFFFFF"}},
        }

        return FlexMessage(
            alt_text="Translation session ended - Goodbye!",
            contents=FlexContainer.from_dict(flex_dict),
        )

    def _create_rate_limit_message(self, reset_seconds: int) -> FlexMessage:
        """
        Create a friendly rate limit notification Flex Message.

        Args:
            reset_seconds: Seconds until rate limit resets

        Returns:
            FlexMessage with rate limit notification
        """
        warning_color = "#F59E0B"  # Amber

        flex_dict = {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "⏳", "size": "4xl", "align": "center"}
                        ],
                        "paddingBottom": "md",
                    },
                    {
                        "type": "text",
                        "text": "Rate Limit Reached",
                        "weight": "bold",
                        "size": "xl",
                        "align": "center",
                        "color": warning_color,
                    },
                    {
                        "type": "text",
                        "text": "คุณแปลเร็วเกินไปค่ะ!",
                        "size": "sm",
                        "color": "#6B7280",
                        "align": "center",
                        "margin": "sm",
                    },
                    {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"Please wait {reset_seconds} seconds",
                                "size": "sm",
                                "color": "#374151",
                                "align": "center",
                                "wrap": True,
                            },
                            {
                                "type": "text",
                                "text": "กรุณารอสักครู่นะคะ 😊",
                                "size": "xs",
                                "color": "#9CA3AF",
                                "align": "center",
                                "margin": "sm",
                            },
                        ],
                        "margin": "xl",
                        "backgroundColor": "#FEF3C7",
                        "cornerRadius": "8px",
                        "paddingAll": "14px",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "💡 Limit: 10 translations per minute",
                                "size": "xxs",
                                "color": "#9CA3AF",
                                "align": "center",
                            }
                        ],
                        "margin": "xl",
                    },
                ],
                "paddingAll": "24px",
                "spacing": "none",
            },
            "styles": {"body": {"backgroundColor": "#FFFFFF"}},
        }

        return FlexMessage(
            alt_text="Rate limit reached - please wait",
            contents=FlexContainer.from_dict(flex_dict),
        )

    def _create_sleep_message(self) -> FlexMessage:
        """
        Create a sleep notification Flex Message.

        Shows that the bot is going to sleep for 24 hours and how to wake it.

        Returns:
            FlexMessage with sleep notification
        """
        sleep_color = "#6366F1"  # Indigo

        flex_dict = {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "😴", "size": "4xl", "align": "center"}
                        ],
                        "paddingBottom": "md",
                    },
                    {
                        "type": "text",
                        "text": "ราตรีสวัสดิ์",
                        "weight": "bold",
                        "size": "xxl",
                        "align": "center",
                        "color": sleep_color,
                    },
                    {
                        "type": "text",
                        "text": "Good Night!",
                        "size": "md",
                        "color": "#6B7280",
                        "align": "center",
                        "margin": "sm",
                    },
                    {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "TeacherBOY",
                                "size": "xs",
                                "color": "#9CA3AF",
                                "align": "center",
                            },
                            {
                                "type": "text",
                                "text": "SLEEPING FOR 24 HOURS",
                                "size": "sm",
                                "weight": "bold",
                                "color": sleep_color,
                                "align": "center",
                                "margin": "xs",
                            },
                        ],
                        "margin": "xl",
                        "backgroundColor": "#EEF2FF",
                        "cornerRadius": "8px",
                        "paddingAll": "12px",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": '☀️ Say "TeacherBoy" to wake me up anytime!',
                                "size": "sm",
                                "color": "#374151",
                                "align": "center",
                                "wrap": True,
                                "weight": "bold",
                            }
                        ],
                        "margin": "xl",
                        "backgroundColor": "#F3F4F6",
                        "cornerRadius": "8px",
                        "paddingAll": "14px",
                    },
                ],
                "paddingAll": "24px",
                "spacing": "none",
            },
            "styles": {"body": {"backgroundColor": "#FFFFFF"}},
        }

        return FlexMessage(
            alt_text="TeacherBOY sleeping for 24 hours",
            contents=FlexContainer.from_dict(flex_dict),
        )

    def _create_wake_message(self) -> FlexMessage:
        """
        Create a wake notification Flex Message.

        Shows that the bot is now awake and ready to translate.

        Returns:
            FlexMessage with wake notification
        """
        wake_color = "#10B981"  # Emerald

        flex_dict = {
            "type": "bubble",
            "size": "kilo",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {"type": "text", "text": "☀️", "size": "4xl", "align": "center"}
                        ],
                        "paddingBottom": "md",
                    },
                    {
                        "type": "text",
                        "text": "สวัสดี!",
                        "weight": "bold",
                        "size": "xxl",
                        "align": "center",
                        "color": wake_color,
                    },
                    {
                        "type": "text",
                        "text": "Good Morning!",
                        "size": "md",
                        "color": "#6B7280",
                        "align": "center",
                        "margin": "sm",
                    },
                    {"type": "separator", "margin": "xl", "color": "#E5E7EB"},
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "TeacherBOY",
                                "size": "xs",
                                "color": "#9CA3AF",
                                "align": "center",
                            },
                            {
                                "type": "text",
                                "text": "AWAKE & READY!",
                                "size": "sm",
                                "weight": "bold",
                                "color": wake_color,
                                "align": "center",
                                "margin": "xs",
                            },
                        ],
                        "margin": "xl",
                        "backgroundColor": "#D1FAE5",
                        "cornerRadius": "8px",
                        "paddingAll": "12px",
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": "🚀 Send Thai text to start translating!",
                                "size": "sm",
                                "color": "#374151",
                                "align": "center",
                                "wrap": True,
                                "weight": "bold",
                            }
                        ],
                        "margin": "xl",
                        "backgroundColor": "#F3F4F6",
                        "cornerRadius": "8px",
                        "paddingAll": "14px",
                    },
                ],
                "paddingAll": "24px",
                "spacing": "none",
            },
            "styles": {"body": {"backgroundColor": "#FFFFFF"}},
        }

        return FlexMessage(
            alt_text="TeacherBOY is awake!",
            contents=FlexContainer.from_dict(flex_dict),
        )
