"""Backwards-compatible translation service shim."""

from __future__ import annotations

from typing import Any

from src.services.ai_translation_service import ai_translation_service


class TranslationService:
    def __init__(self, delegate=ai_translation_service):
        self.delegate = delegate
        self.client: Any = None

    def set_client(self, client: Any) -> None:
        self.client = client

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> Any | None:
        return await self.delegate.translate(text, source_lang, target_lang)


translation_service = TranslationService()
