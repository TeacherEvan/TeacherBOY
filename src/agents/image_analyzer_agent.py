"""
Image Analyzer Agent - General purpose image Q&A using vision AI.

This agent allows users to submit images and ask questions about them.
Unlike the Profiler (which focuses on psychological analysis), this agent
handles general image-based questions like:
- "What's on this menu?"
- "What does this sign say?"
- "What products are shown here?"

Flow:
1. User: "Ms. Green analyze this" / "analyze image"
2. Ms. Green: "Please send the image you'd like me to analyze (60 seconds)"
3. User: [sends image]
4. Ms. Green: "What would you like to know about this image?"
5. User: "What would be most enjoyable on this menu to a westerner?"
6. Ms. Green: [analyzes image and answers question]

Calendar Integration:
When dates are detected in an image (schedules, announcements, etc.),
the agent can offer to add them to the user's calendar with reminders.
"""

import asyncio
import base64
import json
import logging
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessageAction,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.bot_identity_service import get_bot_identity_service
from src.services.debrief_extraction_service import DebriefExtractionService
from src.services.debrief_formatter import DebriefFormatter
from src.services.gemini_service import gemini_service
from src.services.hermes_service import hermes_service
from src.services.hf_inference_service import hf_inference_service
from src.services.image_analyzer_session_manager import (
    image_analyzer_session_manager,
)
from src.services.metrics_service import metrics_service
from src.services.openrouter_service import openrouter_service
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import RateLimiter
from src.utils.llm_fallback import chat_completion_with_vision_fallback
from src.utils.tracing import get_tracer

from .base_agent import BaseAgent

# Instantiate debrief extraction service with the proper vision fallback
_debrief_extraction_service: DebriefExtractionService = DebriefExtractionService(
    llm_vision_fn=chat_completion_with_vision_fallback,
    default_vision_model="openai/gpt-4o",
)

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Rate limiter: 5 analyses per hour per chat (less expensive than profiler)
image_analyzer_rate_limiter = RateLimiter(max_requests=5, time_window_seconds=3600)

# Module-level constants for neutral scene detection (single source of truth)
NEUTRAL_SCENE_TERMS = frozenset(
    [
        "baby",
        "newborn",
        "breastfeed",
        "breast feeding",
        "breastfeeding",
        "family",
        "mother",
        "father",
        "child",
        "medical",
        "hospital",
        "food",
        "menu",
        "sign",
        "document",
        "receipt",
        "package",
        "product",
        "pet",
        "home",
        "household",
        "room",
        "care",
    ]
)

# Maximum image size (10MB) to prevent DoS via memory exhaustion
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024

# Retry configuration for LINE API calls
LINE_API_MAX_RETRIES = 3
LINE_API_BASE_DELAY = 1.0  # seconds


