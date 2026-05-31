from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from src.services.github_models_service import github_models_service
from src.services.openrouter_service import openrouter_service


logger = logging.getLogger(__name__)


@dataclass
class AITranslationResult:
    text: str
    provider: str


class AITranslationService:
    def __init__(self, github_models=github_models_service, openrouter=openrouter_service):
        self.github_models = github_models
        self.openrouter = openrouter

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Optional[AITranslationResult]:
        messages = self._build_messages(text, source_lang, target_lang)

        if self.github_models.is_configured():
            result = await self.github_models.chat_completion(
                messages=messages,
                temperature=0.2,
            )
            if result:
                return AITranslationResult(text=result.strip(), provider="github_models")

        if self.openrouter.is_configured():
            result = await self.openrouter.chat_completion(
                messages=messages,
                temperature=0.2,
            )
            if result:
                return AITranslationResult(text=result.strip(), provider="openrouter")

        logger.warning(
            "AI translation unavailable for %s -> %s",
            source_lang,
            target_lang,
        )
        return None

    def _build_messages(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a translation engine. Translate faithfully and only return the translation. "
                    "Preserve line breaks, punctuation, parenthesized text, emojis, and URLs exactly. "
                    "Do not explain."
                ),
            },
            {
                "role": "user",
                "content": f"Translate from {source_lang} to {target_lang}:\n\n{text}",
            },
        ]


ai_translation_service = AITranslationService()