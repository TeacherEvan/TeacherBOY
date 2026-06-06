"""Backwards-compatible Google translation service shim."""

from __future__ import annotations

from typing import Any

from src.services.ai_translation_service import ai_translation_service


class GoogleTranslationService:
    def __init__(self, delegate=ai_translation_service):
        self.delegate = delegate
        self.api_key: str | None = None
        self.client: Any = None

    def set_client(self, client: Any) -> None:
        self.client = client

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ):
        return await self.delegate.translate(text, source_lang, target_lang)


google_translation_service = GoogleTranslationService()