class ImageAnalyzerAgent(BaseAgent):
    """
    Agent for general-purpose image Q&A.

    Uses GPT-4o vision to analyze images and answer user questions.
    """

    # Trigger phrases that start an image analysis session
    PREFIXED_TRIGGERS = [
        "analyze",
        "examine",
        "look at",
        "debrief",
        "scrape",
    ]

    GENERIC_TRIGGERS = [
        "analyze",
        "analyze this",
        "analyze image",
        "examine this",
        "examine image",
        "look at this",
        "debrief",
        "debrief this",
        "scrape",
        "scrape this",
        "scrape image",
        "extract text",
        "extract text from image",
        "ocr",
    ]

    def __init__(self, http_client=None):
        """
        Initialize ImageAnalyzerAgent.

        Args:
            http_client: Shared HTTP client
        """
        super().__init__(
            name="ImageAnalyzerAgent",
            description="General purpose image Q&A using vision AI",
        )
        self.http_client = http_client
        # Cache for friend status checks with thread-safe access
        self._friend_cache: dict[str, tuple[bool, datetime]] = {}
        self._friend_cache_lock = asyncio.Lock()

    def _identity_name(self) -> str:
        return get_bot_identity_service().get_profile().display_name

    def _strip_identity_prefix(self, text: str) -> str:
        """Strip bot identity prefixes, including slash-separated identity chains."""
        normalized = re.sub(r"\s+", " ", (text or "").strip().lower())
        identity_service = get_bot_identity_service()
        profile = identity_service.get_profile()
        aliases = sorted(
            {profile.display_name.lower(), *profile.aliases},
            key=len,
            reverse=True,
        )

        for alias in aliases:
            if normalized.startswith(f"{alias}/"):
                return self._strip_identity_prefix(normalized[len(alias) + 1 :].lstrip())

        prefix, rest = identity_service.split_command_prefix(normalized)
        if prefix:
            return rest.lower().strip()

        return normalized

    def get_priority(self) -> int:
        """
        Image Analyzer priority - just after Profiler (7), before Search (8).

        This ensures profiler-specific triggers go to profiler first.
        """
        return 7  # Same as profiler (but profiler checks for "profile" keyword)

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

    async def _is_friend(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        """
        Check if user is a LINE friend of the bot.

        Uses LINE API get_profile() which returns error for non-friends.
        Results are cached for 1 minute (reduced from 5 minutes for security).
        Thread-safe with asyncio.Lock and includes retry logic for transient failures.

        Args:
            event: LINE message event
            line_bot_api: LINE Messaging API client

        Returns:
            True if user is a friend, False otherwise
        """
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            logger.warning("🖼️ No user_id found for friendship check")
            return False

        # Check cache with lock (1 minute TTL - reduced for security)
        async with self._friend_cache_lock:
            cached = self._friend_cache.get(user_id)
            if cached:
                is_friend, cached_at = cached
                age = (datetime.now(UTC) - cached_at).total_seconds()
                if age < 60:
                    return is_friend

        # Retry logic for LINE API call
        last_exception = None
        for attempt in range(LINE_API_MAX_RETRIES):
            try:
                await asyncio.to_thread(line_bot_api.get_profile, user_id)
                async with self._friend_cache_lock:
                    self._friend_cache[user_id] = (True, datetime.now(UTC))
                logger.info(f"🖼️ User {user_id} is a friend (verified via LINE API)")
                return True
            except ApiException as e:
                status = getattr(e, "status_code", "unknown")
                logger.info(
                    f"🖼️ User {user_id} is NOT a friend (ApiException: {status})",
                    exc_info=False,
                )
                async with self._friend_cache_lock:
                    self._friend_cache[user_id] = (False, datetime.now(UTC))
                return False
            except Exception as e:
                last_exception = e
                if attempt < LINE_API_MAX_RETRIES - 1:
                    delay = LINE_API_BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"🖼️ Friendship check failed for {user_id} (attempt {attempt + 1}/{LINE_API_MAX_RETRIES}): {e}. Retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        f"🖼️ Friendship check failed for {user_id} after {LINE_API_MAX_RETRIES} attempts: {last_exception}",
                        exc_info=False,
                    )
                    return False

        return False

    def invalidate_friend_cache(self, user_id: str) -> None:
        """Invalidate friend cache for a specific user (call when friend status may have changed)."""
        if user_id in self._friend_cache:
            del self._friend_cache[user_id]
            logger.info(f"🖼️ Invalidated friend cache for user {user_id}")

    async def _get_user_display_name(self, user_id: str, line_bot_api: MessagingApi) -> str:
        """
        Get user's display name from LINE API.

        Returns 'mortal' if unable to get the name.
        """
        try:
            profile = await asyncio.to_thread(line_bot_api.get_profile, user_id)
            return profile.display_name or "mortal"
        except Exception:
            return "mortal"

    def _is_trigger(self, text: str) -> bool:
        """Check if text contains a trigger phrase."""
        text_lower = text.lower().strip()

        # Don't trigger on profiler-specific phrases
        # These go to ProfilerAgent for facial/psychological analysis
        profiler_keywords = [
            "profile",
            "read face",
            "face analysis",
            "facial analysis",
            "read expression",
            "read emotions",
        ]
        if any(keyword in text_lower for keyword in profiler_keywords):
            return False

        # Debrief is a first-class trigger path.
        if "debrief" in text_lower and (
            text_lower.startswith("debrief") or "assistantbot debrief" in text_lower or "ms. green debrief" in text_lower
        ):
            return True

        command_text = self._strip_identity_prefix(text)

        # "m" is an exact-match shorthand for debrief mode — must NOT use startswith
        # because that would match ANY text beginning with 'm' (e.g. "Main room...")
        if command_text == "m" or text_lower.strip() == "m":
            return True

        if command_text != text_lower:
            return any(command_text.startswith(trigger) for trigger in self.PREFIXED_TRIGGERS + self.GENERIC_TRIGGERS)

        return any(text_lower.startswith(trigger) for trigger in self.GENERIC_TRIGGERS)

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Image message when waiting for image
        2. Text message when waiting for analysis choice (new/last)
        3. Text message when waiting for question
        4. Calendar confirmation response (yes/no add to calendar)
        5. Text message with trigger phrase (start session) - ONLY if no active session

        Session state checks MUST come before trigger checks to avoid re-triggering
        on Quick Reply button texts like "Analyze this", "Scrape this", "M".
        """
        # Check if any vision-capable provider is available
        if not (
            hermes_service.is_vision_configured()
            or openrouter_service.is_configured()  # OpenRouter uses vision model from settings
            or gemini_service.is_vision_configured()
            or hf_inference_service.is_vision_configured()
        ):
            return False

        message = getattr(event, "message", None)
        if message is None:
            return False

        message_type = getattr(message, "type", None)
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None

        # Case 1: Image message when waiting for image (highest priority for images)
        if message_type == "image":
            return await image_analyzer_session_manager.is_waiting_for_image(chat_id, user_id)

        # Case 2: Text message when waiting for analysis choice (new/last)
        if message_type == "text" and text:
            if await image_analyzer_session_manager.is_waiting_for_analysis_choice(chat_id, user_id):
                # Only accept 'new' or 'last' as valid choices
                choice = text.strip().lower()
                if choice in ("new", "last"):
                    return True
                # Invalid choice - will re-prompt in handle()
                return True

        # Case 3: Text message when waiting for question
        if message_type == "text" and text:
            if await image_analyzer_session_manager.is_waiting_for_question(chat_id, user_id):
                return True

            # Case 4: Calendar confirmation response
            text_lower = text.lower().strip()
            if await image_analyzer_session_manager.is_waiting_for_calendar_confirmation(chat_id, user_id):
                if any(kw in text_lower for kw in ["yes add", "no skip", "yes", "no", "ใช่", "ไม่"]):
                    return True

        # Case 5: Trigger phrase - start session (lowest priority, only if no active session)
        if message_type == "text" and text and self._is_trigger(text):
            return True

        return False

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """
        Process image analysis request through multi-step flow.

        Args:
            event: LINE message event
            text: Message text (empty for images)
            line_bot_api: LINE Messaging API client

        Returns:
            True if handled successfully
        """
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        message = getattr(event, "message", None)
        message_type = getattr(message, "type", None) if message else None

        with tracer.start_as_current_span("image_analyzer_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)

            try:
                # Step 1: Image received - store and ask for question (highest priority for images)
                if message_type == "image":
                    logger.debug("🖼️ handle: image received, routing to _handle_image")
                    return await self._handle_image(event, chat_id, user_id, line_bot_api, span)

                # Step 2: Analysis choice received (new/last) - before trigger to avoid re-triggering
                waiting_for_choice = await image_analyzer_session_manager.is_waiting_for_analysis_choice(chat_id, user_id)
                if message_type == "text" and waiting_for_choice:
                    logger.debug("🖼️ handle: waiting_for_analysis_choice=True, routing to _handle_analysis_choice")
                    return await self._handle_analysis_choice(event, text, chat_id, user_id, line_bot_api)

                # Step 3: Question received - analyze and respond (before trigger to handle "Analyze this" button)
                waiting_for_question = await image_analyzer_session_manager.is_waiting_for_question(chat_id, user_id)
                if message_type == "text" and waiting_for_question:
                    logger.debug("🖼️ handle: waiting_for_question=True, routing to _handle_question")
                    return await self._handle_question(event, text, chat_id, user_id, line_bot_api, span)

                # Step 4: Calendar confirmation response
                waiting_for_cal = await image_analyzer_session_manager.is_waiting_for_calendar_confirmation(chat_id, user_id)
                if message_type == "text" and waiting_for_cal:
                    logger.debug("🖼️ handle: waiting_for_calendar_confirmation=True, routing to _handle_calendar_confirmation")
                    return await self._handle_calendar_confirmation(event, text, chat_id, user_id, line_bot_api)

                # Step 5: Trigger phrase - start analysis choice flow (lowest priority, only if no active session)
                is_trigger = self._is_trigger(text)
                if message_type == "text" and is_trigger:
                    logger.debug(f"🖼️ handle: is_trigger=True, routing to _handle_trigger (text='{text[:50]}')")
                    return await self._handle_trigger(event, text, chat_id, user_id, line_bot_api)

                logger.debug(
                    f"🖼️ handle: no matching condition, message_type={message_type}, text='{text[:50] if text else None}'"
                )
                return False

            except Exception as e:
                logger.error(f"❌ ImageAnalyzerAgent error: {e}", exc_info=True)
                span.set_attribute("analyzer.error", str(e))
                await self._send_error_message(event, line_bot_api, str(e))
                await image_analyzer_session_manager.clear_session(chat_id)
                return False

    async def _process_direct_debrief(
        self,
        event: MessageEvent,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
        image_data: str,
    ) -> bool:
        """Process a direct debrief request when an image is already stored."""
        logger.info(f"📖 Processing direct debrief for chat {chat_id}")

        await self._send_analyzing_message(event, line_bot_api)

        # Use DebriefExtractionService for structured extraction
        try:
            debrief = await _debrief_extraction_service.extract_from_image(
                image_url_or_base64=image_data,
                chat_id=chat_id,
                date_str=datetime.now().strftime("%Y-%m-%d"),
            )
        except Exception as e:
            logger.error(f"❌ Debrief extraction failed: {e}")
            await self._send_error_message(event, line_bot_api, "Failed to analyze the image for debrief.")
            await image_analyzer_session_manager.clear_session(chat_id)
            return False

        # Format using the new daily debrief formatter
        formatted_msg = DebriefFormatter.format_daily_debrief(debrief)

        # Send via push (reply token already used for "analyzing" message)
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        user_id = getattr(event.source, "user_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            text_msg = TextMessage(text=formatted_msg, quickReply=None, quoteToken=None)
            await asyncio.to_thread(
                line_bot_api.push_message,
                PushMessageRequest(
                    to=target,
                    messages=[text_msg],
                    notificationDisabled=False,
                    customAggregationUnits=None,
                ),
            )

        logger.info(f"✅ Debrief sent for chat {chat_id}")
        await image_analyzer_session_manager.clear_session(chat_id)
        return True

    async def _handle_trigger(
        self,
        event: MessageEvent,
        text: str,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Handle trigger phrase - start choice or image session."""

        # Check rate limiting (skip for admins)
        if not privilege_service.is_admin(user_id):
            if not image_analyzer_rate_limiter.is_allowed(chat_id, user_id):
                metrics_service.record_rate_limited()
                reset_seconds = image_analyzer_rate_limiter.get_reset_time(chat_id, user_id)
                await self._send_rate_limit_message(event, line_bot_api, reset_seconds)
                return True
        else:
            # Structured audit log for admin rate limit bypass
            logger.warning(
                "SECURITY_AUDIT: Admin bypassed image analyzer rate limit",
                extra={
                    "event_type": "rate_limiter_bypass",
                    "admin_user_id": user_id,
                    "chat_id": chat_id,
                    "service": "image_analyzer",
                },
            )

        command_text = self._strip_identity_prefix(text)
        is_debrief = "debrief" in command_text or command_text.strip().lower() == "m"
        is_scrape = "scrape" in command_text or "ocr" in command_text or "extract text" in command_text

        # If debrief trigger and we already have an image stored, process immediately
        if is_debrief:
            session = await image_analyzer_session_manager.get_session(chat_id)
            if session and session.image_data:
                logger.info(f"📖 Direct debrief trigger detected for chat {chat_id}")
                return await self._process_direct_debrief(event, chat_id, user_id, line_bot_api, session.image_data)

        bare_analyze = command_text in ("analyze", "analyze this")

        if bare_analyze:
            await image_analyzer_session_manager.start_analysis_choice(chat_id, user_id)
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="New", text="new"),
                    ),
                    QuickReplyItem(
                        type="action",
                        imageUrl=None,
                        action=MessageAction(label="Last", text="last"),
                    ),
                ]
            )
            prompt_msg = TextMessage(
                text="New or Last",
                quickReply=quick_reply,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[prompt_msg],
                        notificationDisabled=False,
                    ),
                )
            logger.info(f"🖼️ Image analysis choice prompt sent for chat {chat_id}")
            return True

        analysis_mode = "debrief" if is_debrief else ("scrape" if is_scrape else "standard")
        await image_analyzer_session_manager.start_session(chat_id, user_id, analysis_mode=analysis_mode)

        prompt_text = (
            "🖼️ Please send the image you'd like me to analyze.\n\n"
            if analysis_mode != "debrief" and analysis_mode != "scrape"
            else (
                "🖼️ Please send the image you'd like me to debrief.\n\n"
                if analysis_mode == "debrief"
                else "🖼️ Please send the image you'd like me to extract text from.\n\n"
            )
        )
        prompt_msg = TextMessage(
            text=prompt_text
            + "(You have 60 seconds to send an image)\n\n"
            + (
                "ส่งภาพที่ต้องการให้วิเคราะห์ (60 วินาที)"
                if analysis_mode != "debrief" and analysis_mode != "scrape"
                else "ส่งภาพที่ต้องการให้สรุปเชิงวิเคราะห์ (60 วินาที)"
                if analysis_mode == "debrief"
                else "ส่งภาพที่ต้องการให้แยกข้อความ (60 วินาที)"
            ),
            quickReply=None,
            quoteToken=None,
        )

        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[prompt_msg],
                    notificationDisabled=False,
                ),
            )

        logger.info(f"🖼️ Image analysis session started for chat {chat_id}")
        return True

    async def _handle_analysis_choice(
        self,
        event: MessageEvent,
        text: str,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Handle New/Last choice after the bare analyze trigger."""
        choice = re.sub(r"\s+", " ", (text or "").strip().lower())

        if choice == "new":
            await image_analyzer_session_manager.start_session(chat_id, user_id, analysis_mode="standard")
            prompt_msg = TextMessage(
                text=(
                    "🖼️ Please send the image you'd like me to analyze.\n\n"
                    "(You have 60 seconds to send an image)\n\n"
                    "ส่งภาพที่ต้องการให้วิเคราะห์ (60 วินาที)"
                ),
                quickReply=None,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[prompt_msg],
                        notificationDisabled=False,
                    ),
                )
            return True

        if choice == "last":
            last_image = await image_analyzer_session_manager.get_last_image(chat_id)
            if not last_image:
                msg = TextMessage(
                    text=(
                        "⚡ I don't have a previous image for this chat yet.\n\n"
                        "Please send a new image instead.\n\n"
                        "ยังไม่มีภาพล่าสุดในห้องนี้ กรุณาส่งภาพใหม่"
                    ),
                    quickReply=None,
                    quoteToken=None,
                )
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[msg],
                            notificationDisabled=False,
                        ),
                    )
                await image_analyzer_session_manager.clear_session(chat_id)
                return True

            await image_analyzer_session_manager.start_session_with_image(
                chat_id,
                user_id,
                image_data=last_image,
                analysis_mode="standard",
            )

            prompt_msg = TextMessage(
                text=(
                    "⚡ I found the last image. What would you like to know about it?\n\n"
                    "(You have 60 seconds to ask)\n\n"
                    "พบภาพล่าสุดแล้ว! มีคำถามอะไรเกี่ยวกับภาพนี้?"
                ),
                quickReply=None,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[prompt_msg],
                        notificationDisabled=False,
                    ),
                )
            return True

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="New", text="new"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="Last", text="last"),
                ),
            ]
        )
        msg = TextMessage(text="New or Last", quickReply=quick_reply, quoteToken=None)
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[msg],
                    notificationDisabled=False,
                ),
            )
        return True

    async def _handle_image(
        self,
        event: MessageEvent,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
        span,
    ) -> bool:
        """Handle image receipt - store and prompt for question."""

        message_id = getattr(event.message, "id", None)
        if not isinstance(message_id, str) or not message_id.strip():
            await self._send_error_message(event, line_bot_api, "Could not retrieve image. Please try again.")
            return False

        # Download image
        logger.info(f"📸 Downloading image {message_id} from LINE...")
        image_bytes = await self._download_image(message_id)

        if not image_bytes:
            await self._send_error_message(event, line_bot_api, "Failed to download image. Please try again.")
            await image_analyzer_session_manager.clear_session(chat_id)
            return False

        span.set_attribute("image.size_bytes", len(image_bytes))

        # Convert to base64 and store in session manager
        image_base64 = base64.b64encode(image_bytes).decode("utf-8")
        image_data_url = f"data:image/jpeg;base64,{image_base64}"

        # CRITICAL: Clear original binary data after encoding
        del image_bytes  # Remove binary data from memory
        del image_base64  # Remove base64 string (data URL is kept in session)

        if not await image_analyzer_session_manager.store_image(chat_id, image_data_url):
            await self._send_error_message(
                event,
                line_bot_api,
                f"Session expired. Please start again with '{self._identity_name()} analyze this'.",
            )
            del image_data_url  # Clean up on error
            return False

        # Clear data URL reference now that it's stored in session manager
        del image_data_url

        # Present Daily Journal Quick Reply options immediately upon image receipt
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="🔍 Analyze", text="Analyze this"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="📝 Scrape", text="Scrape this"),
                ),
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label="📖 Generate Debrief", text="M"),
                ),
            ]
        )

        question_msg = TextMessage(
            text="⚡ Image received! What would you like to do?\\n\\n"
            "(Tap a button above, or type your question)\\n\\n"
            "ได้รับภาพแล้ว! ต้องการให้ทำอย่างไร?",
            quickReply=quick_reply,
            quoteToken=None,
        )

        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[question_msg],
                    notificationDisabled=False,
                ),
            )

        logger.info(f"🖼️ Image stored for chat {chat_id}, waiting for question")
        return True

    def _is_low_risk_scene_question(self, question: str) -> bool:
        """Return True when the user is asking about a neutral everyday scene."""
        question_lower = (question or "").lower().strip()
        return any(term in question_lower for term in NEUTRAL_SCENE_TERMS)

    async def _handle_question(
        self,
        event: MessageEvent,
        question: str,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
        span,
    ) -> bool:
        """Handle question - analyze image and respond."""

        # Get stored image and question
        (
            image_data,
            _,
            analysis_mode,
        ) = await image_analyzer_session_manager.get_image_and_question(chat_id, question)

        if not image_data:
            await self._send_error_message(
                event,
                line_bot_api,
                "Session expired or image not found. Please start again.",
            )
            return False

        span.set_attribute("question.length", len(question))

        # Send "analyzing" message
        await self._send_analyzing_message(event, line_bot_api)

        low_risk_scene = self._is_low_risk_scene_question(question)
        scene_mode = "literal" if low_risk_scene or analysis_mode == "debrief" else "standard"

        # Build vision message
        if analysis_mode == "debrief":
            # Use DebriefExtractionService for structured extraction
            try:
                start_time = datetime.now(UTC)
                debrief = await _debrief_extraction_service.extract_from_image(
                    image_url_or_base64=image_data,
                    chat_id=chat_id,
                    date_str=datetime.now().strftime("%Y-%m-%d"),
                )
                duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)
            except Exception as e:
                logger.error(f"❌ Debrief extraction failed: {e}")
                await self._send_error_message(event, line_bot_api, "Failed to analyze the image for debrief.")
                await image_analyzer_session_manager.clear_session(chat_id)
                return False

            # Format using the new daily debrief formatter
            formatted_msg = DebriefFormatter.format_daily_debrief(debrief)

            # Save image metadata to HF (if enabled)
            if hasattr(image_analyzer_session_manager, "save_image_metadata"):
                try:
                    # Calculate approximate image size from base64 string
                    image_size_bytes = 0
                    if image_data and image_data.startswith("data:image"):
                        base64_part = image_data.split(",", 1)[1] if "," in image_data else ""
                        image_size_bytes = len(base64_part) * 3 // 4

                    await image_analyzer_session_manager.save_image_metadata(
                        chat_id=chat_id,
                        image_base64=image_data,
                        prompt=question,
                        response=formatted_msg,
                        analysis_mode=analysis_mode,
                        duration_ms=duration_ms,
                        image_size_bytes=image_size_bytes,
                        model_used="auto",
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to save image metadata: {e}")

            # Send via push (reply token already used for "analyzing" message)
            group_id = getattr(event.source, "group_id", None) if event.source else None
            room_id = getattr(event.source, "room_id", None) if event.source else None
            target = group_id or room_id or user_id

            if target:
                text_msg = TextMessage(text=formatted_msg, quickReply=None, quoteToken=None)
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[text_msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                )

            logger.info(f"✅ Debrief sent for chat {chat_id}")
            await image_analyzer_session_manager.clear_session(chat_id)
            return True
        elif analysis_mode == "scrape":
            # Scrape mode: Extract text/OCR from image
            scrape_prompt = (
                "Extract ALL text from this image. Return ONLY the text content found in the image. "
                "Include any text from signs, documents, screens, menus, labels, handwriting, etc. "
                "Preserve line breaks and layout as much as possible. "
                "If multiple languages are present, include all. "
                "Do not add explanations or analysis - just the extracted text."
            )
            scrape_messages = self._build_vision_message(image_data, scrape_prompt, scene_mode="literal")

            start_time = datetime.now(UTC)
            scraped_text = await chat_completion_with_vision_fallback(
                messages=scrape_messages,
                temperature=0.1,
                max_tokens=2000,
            )
            duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

            # Save image metadata to HF (if enabled)
            if hasattr(image_analyzer_session_manager, "save_image_metadata"):
                try:
                    image_size_bytes = 0
                    if image_data and image_data.startswith("data:image"):
                        base64_part = image_data.split(",", 1)[1] if "," in image_data else ""
                        image_size_bytes = len(base64_part) * 3 // 4

                    await image_analyzer_session_manager.save_image_metadata(
                        chat_id=chat_id,
                        image_base64=image_data,
                        prompt=scrape_prompt,
                        response=scraped_text or "No text found",
                        analysis_mode=analysis_mode,
                        duration_ms=duration_ms,
                        image_size_bytes=image_size_bytes,
                        model_used="auto",
                    )
                except Exception as e:
                    logger.warning(f"⚠️ Failed to save image metadata: {e}")

            # Format and send scraped text
            if not scraped_text:
                response = "⚡ No text found in the image."
            else:
                response = f"⚡ EXTRACTED TEXT ⚡\n━━━━━━━━━━━━━━━━━\n\n{scraped_text}"

            response = self._format_response(response)

            # Send via push (reply token already used for "analyzing" message)
            group_id = getattr(event.source, "group_id", None) if event.source else None
            room_id = getattr(event.source, "room_id", None) if event.source else None
            target = group_id or room_id or user_id

            if target:
                text_msg = TextMessage(text=response, quickReply=None, quoteToken=None)
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[text_msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                )

            logger.info(f"✅ Text extraction sent for chat {chat_id}")
            await image_analyzer_session_manager.clear_session(chat_id)
            return True
        else:
            messages = self._build_vision_message(image_data, question, scene_mode=scene_mode)

        # Call vision via provider-agnostic fallback (uses priority chain, no hardcoded model)
        logger.info(f"🖼️ Analyzing image with question: {question[:50]}...")

        start_time = datetime.now(UTC)
        analysis = await chat_completion_with_vision_fallback(
            messages=messages,
            temperature=0.15 if low_risk_scene else settings.llm_temperature,
            max_tokens=2000,
        )
        duration_ms = int((datetime.now(UTC) - start_time).total_seconds() * 1000)

        if not analysis:
            status_code, error_detail, model_used = self._get_vision_error_detail() or (
                None,
                None,
                None,
            )
            logger.error(f"❌ Vision API fallback failed: {status_code} - {error_detail}")
            policy_error_terms = (
                "policy",
                "moderation",
                "unsafe",
                "unsafe content",
                "content violation",
                "violation",
            )
            if error_detail and any(term in error_detail.lower() for term in policy_error_terms) and not low_risk_scene:
                logger.info("🖼️ Retrying image analysis with a more literal prompt after policy-like failure")
                messages = self._build_vision_message(image_data, question, scene_mode="literal")
                analysis = await chat_completion_with_vision_fallback(
                    messages=messages,
                    temperature=0.1,
                    max_tokens=2000,
                )

        # CRITICAL: Clear image data from memory after vision API call
        # This prevents sensitive image data from lingering in memory/logs
        # Save image_data for metadata persistence before clearing
        saved_image_data = image_data
        del image_data  # Clear base64 data URL
        del messages  # Clear vision API messages containing image

        if not analysis:
            status_code, error_detail, model_used = self._get_vision_error_detail() or (
                None,
                None,
                None,
            )
            await self._send_error_message(
                event,
                line_bot_api,
                f"Analysis failed: {error_detail or 'Unknown error'}",
            )
            await image_analyzer_session_manager.clear_session(chat_id)
            return False

        span.set_attribute("analyzer.success", True)
        span.set_attribute("analysis.length", len(analysis))

        # Save image metadata to HF (if enabled)
        if hasattr(image_analyzer_session_manager, "save_image_metadata"):
            try:
                # Calculate approximate image size from base64 string
                image_size_bytes = 0
                if saved_image_data and saved_image_data.startswith("data:image"):
                    # Extract base64 part and calculate original byte size
                    base64_part = saved_image_data.split(",", 1)[1] if "," in saved_image_data else ""
                    image_size_bytes = len(base64_part) * 3 // 4

                await image_analyzer_session_manager.save_image_metadata(
                    chat_id=chat_id,
                    image_base64=saved_image_data,
                    prompt=question,
                    response=analysis,
                    analysis_mode=analysis_mode,
                    duration_ms=duration_ms,
                    image_size_bytes=image_size_bytes,
                    model_used="auto",
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to save image metadata: {e}")

        # Extract detected dates before formatting (which strips them)
        detected_dates = self._extract_dates_from_analysis(analysis)
        if detected_dates:
            logger.info(f"📅 Detected {len(detected_dates)} dates in image analysis")
            span.set_attribute("dates.detected", len(detected_dates))

        # Format and send response (strips date section)
        response = self._format_response(analysis)

        # Send via push (reply token already used for "analyzing" message)
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            text_msg = TextMessage(text=response, quickReply=None, quoteToken=None)
            await asyncio.to_thread(
                line_bot_api.push_message,
                PushMessageRequest(
                    to=target,
                    messages=[text_msg],
                    notificationDisabled=False,
                    customAggregationUnits=None,  # Explicitly None to avoid SDK serialization issues
                ),
            )

        logger.info(f"✅ Image analysis sent for chat {chat_id}")

        # Offer calendar integration if dates were detected
        if detected_dates:
            await self._offer_calendar_integration(event, line_bot_api, detected_dates, user_id, chat_id)

        # Explicitly clear session to prevent memory leaks
        await image_analyzer_session_manager.clear_session(chat_id)
        return True

    def _build_vision_message(self, image_data_url: str, question: str, scene_mode: str = "standard") -> list:
        """Build the vision API message structure."""

        # Get today's date in Bangkok timezone for accurate year inference
        bangkok_tz = ZoneInfo("Asia/Bangkok")
        today = datetime.now(bangkok_tz)
        today_str = today.strftime("%B %d, %Y")  # e.g., "January 8, 2026"
        current_year = today.year
        question_lower = (question or "").lower().strip()

        extra_conservative_instruction = ""
        if scene_mode == "literal" or any(term in question_lower for term in NEUTRAL_SCENE_TERMS):
            extra_conservative_instruction = (
                "This looks like a normal everyday scene. "
                "Stay extremely literal and calm; do not sexualize, sensationalize, or assume hidden intent. "
                "If the image is simply caregiving, feeding, family, medical, or household context, describe it plainly. "
            )

        system_prompt = (
            "You are Ms. Green, a polite and observant assistant. "
            "You speak with calm clarity and practical warmth. "
            "When analyzing images, be maximally literal, neutral, and conservative. "
            "Prefer plain description over speculation; if something is ambiguous, say so. "
            "Treat ordinary family, caregiving, infant-feeding, medical, pet, food, document, and household scenes as normal unless the user asks otherwise. "
            "Do not overreact to benign content; keep a steady, careful tone. "
            f"{extra_conservative_instruction}"
            "For menus, signs, or text: translate and explain if in another language. "
            "For products or items: describe what you see and provide recommendations if asked.\n\n"
            f"TODAY'S DATE: {today_str} (Year: {current_year})\n\n"
            "IMPORTANT: If you detect any dates, deadlines, events, or schedules in the image, "
            "always include a section at the end of your response with the following format:\n"
            "---DATES_DETECTED---\n"
            '[{"date": "2026-01-15", "title": "Event title", "description": "Brief description"}]\n'
            "---END_DATES---\n"
            f"Use ISO format (YYYY-MM-DD) for dates. ALWAYS use the actual year number (e.g., {current_year}), never 'YYYY' as a placeholder. "
            f"If the year is not specified in the image, use {current_year} for dates that haven't passed yet, or {current_year + 1} for dates earlier in the year that have already passed. "
            "Only include this section if you actually find date-related information in the image."
        )

        return [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Examine this image and answer my question:\n\n{question}",
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]

    def _get_vision_error_detail(self) -> tuple[int | None, str | None, str | None]:
        """Collect the most recent vision API error detail."""
        for svc in (hermes_service, openrouter_service):
            try:
                detail = svc.get_last_error()
            except AttributeError:
                continue
            if detail and detail[1]:
                return detail
        return (None, None, None)

    def _format_response(self, analysis: str) -> str:
        """Format the analysis response for LINE (strip date detection section)."""
        header = "⚡ MS. GREEN OBSERVES ⚡\n"
        header += "━" * 20 + "\n\n"

        # Strip date detection section from user-visible response
        clean_analysis = self._strip_dates_section(analysis)

        # Truncate if too long (LINE limit is 5000 chars)
        max_content = 4800 - len(header)
        if len(clean_analysis) > max_content:
            clean_analysis = clean_analysis[:max_content] + "\n\n[Response truncated]"

        return header + clean_analysis

    def _strip_dates_section(self, analysis: str) -> str:
        """Remove the dates detection section from analysis text."""
        # Remove the dates section that's meant for internal processing
        pattern = r"---DATES_DETECTED---.*?---END_DATES---"
        return re.sub(pattern, "", analysis, flags=re.DOTALL).strip()

    def _extract_dates_from_analysis(self, analysis: str) -> list[dict[str, str]]:
        """
        Extract detected dates from the analysis response.

        Returns:
            List of dicts with 'date', 'title', 'description' keys
        """
        try:
            # Look for the dates section
            match = re.search(r"---DATES_DETECTED---\s*(.+?)\s*---END_DATES---", analysis, re.DOTALL)
            if not match:
                return []

            dates_json = match.group(1).strip()

            # Parse JSON
            dates = json.loads(dates_json)

            if isinstance(dates, list):
                # Validate each date entry
                valid_dates = []
                for entry in dates:
                    if isinstance(entry, dict) and "date" in entry and "title" in entry:
                        valid_dates.append(
                            {
                                "date": str(entry.get("date", "")),
                                "title": str(entry.get("title", "Untitled Event")),
                                "description": str(entry.get("description", "")),
                            }
                        )
                return valid_dates

            return []

        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"⚠️ Failed to parse dates from analysis: {e}")
            return []

    async def _offer_calendar_integration(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        detected_dates: list[dict[str, str]],
        user_id: str | None,
        chat_id: str,
    ) -> bool:
        """
        Offer to add detected dates to the calendar.

        Returns:
            True if offer was sent successfully
        """
        if not detected_dates:
            return False

        # Check if calendar is enabled
        if not settings.is_calendar_configured():
            logger.debug("Calendar not configured, skipping date integration offer")
            return False

        # Format the dates for display
        dates_summary = []
        for i, d in enumerate(detected_dates[:5], 1):  # Limit to 5 dates
            dates_summary.append(f"{i}. {d['date']}: {d['title']}")

        dates_text = "\n".join(dates_summary)

        # Store dates in session for later retrieval
        await image_analyzer_session_manager.store_detected_dates(chat_id, detected_dates)

        # Create message with quick reply
        msg_text = (
            f"📅 I detected {len(detected_dates)} date(s) in this image:\n\n"
            f"{dates_text}\n\n"
            f"Would you like to add these to your calendar with reminders?\n\n"
            f"ฉันพบวันที่ {len(detected_dates)} รายการในภาพนี้\n"
            f"ต้องการเพิ่มลงในปฏิทินพร้อมการแจ้งเตือนไหม?"
        )

        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    action=MessageAction(label="📅 Yes / ใช่", text="yes add to calendar"),
                ),
                QuickReplyItem(
                    type="action",
                    action=MessageAction(label="❌ No / ไม่", text="no skip calendar"),
                ),
            ]
        )

        msg = TextMessage(text=msg_text, quickReply=quick_reply, quoteToken=None)

        # Get target for push message
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,  # Explicitly None to avoid SDK serialization issues
                    ),
                )
                logger.info(f"📅 Offered calendar integration for {len(detected_dates)} dates in chat {chat_id}")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to offer calendar integration: {e}")
                return False

        return False

    async def _handle_calendar_confirmation(
        self,
        event: MessageEvent,
        text: str,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
    ) -> bool:
        """
        Handle user's response to calendar integration offer.

        Args:
            event: LINE message event
            text: User's response text
            chat_id: Chat ID
            user_id: User ID
            line_bot_api: LINE API client

        Returns:
            True if handled successfully
        """
        text_lower = text.lower().strip()

        # Check for "yes" response
        if "yes" in text_lower or "add to calendar" in text_lower:
            # Check if user is a friend (calendar features require friendship)
            # Skip friend check for admins
            is_admin = privilege_service.is_admin(user_id)
            is_friend = is_admin or await self._is_friend(event, line_bot_api)

            if not is_friend:
                # Get user's display name for personalized quirky response
                display_name = await self._get_user_display_name(user_id or "", line_bot_api) if user_id else "mortal"

                identity_name = self._identity_name()
                quirky_responses = [
                    f"⚡ Alas, {display_name}... are we friends?\n\n"
                    f"Calendar powers are reserved for those who have befriended {identity_name}!\n"
                    f"Add me as a LINE friend to unlock this divine feature.\n\n"
                    f"📱 เพิ่มเพื่อนกับ {identity_name} ก่อนนะ!",
                    f"🤔 Hmm, {display_name}... I sense we are not yet friends.\n\n"
                    f"Only friends of the Olympian king may access the sacred calendar!\n"
                    f"Become my friend to wield this power.\n\n"
                    f"📱 กรุณาเพิ่มเพื่อนก่อนใช้ปฏิทิน!",
                    f"⚡ Hold, {display_name}!\n\n"
                    f"The calendar is a gift I bestow only upon my mortal friends.\n"
                    f"Add {identity_name} as a friend to receive this blessing!\n\n"
                    f"📱 เป็นเพื่อนกับ {identity_name} สิ!",
                ]

                import random

                quirky_msg = random.choice(quirky_responses)

                msg = TextMessage(
                    text=quirky_msg,
                    quickReply=None,
                    quoteToken=None,
                )
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[msg],
                            notificationDisabled=False,
                        ),
                    )
                await image_analyzer_session_manager.clear_session(chat_id)
                logger.info(f"🖼️ Non-friend {user_id} ({display_name}) denied calendar access")
                return True

            # Get detected dates from session
            detected_dates = await image_analyzer_session_manager.get_detected_dates(chat_id)

            if not detected_dates:
                # Session expired or no dates found
                msg = TextMessage(
                    text="⏳ Session expired. Please analyze the image again.\n\nเซสชันหมดอายุ กรุณาวิเคราะห์ภาพใหม่อีกครั้ง",
                    quickReply=None,
                    quoteToken=None,
                )
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[msg],
                            notificationDisabled=False,
                        ),
                    )
                await image_analyzer_session_manager.clear_session(chat_id)
                return True

            # Import and call calendar agent to start extraction flow
            try:
                from datetime import datetime

                from src.agents.calendar_agent import CalendarAgent

                # Find calendar agent from the router or create one
                # For now, we'll create a new instance since it's stateless
                calendar_agent = CalendarAgent()

                # Convert detected date strings into CalendarAgent-compatible extracted_dates
                extracted_dates = []
                for d in detected_dates:
                    raw_date = (d.get("date") or "").strip()
                    title = str(d.get("title") or "Event")
                    description = str(d.get("description") or "")

                    try:
                        parsed_date = datetime.strptime(raw_date, "%Y-%m-%d").date()
                    except ValueError:
                        continue

                    extracted_dates.append(
                        {
                            "date": parsed_date,
                            "title": title,
                            "description": description,
                        }
                    )

                if not extracted_dates:
                    msg = TextMessage(
                        text=(
                            "❌ I couldn't parse any dates to add to calendar.\n\n"
                            f"Please try again or use '{self._identity_name()} add [date] [title]'."
                        ),
                        quickReply=None,
                        quoteToken=None,
                    )
                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[msg],
                                notificationDisabled=False,
                            ),
                        )
                    await image_analyzer_session_manager.clear_session(chat_id)
                    return True

                # Start the extraction flow with detected dates
                if not user_id:
                    logger.error("Cannot start extraction flow: user_id is None")
                    await image_analyzer_session_manager.clear_session(chat_id)
                    return True
                await calendar_agent.start_extraction_flow_from_image(
                    chat_id=chat_id,
                    user_id=user_id,
                    extracted_dates=extracted_dates,
                    is_friend=bool(is_friend),
                    event=event,
                    line_bot_api=line_bot_api,
                )

                # Clear session AFTER calendar flow starts successfully
                await image_analyzer_session_manager.clear_session(chat_id)

                logger.info(f"📅 Started calendar extraction flow for {len(extracted_dates)} dates in chat {chat_id}")
                return True

            except Exception as e:
                logger.error(f"❌ Failed to start calendar extraction flow: {e}", exc_info=True)
                identity_name = self._identity_name()
                msg = TextMessage(
                    text=f"❌ Failed to start calendar flow. Please try '{identity_name} add event' manually.\n\n"
                    f"เกิดข้อผิดพลาด กรุณาลอง '{identity_name} add event' ด้วยตนเอง",
                    quickReply=None,
                    quoteToken=None,
                )
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[msg],
                            notificationDisabled=False,
                        ),
                    )
                await image_analyzer_session_manager.clear_session(chat_id)
                return True

        # Check for "no" response
        elif "no" in text_lower or "skip" in text_lower:
            # Clear session and acknowledge
            await image_analyzer_session_manager.clear_session(chat_id)

            msg = TextMessage(
                text="👍 Understood. Calendar skipped.\n\nเข้าใจแล้ว ไม่เพิ่มลงปฏิทิน",
                quickReply=None,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[msg],
                        notificationDisabled=False,
                    ),
                )

            logger.info(f"📅 User skipped calendar integration in chat {chat_id}")
            return True

        else:
            # Unclear response, ask again
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        type="action",
                        action=MessageAction(label="📅 Yes / ใช่", text="yes add to calendar"),
                    ),
                    QuickReplyItem(
                        type="action",
                        action=MessageAction(label="❌ No / ไม่", text="no skip calendar"),
                    ),
                ]
            )

            msg = TextMessage(
                text="❓ Would you like to add the detected dates to your calendar?\n\nต้องการเพิ่มวันที่ที่ตรวจพบลงในปฏิทินไหม?",
                quickReply=quick_reply,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[msg],
                        notificationDisabled=False,
                    ),
                )
            return True

    async def _download_image(self, message_id: str) -> bytes | None:
        """Download image content from LINE servers with size limit and retry logic."""
        last_exception = None

        for attempt in range(LINE_API_MAX_RETRIES):
            try:
                configuration = Configuration(access_token=settings.line_channel_access_token)

                with ApiClient(configuration) as api_client:
                    blob_api = MessagingApiBlob(api_client)

                    response = await asyncio.to_thread(blob_api.get_message_content, message_id)

                    # Handle None response explicitly
                    if response is None:
                        logger.warning("❌ Response is None from LINE API")
                        return None

                    if isinstance(response, bytes):
                        image_bytes = response
                    elif isinstance(response, bytearray):
                        image_bytes = bytes(response)
                    elif hasattr(response, "read") and callable(getattr(response, "read", None)):
                        image_bytes = response.read()
                    else:
                        # Try to iterate as generator/stream
                        chunks = []
                        try:
                            for chunk in response:  # type: ignore[union-attr]
                                chunks.append(chunk)
                            image_bytes = b"".join(chunks)
                        except TypeError:
                            logger.error(f"❌ Unexpected response type: {type(response)}")
                            return None

                # Validate image size to prevent DoS via memory exhaustion
                if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
                    logger.warning(f"🖼️ Image too large: {len(image_bytes)} bytes (max {MAX_IMAGE_SIZE_BYTES})")
                    return None

                return image_bytes

            except Exception as e:
                last_exception = e
                if attempt < LINE_API_MAX_RETRIES - 1:
                    delay = LINE_API_BASE_DELAY * (2**attempt)
                    logger.warning(
                        f"🖼️ Failed to download image {message_id} (attempt {attempt + 1}/{LINE_API_MAX_RETRIES}): {e}. Retrying in {delay}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"❌ Failed to download image {message_id} after {LINE_API_MAX_RETRIES} attempts: {last_exception}",
                        exc_info=True,
                    )
                    return None

        return None

    async def _send_analyzing_message(self, event: MessageEvent, line_bot_api: MessagingApi):
        """Send a message indicating analysis is in progress using push_message to avoid reply_token expiry."""
        msg = TextMessage(
            text="🔍 Examining thy image... One moment.\n\nกำลังวิเคราะห์ภาพ... กรุณารอสักครู่",
            quickReply=None,
            quoteToken=None,
        )

        user_id = getattr(event.source, "user_id", None) if event.source else None
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to send analyzing message: {e}")

    async def _send_rate_limit_message(self, event: MessageEvent, line_bot_api: MessagingApi, reset_seconds: int):
        """Send rate limit notification."""
        reset_minutes = (reset_seconds + 59) // 60

        msg = TextMessage(
            text=f"⏳ Image Analysis Rate Limit\n\n"
            f"Maximum 5 analyses per hour.\n"
            f"Please wait ~{reset_minutes} minute{'s' if reset_minutes != 1 else ''}.\n\n"
            f"กรุณารออีก ~{reset_minutes} นาที 😊",
            quickReply=None,
            quoteToken=None,
        )

        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[msg],
                    notificationDisabled=False,
                ),
            )

    async def _send_error_message(self, event: MessageEvent, line_bot_api: MessagingApi, error_detail: str):
        """Send softer fallback message to user without exposing internal error details."""
        # Log the actual error detail internally for debugging
        logger.error(f"Image analysis error: {error_detail}")
        # Send user-friendly message without internal error details
        msg = TextMessage(
            text=(
                "⚡ I hit a snag while analyzing that image.\n\n"
                "What I can safely say is: this looks like a normal scene, and I can try again with a more literal description.\n\n"
                "If you want, ask me to:\n"
                "• describe the image plainly\n"
                "• read any text in it\n"
                "• summarize what objects are visible"
            ),
            quickReply=None,
            quoteToken=None,
        )

        user_id = getattr(event.source, "user_id", None) if event.source else None
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,  # Explicitly None to avoid SDK serialization issues
                    ),
                )
            except Exception as e:
                logger.error(f"❌ Failed to send error message: {e}")
