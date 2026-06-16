from __future__ import annotations

import logging
from typing import Any

from src.services.openrouter_service import (
    openrouter_service as default_openrouter_service,
)
from src.utils.llm_fallback import chat_completion_with_fallback

logger = logging.getLogger(__name__)


class AIReviewService:
    def __init__(
        self,
        openrouter_service: Any | None = None,
    ):
        self.openrouter_service = openrouter_service or default_openrouter_service

    async def _complete(
        self,
        messages,
        openrouter_model: str = "openai/gpt-4o",
    ) -> str | None:
        # Try fallback chain (gemini first per config)
        result = await chat_completion_with_fallback(
            messages=messages,
            temperature=0.2,
            max_tokens=900,
        )
        if result:
            return result

        # Fallback to OpenRouter if configured
        if self.openrouter_service and self.openrouter_service.is_configured():
            try:
                return await self.openrouter_service.chat_completion(
                    messages=messages,
                    model=openrouter_model,
                    temperature=0.2,
                )
            except Exception:
                logger.warning(
                    "AIReviewService OpenRouter fallback failed",
                    exc_info=True,
                )

        return None

    async def translate_and_summarize(self, text: str) -> str | None:
        messages = [
            {
                "role": "system",
                "content": (
                    "Translate the non-English message into English, "
                    "summarize it clearly, and suggest calendar-worthy "
                    "actions. Output concise plain text."
                ),
            },
            {"role": "user", "content": text},
        ]
        return await self._complete(messages)

    async def extract_calendar_candidates(self, texts: list[str]) -> str | None:
        messages = [
            {
                "role": "system",
                "content": ("Extract date-bearing events for school staff planning. Return JSON only."),
            },
            {
                "role": "user",
                "content": "\n".join(texts),
            },
        ]
        return await self._complete(messages)


ai_review_service = AIReviewService()