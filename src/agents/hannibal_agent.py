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
import re
import statistics
from collections import Counter
from datetime import UTC, datetime
from typing import Any

from linebot.v3.messaging import (
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.bot_identity_service import get_bot_identity_service
from src.services.conversation_memory_service import get_conversation_memory
from src.services.message_buffer_service import message_buffer_service
from src.services.metrics_service import metrics_service
from src.services.privilege_service import privilege_service
from src.services.rate_limiter import RateLimiter
from src.utils.llm_fallback import chat_completion_with_fallback
from src.utils.text_split import LINE_PART_CHARS, split_text
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

# Hard caps so a huge chat cannot blow the LLM context window.
MAX_ANALYSIS_MESSAGES = 300
MAX_PROMPT_CHARS = 48000

# Trigger vocabulary. The strict variants are the only ones honoured in a
# group chat (where a profile of every member must never be broadcast).
STRICT_TRIGGERS = ("hannibal",)
LOOSE_TRIGGERS = (
    "hannibal profile",
    "profile messages",
    "analyze messages",
    "analyze chat",
    "read chat",
    "profile chat",
    "analyze writing",
    "writing analysis",
)


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

        In a group or room only the strict triggers are honoured, so a casual
        "read chat" never hijacks group conversation. A strict trigger in a
        group is answered with a "do this in DM" notice instead of a profile
        of every member.
        """
        if not text:
            return False

        # Check if any LLM provider is configured
        # Just check if any provider is available - the fallback handles it
        available = any(
            [
                settings.is_openrouter_configured(),
                settings.is_hermes_configured(),
                settings.is_gemini_configured(),
                settings.is_nous_configured(),
            ]
        )
        if not available:
            return False

        text_lower = text.lower().strip()
        prefix, rest = get_bot_identity_service().split_command_prefix(text)
        rest_lower = rest.lower().strip() if prefix else ""

        if prefix and rest_lower == "hannibal":
            return True

        if self._is_group_chat(event):
            # Only an explicit profiling request is worth a group reply.
            return any(trigger in text_lower for trigger in STRICT_TRIGGERS)

        return any(trigger in text_lower for trigger in LOOSE_TRIGGERS)

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """
        Process Hannibal profile request.

        1. Collect every chat message available for this chat
           (live buffer + persisted conversation memory)
        2. Compute deterministic linguistic/temporal statistics
        3. Build the analysis prompt from real data
        4. Send to the LLM fallback chain for the narrative report
        5. Deliver the **complete** report (split across LINE-safe parts)

        Args:
            event: LINE message event
            text: Message text (trigger)
            line_bot_api: LINE Messaging API client

        Returns:
            True if handled successfully
        """
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        is_group = self._is_group_chat(event)

        with tracer.start_as_current_span("hannibal_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)
            span.set_attribute("user.id", user_id or "unknown")
            span.set_attribute("hannibal.group", is_group)

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

                # Determine target user for analysis.
                # In a group we only ever profile the requester: a group-wide
                # profile would broadcast every member's analysis to everyone.
                if is_group:
                    target_user_id = user_id
                else:
                    target_user_id = self._extract_target_user(text, user_id)

                # Collect every message available for this chat
                messages = await self._collect_messages(chat_id, target_user_id)

                # Check minimum message requirement
                if len(messages) < MIN_MESSAGES_FOR_PROFILE:
                    await self._send_insufficient_messages(event, line_bot_api, len(messages))
                    return True

                span.set_attribute("messages.count", len(messages))
                span.set_attribute("hannibal.target", target_user_id or "all")

                # Send "analyzing" indicator
                await self._send_analyzing_message(event, line_bot_api, len(messages))

                # Build analysis prompt (statistics + verbatim messages)
                analysis_prompt = self._build_analysis_prompt(messages, target_user_id)

                # Get analysis from LLM fallback chain (Gemini first)
                logger.info(f"🎭 Sending {len(messages)} messages to LLM for Hannibal analysis...")

                analysis = await chat_completion_with_fallback(
                    messages=[
                        {"role": "system", "content": self._get_system_prompt()},
                        {"role": "user", "content": analysis_prompt},
                    ],
                    temperature=0.4,  # Balanced for analysis
                    # A full five-section report needs more than 4000 tokens,
                    # otherwise the report is cut off mid-section.
                    max_tokens=8000,
                )

                if not analysis:
                    await self._send_error_message(event, line_bot_api)
                    return False

                span.set_attribute("hannibal.success", True)

                # Format and send profile
                profile_text = self._format_profile(analysis, len(messages), target_user_id)

                # Split if too long for LINE (5000 char limit) — every part is sent
                parts = self._split_message(profile_text)
                await self._send_multipart_response(event, line_bot_api, parts, user_id)

                logger.info(
                    f"🎭 Hannibal profile completed for chat {chat_id} " f"({len(messages)} messages, {len(parts)} part(s))"
                )
                return True

            except Exception as e:
                logger.error(f"❌ Hannibal agent error: {e}", exc_info=True)
                span.set_attribute("hannibal.error", True)
                await self._send_error_message(event, line_bot_api)
                return False

    # ------------------------------------------------------------------
    # Data collection
    # ------------------------------------------------------------------
    @staticmethod
    def _normalize_timestamp(value: Any) -> datetime | None:
        """
        Normalize a timestamp to a timezone-aware datetime.

        The live buffer stores ``datetime`` objects while the persisted
        conversation memory stores ISO-8601 strings, so both sources are
        normalised before they are compared or sorted.
        """
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        if isinstance(value, str):
            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                return None
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        return None

    async def _collect_messages(self, chat_id: str, target_user_id: str | None) -> list[Any]:
        """
        Collect every message available for a chat.

        Two sources are merged:
        - the live in-memory buffer (recent, per chat)
        - the persisted conversation memory (older history, survives restarts)

        Messages are de-duplicated on (user_id, text) because both sources see
        the same events.

        Args:
            chat_id: Normalized chat id
            target_user_id: When set, only that user's messages are returned

        Returns:
            List of message records: {"user_id", "text", "timestamp"}
        """
        collected: list[dict[str, Any]] = []

        # De-duplication happens *between* the two sources only. Repeated
        # messages inside one source ("ok", "ok") are legitimate data and
        # must be preserved for the linguistic statistics.
        buffer_pairs: set[tuple[str, str]] = set()
        buffer_texts: set[str] = set()

        def remember(user: str, text: str) -> None:
            buffer_pairs.add((user, text))
            buffer_texts.add(text)

        # 1) Live buffer
        try:
            buffered = message_buffer_service.get_recent_messages(chat_id, limit=MAX_ANALYSIS_MESSAGES)
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"⚠️ Could not read message buffer: {e}")
            buffered = []

        for msg in buffered:
            text = msg.text or ""
            if not text.strip():
                continue
            user = msg.user_id or "unknown"
            remember(user, text.strip())
            collected.append(
                {
                    "user_id": user,
                    "text": text,
                    "timestamp": self._normalize_timestamp(getattr(msg, "timestamp", None)),
                }
            )

        # 2) Persisted conversation memory
        memory_pairs: set[tuple[str, str]] = set()
        memory_texts: set[str] = set()
        try:
            memory = get_conversation_memory()
            if memory is not None:
                entries = await memory.get_recent_entries(chat_id, limit=MAX_ANALYSIS_MESSAGES)
                for entry in entries:
                    if entry.get("role") != "user":
                        continue
                    text = (entry.get("content") or "").strip()
                    if not text:
                        continue
                    user = entry.get("user_id") or "unknown"

                    if user != "unknown":
                        if (user, text) in buffer_pairs or (user, text) in memory_pairs:
                            continue
                        memory_pairs.add((user, text))
                    else:
                        # Sender unknown: match on the text alone.
                        if text in buffer_texts or text in memory_texts:
                            continue
                        memory_texts.add(text)

                    collected.append(
                        {
                            "user_id": user,
                            "text": text,
                            "timestamp": self._normalize_timestamp(entry.get("timestamp")),
                        }
                    )
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(f"⚠️ Could not read conversation memory: {e}")

        # Filter to the target user when profiling a single person
        if target_user_id and target_user_id != "all":
            collected = [m for m in collected if m["user_id"] == target_user_id]

        # Keep the most recent window
        collected = collected[-MAX_ANALYSIS_MESSAGES:]
        collected.sort(key=lambda m: (m["timestamp"] is None, m["timestamp"]))
        return collected

    # ------------------------------------------------------------------
    # Deterministic statistics
    # ------------------------------------------------------------------
    def _compute_stats(self, messages: list[dict[str, Any]]) -> dict[str, Any]:
        """
        Compute deterministic linguistic and temporal statistics.

        These ground the LLM narrative in real numbers instead of letting it
        invent them.
        """
        stats: dict[str, Any] = {}

        total = len(messages)
        stats["total_messages"] = total

        per_user: Counter[str] = Counter()
        lengths: list[int] = []
        questions = 0
        exclamations = 0
        all_caps = 0
        emoji_count = 0
        hours: Counter[int] = Counter()
        days: Counter[str] = Counter()
        timestamps: list[datetime] = []

        for msg in messages:
            text = msg.get("text") or ""
            per_user[msg.get("user_id") or "unknown"] += 1
            lengths.append(len(text))

            if "?" in text:
                questions += 1
            if "!" in text:
                exclamations += 1
            letters = [c for c in text if c.isalpha()]
            if letters and all(c.isupper() for c in letters):
                all_caps += 1
            emoji_count += sum(1 for c in text if ord(c) > 0x1F000)

            stamp = msg.get("timestamp")
            if isinstance(stamp, datetime):
                timestamps.append(stamp)
                hours[stamp.hour] += 1
                days[stamp.strftime("%a")] += 1

        stats["participants"] = len(per_user)
        stats["messages_per_user"] = dict(per_user.most_common(10))
        stats["avg_chars"] = round(statistics.mean(lengths), 1) if lengths else 0
        stats["median_chars"] = round(statistics.median(lengths), 1) if lengths else 0
        stats["max_chars"] = max(lengths) if lengths else 0
        stats["question_ratio_pct"] = round(questions * 100 / total, 1) if total else 0
        stats["exclamation_ratio_pct"] = round(exclamations * 100 / total, 1) if total else 0
        stats["allcaps_ratio_pct"] = round(all_caps * 100 / total, 1) if total else 0
        stats["emoji_total"] = emoji_count

        if hours:
            peak_hour, peak_count = hours.most_common(1)[0]
            stats["peak_hour"] = f"{peak_hour:02d}:00"
            stats["peak_hour_pct"] = round(peak_count * 100 / total, 1)
            stats["active_hours"] = len(hours)
        else:
            stats["peak_hour"] = "unknown"
            stats["peak_hour_pct"] = 0
            stats["active_hours"] = 0

        if days:
            stats["active_days"] = len(days)
            stats["busiest_day"] = days.most_common(1)[0][0]
        else:
            stats["active_days"] = 0
            stats["busiest_day"] = "unknown"

        if len(timestamps) >= 2:
            ordered = sorted(timestamps)
            gaps = [(ordered[i + 1] - ordered[i]).total_seconds() for i in range(len(ordered) - 1)]
            stats["median_gap_minutes"] = round(statistics.median(gaps) / 60, 1)
            stats["longest_gap_hours"] = round(max(gaps) / 3600, 1)
        else:
            stats["median_gap_minutes"] = 0
            stats["longest_gap_hours"] = 0

        return stats

    def _format_stats(self, stats: dict[str, Any]) -> str:
        """Render the statistics block for the prompt."""
        lines = [
            f"- Total messages analyzed: {stats['total_messages']}",
            f"- Distinct participants: {stats['participants']}",
            f"- Messages per participant: {stats['messages_per_user']}",
            f"- Average message length: {stats['avg_chars']} chars (median {stats['median_chars']}, max {stats['max_chars']})",
            f"- Questions: {stats['question_ratio_pct']}% of messages",
            f"- Exclamations: {stats['exclamation_ratio_pct']}% of messages",
            f"- ALL-CAPS messages: {stats['allcaps_ratio_pct']}% of messages",
            f"- Emoji usage: {stats['emoji_total']} total",
            f"- Active hours of day: {stats['active_hours']} (peak {stats['peak_hour']}, {stats['peak_hour_pct']}% of traffic)",
            f"- Days active: {stats['active_days']} (busiest: {stats['busiest_day']})",
            f"- Median gap between messages: {stats['median_gap_minutes']} min (longest {stats['longest_gap_hours']} h)",
        ]
        return "\n".join(lines)

    def _extract_target_user(self, text: str, default_user: str | None) -> str | None:
        """
        Extract target user ID from text if specified.

        Patterns:
        - "hannibal profile all" -> analyze all users
        - "hannibal profile me" -> analyze requesting user
        - Default: analyze all users in group, requesting user in DM

        Word-boundary matching is used so that "remember" does not match
        "me" and "overall" does not match "all".
        """
        text_lower = text.lower()

        if re.search(r"\ball\b", text_lower):
            return "all"
        if re.search(r"\b(me|myself)\b", text_lower):
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

## REQUIRED OUTPUT STRUCTURE

Always produce these sections, in this order, using these exact headings:

### COMMUNICATION STYLE
- Verbosity (use the measured average length)
- Formality and code-switching
- Structure habits
- Question vs. statement ratio (use the measured percentage)
- Vocabulary richness

### EMOTIONAL PROFILE
- Primary emotion and baseline state
- Secondary and blended emotions
- Emotional range and regulation
- Markers of suppression or masking

### COGNITIVE INDICATORS
- Complexity and abstraction
- Reasoning style
- Planning / future orientation
- Metacognition

### SOCIAL DYNAMICS
- Dominance vs. collaboration signals
- Affiliation and empathy markers
- Conflict style
- Group behaviour (if multiple participants)

### TEMPORAL PATTERNS
- Peak activity window (use the measured peak hour)
- Response latency (use the measured median gap)
- Consistency and engagement rhythm

### KEY BEHAVIORAL INDICATORS
- A short list of "+" strengths and "-" vulnerabilities, each tied to observed evidence

### CLINICAL SUMMARY
- One tight paragraph integrating the findings.

Rules:
- Quote or reference specific messages as evidence for every observation.
- Use the measured statistics provided; do not invent numbers.
- Use calibrated language ("suggests", "consistent with"), never "proves".
- Never skip a section. If the data is thin, say so explicitly.
- Write in Dr. Lecter's voice: clinical, precise, faintly unsettling, never cruel.

DISCLAIMER: This is for entertainment/educational purposes only."""

    def _build_analysis_prompt(self, messages: list[Any], target_user_id: str | None) -> str:
        """
        Build the analysis prompt from the available messages.

        The prompt contains (a) deterministic statistics computed locally and
        (b) the verbatim messages, newest last. The prompt is capped so a huge
        chat cannot exceed the model context window — the oldest messages are
        dropped first and the report states how many were analysed.
        """
        stats = self._compute_stats(messages)

        # Format messages for analysis
        formatted_messages: list[str] = []
        for msg in messages:
            user = str(msg.get("user_id") or "unknown")[:8]
            text = (msg.get("text") or "").strip()
            stamp = msg.get("timestamp")
            time_label = ""
            if isinstance(stamp, datetime):
                time_label = f" ({stamp.strftime('%m-%d %H:%M')})"
            formatted_messages.append(f"[{user}]{time_label}: {text}")

        # Keep the prompt within budget: drop oldest messages first.
        included = formatted_messages
        dropped = 0
        while included:
            if len("\n".join(included)) <= MAX_PROMPT_CHARS:
                break
            drop_count = len(included) // 4
            if drop_count == 0:
                # A single message larger than the whole budget: trim it
                # instead of looping forever.
                included = [included[0][:MAX_PROMPT_CHARS]]
                break
            included = included[drop_count:]  # drop the oldest quarter
        dropped = len(formatted_messages) - len(included)

        messages_text = "\n".join(included)

        target_label = (
            "All participants"
            if target_user_id == "all"
            else f"User {str(target_user_id)[:8] if target_user_id else 'Unknown'}"
        )

        context = f"""Analyze the following {len(messages)} messages from a chat conversation.

Target for analysis: {target_label}

## MEASURED STATISTICS (computed from the data — use these exact numbers)

{self._format_stats(stats)}
"""

        if dropped:
            context += (
                f"\nNOTE: {dropped} of the oldest messages were omitted to fit the context "
                f"window; the statistics above cover all {len(messages)} messages.\n"
            )

        context += f"""
---BEGIN MESSAGES---
{messages_text}
---END MESSAGES---

Provide a comprehensive psychological profile based on the communication patterns observed.
Follow the required output structure. Focus on concrete observations from the text, not assumptions."""

        return context

    def _format_profile(self, analysis: str, message_count: int, target_user_id: str | None = None) -> str:
        """Format the profile response."""
        target_label = (
            "all participants"
            if target_user_id == "all"
            else f"participant {str(target_user_id)[:8] if target_user_id else 'unknown'}"
        )

        header = (
            "🎭 **HANNIBAL PROFILE ANALYSIS**\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            f"📊 Messages analyzed: {message_count}\n"
            f"🎯 Target: {target_label}\n"
            f"🕐 Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        )

        footer = (
            "\n\n━━━━━━━━━━━━━━━━━━━━━━\n"
            "⚠️ DISCLAIMER: Entertainment/educational only.\n"
            "Not a clinical psychological assessment."
        )

        return header + analysis + footer

    def _split_message(self, text: str, max_length: int = LINE_PART_CHARS) -> list[str]:
        """
        Split long message into parts.

        Uses the shared LINE-safe splitter so no content is ever lost, and
        labels each part so the reader knows the report continues.
        """
        parts = split_text(text, max_length)
        if not parts:
            return []

        if len(parts) == 1:
            return parts

        total = len(parts)
        return [f"[Part {i + 1}/{total}]\n\n{part}" for i, part in enumerate(parts)]

    async def _send_multipart_response(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        parts: list[str],
        user_id: str | None = None,
    ) -> None:
        """
        Send the complete report.

        The first part uses the reply token (so it appears as a reply). Any
        remaining parts are pushed, because a LINE reply token can only be
        used once. Every part is delivered — the report is never truncated.
        """
        if not parts:
            return

        # Push the remaining parts to the same conversation the reply went to:
        # the group/room in a group chat, the user in a DM.
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id
        if not target:
            logger.warning("🎭 No push target for remaining profile parts")
            return

        sent_reply = False

        if event.reply_token:
            first_msg = TextMessage(text=parts[0], quickReply=None, quoteToken=None)
            try:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[first_msg],
                        notificationDisabled=False,
                    ),
                )
                sent_reply = True
            except Exception as e:
                logger.warning(f"🎭 Reply with first profile part failed: {e}")

        remaining = parts[1:] if sent_reply else parts
        failed: list[int] = []

        for index, part in enumerate(remaining):
            if sent_reply:
                # Let the reply land before pushing the rest so the report
                # is not delivered out of order.
                await asyncio.sleep(0.4)

            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[TextMessage(text=part, quickReply=None, quoteToken=None)],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                )
            except Exception as e:
                # One failed push must not discard the remaining parts:
                # keep going and report the gap to the user at the end.
                logger.error(f"🎭 Failed to push profile part {index + 2}: {e}")
                failed.append(index + 2)
                continue

            if index < len(remaining) - 1:
                await asyncio.sleep(0.35)

        if failed:
            await self._send_partial_report_notice(event, line_bot_api, target, failed, len(parts))

    async def _send_partial_report_notice(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        target: str,
        failed: list[int],
        total: int,
    ) -> None:
        """Tell the user that part of the report could not be delivered."""
        part_list = ", ".join(str(f) for f in failed)
        msg = TextMessage(
            text=(
                f"⚠️ Part(s) {part_list} of {total} could not be delivered.\n"
                "The remaining sections of the profile are above.\n"
                "Please re-run the profile if you need the full report."
            ),
            quickReply=None,
            quoteToken=None,
        )

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
            logger.error(f"🎭 Failed to send partial report notice: {e}")

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
