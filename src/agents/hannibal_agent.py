"""
Hannibal Profile Agent - Psychological profiling from message history.

This agent analyzes communication patterns and writing style from chat messages
to create a comprehensive psychological assessment. Named after Dr. Hannibal Lecter's
renowned ability to profile individuals through their speech patterns.

Frameworks used:
- Linguistic Analysis (word choice, vocabulary richness, sentence structure)
- Communication Patterns (message frequency, response patterns, timing)
- Emotional Indicators (sentiment, tone, emotional regulation)
- DISC/MBTI-style Personality Traits (behavioral tendencies)
- Dark Triad Markers (for educational purposes only)

DISCLAIMER: For educational/entertainment purposes only. Not a clinical tool.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any

from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.bot_identity_service import get_bot_identity_service
from src.services.github_models_service import github_models_service
from src.services.message_buffer_service import message_buffer_service
from src.services.metrics_service import metrics_service
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import RateLimiter
from src.utils.tracing import get_tracer

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Rate limiter: 1 Hannibal profile per 6 hours per chat (very expensive)
hannibal_rate_limiter = RateLimiter(
    max_requests=1,
    time_window_seconds=21600,  # 6 hours
)

# Minimum messages required for meaningful analysis
MIN_MESSAGES_FOR_PROFILE = 20
IDEAL_MESSAGES_FOR_PROFILE = 100


class HannibalProfileAgent(BaseAgent):
    """
    Agent for psychological profiling from written communication patterns.

    Uses GPT-4o to analyze message history and provide comprehensive
    behavioral and psychological assessments based on writing style.
    """

    def __init__(self, http_client=None):
        """
        Initialize HannibalProfileAgent.

        Args:
            http_client: Shared HTTP client (not used directly but kept for interface consistency)
        """
        super().__init__(
            name="HannibalProfileAgent",
            description="Psychological profiling from message history analysis",
        )
        self.http_client = http_client

    def get_priority(self) -> int:
        """
        Priority 6: After admin/help (5), before profiler (7).
        Needs to intercept trigger before image-based profiler.
        """
        return 6

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

    def _is_group_chat(self, event: MessageEvent) -> bool:
        """Check if message is from a group or room."""
        if event.source and getattr(event.source, "group_id", None):
            return True
        if event.source and getattr(event.source, "room_id", None):
            return True
        return False

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if text contains Hannibal profile trigger.

        Triggers:
        - "hannibal profile"
        - "zeus hannibal"
        - "profile messages"
        - "analyze messages"
        - "read chat"
        """
        if not text:
            return False

        # Check if GitHub Models is configured (required for LLM)
        if not github_models_service.is_configured():
            return False

        text_lower = text.lower().strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(text)
        rest_lower = rest.lower().strip() if prefix else ""

        # Hannibal profile triggers
        triggers = [
            "hannibal profile",
            "profile messages",
            "analyze chat",
            "read chat",
            "profile chat",
            "analyze writing",
            "writing analysis",
        ]

        if prefix and rest_lower == "hannibal":
            return True

        return any(trigger in text_lower for trigger in triggers)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """
        Process Hannibal profile request.

        1. Get recent messages from buffer
        2. Build psychological analysis prompt
        3. Send to GPT-4o for analysis
        4. Return formatted profile

        Args:
            event: LINE message event
            text: Message text (trigger)
            line_bot_api: LINE Messaging API client

        Returns:
            True if handled successfully
        """
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None

        with tracer.start_as_current_span("hannibal_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)
            span.set_attribute("user.id", user_id or "unknown")

            try:
                # Check rate limiting (skip for admins)
                if not privilege_service.is_admin(user_id):
                    if not hannibal_rate_limiter.is_allowed(chat_id, user_id):
                        span.set_attribute("hannibal.rate_limited", True)
                        metrics_service.record_rate_limited()

                        reset_seconds = hannibal_rate_limiter.get_reset_time(chat_id, user_id)
                        await self._send_rate_limit_message(event, line_bot_api, reset_seconds)
                        return True
                else:
                    logger.info(f"🔓 Admin {user_id} bypassed Hannibal rate limit")

                # Determine target user for analysis
                target_user_id = self._extract_target_user(text, user_id)

                # Get messages from buffer
                messages = message_buffer_service.get_recent_messages(
                    chat_id,
                    limit=200,  # Get as many as available
                )

                # Filter to target user's messages if specified
                if target_user_id and target_user_id != "all":
                    messages = [m for m in messages if m.user_id == target_user_id]

                # Check minimum message requirement
                if len(messages) < MIN_MESSAGES_FOR_PROFILE:
                    await self._send_insufficient_messages(event, line_bot_api, len(messages))
                    return True

                span.set_attribute("messages.count", len(messages))

                # Send "analyzing" indicator
                await self._send_analyzing_message(event, line_bot_api, len(messages))

                # Build analysis prompt
                analysis_prompt = self._build_analysis_prompt(messages, target_user_id)

                # Get analysis from GPT-4o
                logger.info(f"🎭 Sending {len(messages)} messages to GPT-4o for Hannibal analysis...")

                analysis = await github_models_service.chat_completion(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": analysis_prompt},
                    ],
                    model=getattr(settings, "profiler_model", "openai/gpt-4o"),
                    temperature=0.4,  # Balanced for analysis
                    max_tokens=4000,
                )

                if not analysis:
                    await self._send_error_message(event, line_bot_api)
                    return False

                span.set_attribute("hannibal.success", True)

                # Format and send profile
                profile_text = self._format_profile(analysis, len(messages))

                # Split if too long for LINE (5000 char limit)
                if len(profile_text) > 4900:
                    parts = self._split_message(profile_text)
                    await self._send_multipart_response(event, line_bot_api, parts)
                else:
                    response_msg = TextMessage(
                        text=profile_text,
                        quickReply=None,
                        quoteToken=None,
                    )

                    if event.reply_token:
                        await asyncio.to_thread(
                            line_bot_api.reply_message,
                            ReplyMessageRequest(
                                replyToken=event.reply_token,
                                messages=[response_msg],
                                notificationDisabled=False,
                            ),
                        )

                logger.info(f"🎭 Hannibal profile completed for chat {chat_id}")
                return True

            except Exception as e:
                logger.error(f"❌ Hannibal agent error: {e}", exc_info=True)
                span.set_attribute("hannibal.error", True)
                await self._send_error_message(event, line_bot_api)
                return False

    def _extract_target_user(self, text: str, default_user: str | None) -> str | None:
        """
        Extract target user ID from text if specified.

        Patterns:
        - "hannibal profile all" -> analyze all users
        - "hannibal profile me" -> analyze requesting user
        - Default: analyze all users in group, requesting user in DM
        """
        text_lower = text.lower()

        if "all" in text_lower:
            return "all"
        if "me" in text_lower or "myself" in text_lower:
            return default_user

        # Default: analyze all in group
        return "all"

    def _get_system_prompt(self) -> str:
        """Get the system prompt for Hannibal analysis."""
        return """You are Dr. Hannibal Lecter, a brilliant forensic psychiatrist with unparalleled
insight into human psychology. You analyze communication patterns with clinical precision
and artistic flair.

Your analysis framework includes:

1. **LINGUISTIC ANALYSIS**
   - Vocabulary richness and word choice patterns
   - Sentence structure complexity
   - Use of hedging language vs. assertive statements
   - Figurative language and metaphors
   - Formality level and code-switching

2. **COMMUNICATION STYLE**
   - Message length patterns (verbose vs. terse)
   - Question-asking vs. statement-making ratio
   - Topic initiation vs. response patterns
   - Emotional expression frequency
   - Humor and sarcasm usage

3. **PSYCHOLOGICAL INDICATORS**
   - Attachment style markers (secure, anxious, avoidant)
   - Locus of control (internal vs. external)
   - Cognitive complexity indicators
   - Emotional regulation patterns
   - Defense mechanisms in language

4. **PERSONALITY FRAMEWORK**
   - DISC tendencies (Dominance, Influence, Steadiness, Conscientiousness)
   - Big Five markers (Openness, Conscientiousness, Extraversion, Agreeableness, Neuroticism)
   - Dark Triad indicators (if present, note subtly)

5. **BEHAVIORAL PREDICTIONS**
   - Likely response to stress
   - Decision-making style
   - Conflict resolution approach
   - Trust-building patterns

Provide your analysis in a conversational yet insightful manner, as Dr. Lecter would.
Include specific examples from the messages to support your observations.
End with a brief "Clinical Summary" paragraph.

DISCLAIMER: This is for entertainment/educational purposes only."""

    def _build_analysis_prompt(self, messages: list[Any], target_user_id: str | None) -> str:
        """Build the analysis prompt from messages."""
        # Format messages for analysis
        formatted_messages = []
        user_message_counts: dict[str, int] = {}

        for msg in messages:
            user = msg.user_id[:8] if msg.user_id else "Unknown"
            user_message_counts[user] = user_message_counts.get(user, 0) + 1
            formatted_messages.append(f"[{user}]: {msg.text}")

        messages_text = "\n".join(formatted_messages)

        # Build context
        context = f"""Analyze the following {len(messages)} messages from a chat conversation.

Message distribution by user:
{self._format_user_stats(user_message_counts)}

Target for analysis: {"All participants" if target_user_id == "all" else f"User {target_user_id[:8] if target_user_id else 'Unknown'}"}

---BEGIN MESSAGES---
{messages_text}
---END MESSAGES---

Provide a comprehensive psychological profile based on the communication patterns observed.
Focus on concrete observations from the text, not assumptions."""

        return context

    def _format_user_stats(self, counts: dict[str, int]) -> str:
        """Format user message statistics."""
        if not counts:
            return "No messages"

        lines = []
        for user, count in sorted(counts.items(), key=lambda x: -x[1]):
            lines.append(f"- {user}: {count} messages")
        return "\n".join(lines[:5])  # Top 5 users

    def _format_profile(self, analysis: str, message_count: int) -> str:
        """Format the profile response."""
        header = (
            "🎭 **HANNIBAL PROFILE ANALYSIS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Messages analyzed: {message_count}\n"
            f"🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        footer = (
            "\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ DISCLAIMER: Entertainment/educational only.\n"
            "Not a clinical psychological assessment."
        )

        return header + analysis + footer

    def _split_message(self, text: str, max_length: int = 4500) -> list[str]:
        """Split long message into parts."""
        if len(text) <= max_length:
            return [text]

        parts = []
        current = ""

        for paragraph in text.split("\n\n"):
            if len(current) + len(paragraph) + 2 <= max_length:
                current += paragraph + "\n\n"
            else:
                if current:
                    parts.append(current.strip())
                current = paragraph + "\n\n"

        if current:
            parts.append(current.strip())

        # Add part indicators
        total = len(parts)
        return [f"[{i + 1}/{total}]\n\n{part}" for i, part in enumerate(parts)]

    async def _send_multipart_response(self, event: MessageEvent, line_bot_api: MessagingApi, parts: list[str]) -> None:
        """Send multipart response using push messages after initial reply."""
        if not parts:
            return

        # First part uses reply token
        if event.reply_token:
            first_msg = TextMessage(text=parts[0], quickReply=None, quoteToken=None)
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[first_msg],
                    notificationDisabled=False,
                ),
            )

        # Subsequent parts would need push (not implemented to avoid spam)
        if len(parts) > 1:
            logger.warning(f"🎭 Profile truncated: {len(parts)} parts, only first sent")

    async def _send_analyzing_message(self, event: MessageEvent, line_bot_api: MessagingApi, message_count: int) -> None:
        """Send analyzing indicator (uses push since reply token used for actual response)."""
        logger.info(f"🎭 Starting Hannibal analysis of {message_count} messages")
        # Don't consume reply token here - save it for the actual response

    async def _send_insufficient_messages(self, event: MessageEvent, line_bot_api: MessagingApi, actual_count: int) -> None:
        """Send message when not enough messages for analysis."""
        msg = TextMessage(
            text=(
                f"🎭 **Insufficient Data for Hannibal Profile**\n\n"
                f"Found: {actual_count} messages\n"
                f"Required: {MIN_MESSAGES_FOR_PROFILE}+ messages\n"
                f"Ideal: {IDEAL_MESSAGES_FOR_PROFILE}+ messages\n\n"
                f"Keep chatting and try again later!\n"
                f"The message buffer stores recent conversations.\n\n"
                f"💡 Tip: More messages = more accurate profile"
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

    async def _send_rate_limit_message(self, event: MessageEvent, line_bot_api: MessagingApi, reset_seconds: int) -> None:
        """Send rate limit notification."""
        hours = reset_seconds // 3600
        minutes = (reset_seconds % 3600) // 60

        msg = TextMessage(
            text=(
                f"🎭 **Hannibal Profile Rate Limited**\n\n"
                f"This feature is limited to 1 analysis per 6 hours.\n"
                f"⏳ Try again in: {hours}h {minutes}m\n\n"
                f"กรุณารอ {hours} ชั่วโมง {minutes} นาที"
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

    async def _send_error_message(self, event: MessageEvent, line_bot_api: MessagingApi) -> None:
        """Send error message."""
        msg = TextMessage(
            text=(
                "🎭 **Analysis Failed**\n\n"
                "Something went wrong with the Hannibal profile.\n"
                "Please try again later.\n\n"
                "ขออภัย เกิดข้อผิดพลาด"
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
