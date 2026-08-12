"""Conversation Summarization Service - Automatic history compression.

This service implements rolling summarization to reduce token usage in
conversation memory while preserving semantic context.

Key features:
- Automatic triggering when token threshold exceeded
- Incremental summarization (updates existing summary)
- Configurable retention of recent messages
- Uses cheap model (gpt-4o-mini) for cost efficiency

Token savings example:
- Before: 20 messages × 200 tokens = 4,000 tokens
- After: 1 summary × 300 tokens + 6 recent × 200 tokens = 1,500 tokens
- Savings: 62.5% reduction
"""

import logging

logger = logging.getLogger(__name__)


class ConversationSummarizer:
    """
    Automatically summarize conversation history to save tokens.

    Uses a rolling summary approach:
    1. Maintain summary of old messages
    2. Keep recent N messages in full
    3. When threshold exceeded, summarize oldest messages
    4. Update running summary incrementally
    """

    def __init__(
        self,
        summarization_model: str = "openai/gpt-4o-mini",
        max_tokens_before_summary: int = 2000,
        messages_to_keep_full: int = 6,
        summary_max_tokens: int = 300,
    ):
        """
        Initialize summarizer.

        Args:
            summarization_model: Cheap model for summaries
            max_tokens_before_summary: Trigger threshold
            messages_to_keep_full: Keep N most recent messages
            summary_max_tokens: Maximum tokens for summary
        """
        self.model = summarization_model
        self.threshold = max_tokens_before_summary
        self.keep_recent = messages_to_keep_full
        self.summary_max_tokens = summary_max_tokens

        logger.info(f"📝 Summarizer initialized: threshold={max_tokens_before_summary}, keep_recent={messages_to_keep_full}")

    async def maybe_summarize(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
    ) -> tuple[str | None, list[dict[str, str]]]:
        """
        Conditionally summarize if messages exceed threshold.

        Args:
            messages: Full conversation history
            current_summary: Existing summary (if any)

        Returns:
            Tuple of (updated_summary, recent_messages_to_keep)
        """
        # Estimate tokens (rough: 4 chars = 1 token)
        estimated_tokens = sum(len(m.get("content", "")) // 4 for m in messages)

        logger.debug(f"📝 Conversation size: {len(messages)} messages, ~{estimated_tokens} tokens")

        # No summarization needed
        if estimated_tokens < self.threshold:
            logger.debug("📝 Below threshold, no summarization needed")
            return current_summary, messages

        # Split messages: old (to summarize) + recent (to keep)
        if len(messages) <= self.keep_recent:
            logger.debug("📝 Too few messages to summarize, keeping all")
            return current_summary, messages

        to_summarize = messages[: -self.keep_recent]
        to_keep = messages[-self.keep_recent :]

        logger.info(f"📝 Summarizing {len(to_summarize)} messages, keeping {len(to_keep)} recent")

        # Generate or update summary
        new_summary = await self._generate_summary(to_summarize, current_summary)

        if new_summary:
            logger.info(f"📝 Generated summary ({len(new_summary)} chars)")
            return new_summary, to_keep
        else:
            logger.warning("📝 Summarization failed, keeping all messages")
            return current_summary, messages

    async def _generate_summary(
        self,
        messages: list[dict[str, str]],
        existing_summary: str | None,
    ) -> str | None:
        """
        Generate or update conversation summary.

        Args:
            messages: Messages to summarize
            existing_summary: Previous summary to update

        Returns:
            New summary text or None if failed
        """
        # Import here to avoid circular dependency
        from src.utils.llm_fallback import chat_completion_with_fallback

        # Build summary prompt
        summary_prompt = self._build_summary_prompt(messages, existing_summary)

        try:
            new_summary = await chat_completion_with_fallback(
                messages=[{"role": "user", "content": summary_prompt}],
                temperature=0.3,  # Low temperature for factual summarization
                max_tokens=self.summary_max_tokens,
            )

            return new_summary

        except Exception as e:
            logger.error(f"📝 Summarization failed: {e}")
            return None

    def _build_summary_prompt(
        self,
        messages: list[dict[str, str]],
        existing_summary: str | None,
    ) -> str:
        """
        Build prompt for summarization task.

        Args:
            messages: Messages to summarize
            existing_summary: Previous summary to update

        Returns:
            Prompt text
        """
        # Format messages for prompt
        formatted_messages = self._format_messages(messages)

        if existing_summary:
            # Incremental summarization
            prompt = f"""You are summarizing a conversation to save memory.

**Previous Summary:**
{existing_summary}

**New Messages to Incorporate:**
{formatted_messages}

Update the summary to include key information from the new messages. Focus on:
- Important facts and data shared
- User preferences or requirements mentioned
- Key decisions or conclusions reached
- Main topics discussed

Provide an updated summary (max 150 words):"""
        else:
            # Initial summarization
            prompt = f"""Summarize the following conversation exchanges concisely.

**Messages:**
{formatted_messages}

Focus on:
- Key questions asked by the user
- Important facts and data provided
- User preferences or requirements mentioned
- Main topics discussed

Provide a concise summary (max 150 words):"""

        return prompt

    def _format_messages(self, messages: list[dict[str, str]]) -> str:
        """
        Format messages for summarization prompt.

        Args:
            messages: Messages to format

        Returns:
            Formatted text
        """
        formatted = []

        for i, msg in enumerate(messages, 1):
            role = msg.get("role", "unknown").upper()
            content = msg.get("content", "")

            # Truncate very long messages
            if len(content) > 300:
                content = content[:297] + "..."

            formatted.append(f"{i}. {role}: {content}")

        return "\n".join(formatted)

    def estimate_savings(
        self,
        messages: list[dict[str, str]],
        current_summary: str | None = None,
    ) -> dict[str, int]:
        """
        Estimate token savings from summarization.

        Args:
            messages: Full conversation history
            current_summary: Existing summary

        Returns:
            Dict with token estimates
        """
        # Estimate current tokens
        current_tokens = sum(len(m.get("content", "")) // 4 for m in messages)

        # Estimate after summarization
        if len(messages) <= self.keep_recent:
            return {
                "current_tokens": current_tokens,
                "optimized_tokens": current_tokens,
                "savings": 0,
                "savings_percent": 0,
            }

        summary_tokens = (len(current_summary) // 4) if current_summary else self.summary_max_tokens
        recent_tokens = sum(len(m.get("content", "")) // 4 for m in messages[-self.keep_recent :])
        optimized_tokens = summary_tokens + recent_tokens

        savings = current_tokens - optimized_tokens
        savings_percent = int((savings / current_tokens) * 100) if current_tokens > 0 else 0

        return {
            "current_tokens": current_tokens,
            "optimized_tokens": optimized_tokens,
            "savings": savings,
            "savings_percent": savings_percent,
        }


# Singleton instance
conversation_summarizer = ConversationSummarizer()
