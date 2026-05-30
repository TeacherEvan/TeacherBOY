"""Translation agent - Handles Thai/English translation with session management."""

import asyncio
import logging
import re
from typing import Optional
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
from src.services.metrics_service import metrics_service
from src.utils.tracing import get_tracer
from src.config import settings
from src.services.privilege_service import privilege_service

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class TranslationAgent(BaseAgent):
    """Agent for handling Thai/English translation with smart session management."""

    _NEWS_TRIGGERS = {"news", "ข่าว", "นิวส์"}

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

        Sleep patterns: "good night zeus", "sleep zeus", "zeus sleep" (case insensitive)
        """
        text_lower = text.lower().strip()
        # Pattern for explicit sleep commands addressing Zeus
        sleep_pattern = r"^(good\s*night\s*zeus|sleep\s*zeus|zeus\s*sleep)[\s.!]*$"
        return bool(re.search(sleep_pattern, text_lower))

    def is_wake_command(self, text: str) -> bool:
        """
        Check if text is a wake command (wakes bot from sleep).

        Wake pattern: Any message starting with "Zeus"
        """
        # Wake up if message starts with "Zeus"
        zeus_pattern = r"^zeus\b"
        return bool(re.match(zeus_pattern, text.lower().strip()))

    def is_help_command(self, text: str) -> bool:
        """Check if text is a help command."""
        return text.lower().strip() in {"help", "/help"}



    def _is_private_chat(self, event: MessageEvent) -> bool:
        if event.source and getattr(event.source, "group_id", None):
            return False
        if event.source and getattr(event.source, "room_id", None):
            return False
        return True



    def is_exit_command(self, text: str) -> bool:
        """Check if text is an exit command (ends session but doesn't sleep)."""
        # Sleep command is now the primary way to exit
        return self.is_sleep_command(text)

    def is_news_trigger(self, text: str) -> bool:
        """Check if text is a news trigger word (should be handled by NewsAgent)."""
        text_clean = re.sub(r"[\s.!?]+$", "", text.lower().strip())
        return text_clean in self._NEWS_TRIGGERS

    def is_special_news_command(self, text: str) -> bool:
        """Check if text is the reserved /special news command (handled elsewhere)."""
        text_clean = re.sub(r"\s+", " ", text.lower().strip())
        return text_clean == "/special news"

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Wake command (always, even if not sleeping - to confirm awake status)
        2. Thai text detected (auto-start session)
        3. Session is active for this chat
        4. Sleep command (to properly put bot to sleep)

        NOTE: Skip news triggers ("news", "ข่าว") - let NewsAgent handle them.
        """
        chat_id = self._get_chat_id(event)

        # Help is handled by HelpAgent in production, but keep a minimal help
        # path here for backwards-compatible tests and direct invocation.
        if self.is_help_command(text):
            return True



        # Always handle wake command (even if not sleeping)
        if self.is_wake_command(text):
            return True

        # Always handle sleep commands (even if no active translation session).
        # Exception: if the chat is currently in a NewsAgent flow, let NewsAgent
        # own the shutdown phrase so it can exit its flow cleanly.
        if self.is_sleep_command(text):
            try:
                from src.services.news_session_manager import news_session_manager
            except ImportError as exc:
                logger.warning(
                    "⚠️ news_session_manager not available when handling sleep command: %s",
                    exc,
                    exc_info=True,
                )
            else:
                try:
                    if news_session_manager.is_in_news_flow(chat_id):
                        return False
                except Exception as exc:
                    logger.error(
                        "❌ Error while checking news flow state in TranslationAgent: %s",
                        exc,
                        exc_info=True,
                    )
            return True

        # Don't handle anything else if sleeping
        if session_manager.is_sleeping(chat_id):
            return False

        # Skip news triggers - let NewsAgent handle them
        if self.is_news_trigger(text):
            return False

        # Skip /special news - let SpecialNewsAgent handle it
        if self.is_special_news_command(text):
            return False

        # Auto-translation is disabled. Only explicit wake/help/sleep paths and
        # already-active sessions should be handled here.
        return session_manager.is_session_active(chat_id)

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """Process translation request."""
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None

        with tracer.start_as_current_span("translation_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)
            try:

                # Minimal help path (HelpAgent handles this in production).
                if self.is_help_command(text):
                    is_admin = privilege_service.is_admin(user_id)
                    msg = (
                        "User commands\n"
                        "- Send Thai to translate to English\n"
                        "- Send English to translate to Thai\n"
                        "- Dear Zeus (wake)\n"
                        "- amen (sleep)\n"
                    )
                    if is_admin:
                        msg += (
                            "\nAdmin commands\n"
                            "- /admin help\n"
                            "- /admin stats\n"
                        )
                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[
                                    TextMessage(
                                        text=msg,
                                        quickReply=None,
                                        quoteToken=None,
                                    )
                                ],
                                notificationDisabled=False,
                            ),
                        )
                    return True


                # Handle wake command
                if self.is_wake_command(text):
                    span.set_attribute("translation.command", "wake")
                    if session_manager.is_sleeping(chat_id):
                        session_manager.wake_chat(chat_id)
                        wake_message = self._create_wake_message()
                        if event.reply_token:
                            await asyncio.to_thread(
                                line_bot_api.reply_message,
                                ReplyMessageRequest(
                                    replyToken=event.reply_token,
                                    messages=[wake_message],
                                    notificationDisabled=False,
                                ),
                            )
                        logger.info(f"☀️ Chat {chat_id} woken up by user")
                    else:
                        # Already awake, confirm status
                        already_awake_msg = TextMessage(
                            text="I'm awake! 😊 and waiting!",
                            quickReply=None,
                            quoteToken=None,
                        )
                        if event.reply_token:
                            await asyncio.to_thread(
                                line_bot_api.reply_message,
                                ReplyMessageRequest(
                                    replyToken=event.reply_token,
                                    messages=[already_awake_msg],
                                    notificationDisabled=False,
                                ),
                            )
                        logger.info(f"✅ Chat {chat_id} confirmed awake status")
                    return True

                # Handle sleep command
                if self.is_sleep_command(text):
                    span.set_attribute("translation.command", "sleep")
                    session_manager.sleep_chat(chat_id, hours=24)
                    sleep_message = self._create_sleep_message()
                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[sleep_message],
                                notificationDisabled=False,
                            ),
                        )
                    logger.info(f"😴 Chat {chat_id} put to sleep for 24 hours")
                    return True

                # Check for rate limiting (skip for admins)
                if not privilege_service.is_admin(user_id) and not rate_limiter.is_allowed(chat_id, user_id):
                    span.set_attribute("translation.rate_limited", True)
                    metrics_service.record_rate_limited()
                    reset_seconds = rate_limiter.get_reset_time(chat_id, user_id)
                    rate_limit_message = self._create_rate_limit_message(reset_seconds, user_id)
                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[rate_limit_message],
                                notificationDisabled=False,
                            ),
                        )
                    logger.warning(f"⚠️  Rate limited chat {chat_id}, user {user_id}")
                    return True
                elif privilege_service.is_admin(user_id):
                    logger.debug(f"🔓 Admin {user_id} bypassed rate limit")

                # Check for duplicate message
                if session_manager.is_duplicate_message(chat_id, text):
                    span.set_attribute("translation.duplicate", True)
                    logger.info(f"🔁 Skipping duplicate message in chat {chat_id}")
                    # Silently skip duplicate - no need to reply
                    return True

                # Start session if Thai detected
                if self.contains_thai(text):
                    span.set_attribute("translation.detected", "th")
                    if not session_manager.is_session_active(chat_id):
                        session_manager.start_session(chat_id, user_id or "unknown")
                        logger.info(f"🔥 Translation session started for chat {chat_id}")
                else:
                    span.set_attribute("translation.detected", "en")

                # Translate the message
                translated_text = await self._translate_message(text, chat_id)

                if translated_text:
                    # Send simple text message as requested
                    text_message = TextMessage(
                        text=translated_text, quickReply=None, quoteToken=None
                    )

                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[text_message],
                                notificationDisabled=False,
                            ),
                        )
                    logger.info(f"✅ Translation sent for chat {chat_id}")
                    span.set_attribute("translation.success", True)
                    return True
                else:
                    logger.error("Translation failed - no result")
                    metrics_service.record_failed_translation()
                    span.set_attribute("translation.success", False)
                    return False

            except Exception as e:
                logger.error(f"❌ Translation agent error: {e}", exc_info=True)
                span.set_attribute("translation.error", True)
                return False

    async def _translate_message(self, text: str, chat_id: Optional[str] = None) -> str:
        """Translate using Google (primary) or LibreTranslate (fallback)."""
        # Try Google Translate first
        if google_translation_service.is_configured():
            with tracer.start_as_current_span("translation.translate.google") as span:
                span.set_attribute("translation.provider", "google")
                result = await google_translation_service.auto_translate(text)
            if result:
                metrics_service.record_translation("google", chat_id)
                return result
            logger.warning("⚠️  Google Translate failed, trying LibreTranslate...")

        # Fallback to LibreTranslate
        with tracer.start_as_current_span("translation.translate.libre") as span:
            span.set_attribute("translation.provider", "libretranslate")
            if self.contains_thai(text):
                result = await translation_service.translate(text, "th", "en")
            else:
                result = await translation_service.translate(text, "en", "th")

        if result:
            metrics_service.record_translation("libre", chat_id)
            return result

        # Record final failure only if both providers failed
        metrics_service.record_failed_translation()
        return "Translation failed"

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return f"group_{group_id}"
        if event.source and hasattr(event.source, "room_id"):
            room_id = getattr(event.source, "room_id", None)
            if room_id:
                return f"room_{room_id}"
        if event.source:
            user_id = getattr(event.source, "user_id", "unknown")
            return f"user_{user_id}"
        return "user_unknown"

    def _create_translation_flex(
        self,
        original_text: str,
        translated_text: str,
        source_lang: str,
        target_lang: str,
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
                                "text": "Zeus Translate",
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
                                    {
                                        "type": "text",
                                        "text": "✨",
                                        "size": "sm",
                                        "flex": 0,
                                    },
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
                                "text": '💡 Tip: Say "amen" to sleep for 24h',
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
            altText=f"Translation: {original_text[:50]}...",
            contents=FlexContainer.from_dict(flex_dict),
            quickReply=None,
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
                            {
                                "type": "text",
                                "text": "👋",
                                "size": "4xl",
                                "align": "center",
                            }
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
            altText="Translation session ended - Goodbye!",
            contents=FlexContainer.from_dict(flex_dict),
            quickReply=None,
        )

    def _create_rate_limit_message(self, reset_seconds: int, user_id: Optional[str] = None) -> TextMessage:
        """
        Create a friendly rate limit notification message with premium upgrade options.

        Args:
            reset_seconds: Seconds until rate limit resets
            user_id: User ID to check for premium eligibility

        Returns:
            TextMessage with rate limit notification
        """
        import os
        user_name = os.getenv("USER_NAME")

        # Check if this is a user-based limit breach
        is_user_limit = user_id and user_name and user_id == user_name

        if is_user_limit:
            message_text = (
                "⚡ Premium User Rate Limit\n"
                "You've reached your daily interaction limit!\n\n"
                f"⏳ Reset in: {reset_seconds // 3600}h {(reset_seconds % 3600) // 60}m\n\n"
                "💎 Upgrade to premium for unlimited access:\n"
                "• Higher daily limits\n"
                "• Priority support\n"
                "• Advanced features\n\n"
                "Contact admin for premium upgrade options!"
            )
        else:
            message_text = (
                "⏳ Rate Limit Reached\n"
                "คุณแปลเร็วเกินไปค่ะ!\n\n"
                f"Please wait {reset_seconds} seconds\n"
                "กรุณารอสักครู่นะคะ 😊\n\n"
                "💡 Limit: 10 translations per minute\n\n"
                "💎 Premium users get higher limits!"
            )

        return TextMessage(text=message_text, quickReply=None, quoteToken=None)

    def _create_sleep_message(self) -> TextMessage:
        """
        Create a sleep notification message.

        Shows that the bot is going to sleep for 24 hours and how to wake it.

        Returns:
            TextMessage with sleep notification
        """
        message_text = (
            "😴 ราตรีสวัสดิ์ Good Night!\n\n"
            "Zeus is sleeping for 24 hours.\n\n"
            '☀️ Say "Zeus" to wake me up anytime!'
        )

        return TextMessage(text=message_text, quickReply=None, quoteToken=None)

    def _create_wake_message(self) -> TextMessage:
        """
        Create a wake notification message.

        Shows that the bot is now awake and ready to translate.

        Returns:
            TextMessage with wake notification
        """
        message_text = (
            "☀️ สวัสดี! Good Morning!\n\n"
            "Zeus is now awake and ready!\n\n"
            "🚀 Send Thai text to start translating!"
        )

        return TextMessage(text=message_text, quickReply=None, quoteToken=None)
