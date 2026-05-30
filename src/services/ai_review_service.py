from __future__ import annotations

from typing import Any, Optional

from src.services.github_models_service import github_models_service
from src.services.openrouter_service import (
    openrouter_service as default_openrouter_service,
)


class AIReviewService:
    def __init__(
        self,
        github_service: Optional[Any] = None,
        openrouter_service: Optional[Any] = None,
    ):
        self.github_service = github_service or github_models_service
        self.openrouter_service = (
            openrouter_service or default_openrouter_service
        )

    async def _complete(
        self,
        messages,
        github_model: str = "openai/gpt-4o-mini",
        openrouter_model: str = "openai/gpt-4o",
    ) -> str | None:
        if self.github_service and self.github_service.is_configured():
            response = await self.github_service.chat_completion(
                messages=messages,
                model=github_model,
                temperature=0.2,
                max_tokens=900,
            )
            if response:
                return response

        if self.openrouter_service and self.openrouter_service.is_configured():
            return await self.openrouter_service.chat_completion(
                messages=messages,
                model=openrouter_model,
                temperature=0.2,
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

    async def extract_calendar_candidates(
        self, texts: list[str]
    ) -> str | None:
        messages = [
            {
                "role": "system",
                "content": (
                    "Extract date-bearing events for school staff planning. "
                    "Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": "\n".join(texts),
            },
        ]
        return await self._complete(messages)


ai_review_service = AIReviewService()
