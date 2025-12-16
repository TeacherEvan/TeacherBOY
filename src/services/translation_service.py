"""Service for detecting language and translating text."""

import httpx
import logging
from typing import Optional, Tuple
from langdetect import detect, LangDetectException

from src.config import settings
from src.utils.text_preprocessing import (
    extract_parenthesized_text,
    restore_parenthesized_text,
)

logger = logging.getLogger(__name__)


class TranslationService:
    """Service to handle language detection and translation using LibreTranslate API."""

    def __init__(self):
        self.api_url = settings.libretranslate_api_url
        self.api_key = settings.libretranslate_api_key
        self.client: Optional[httpx.AsyncClient] = None

    def set_client(self, client: httpx.AsyncClient):
        """Set the shared HTTP client."""
        self.client = client

    async def detect_language(self, text: str) -> Optional[str]:
        """
        Detect the language of the input text.

        Args:
            text: Input text to detect language

        Returns:
            Language code ('th' for Thai, 'en' for English) or None if detection fails
        """
        try:
            # Optimization: Check for simple ASCII to guess English quickly
            if text.isascii():
                return "en"

            lang = detect(text)
            logger.debug(f"Detected language: {lang}")

            # Normalize to Thai or English
            if lang == "th":
                return "th"

            # Default to English for all other languages (including en, en-US, etc.)
            return "en"
        except LangDetectException as e:
            logger.error(f"Language detection error: {str(e)}")
            return None

    async def translate(
        self, text: str, source_lang: str, target_lang: str
    ) -> Optional[str]:
        """
        Translate text from source language to target language.

        Text within parentheses is preserved and not translated.

        Args:
            text: Text to translate
            source_lang: Source language code ('th' or 'en')
            target_lang: Target language code ('th' or 'en')

        Returns:
            Translated text or None if translation fails
        """
        try:
            # Extract parenthesized text before translation
            processed_text, extracted_items = extract_parenthesized_text(text)
            
            # If nothing to translate (only parentheses), return original
            if not processed_text.strip() or processed_text.strip() == "".join(
                [f"__PAREN_{i}__" for i in range(len(extracted_items))]
            ).strip():
                logger.info("Text contains only parenthesized content, skipping translation")
                return text

            payload = {
                "q": processed_text,
                "source": source_lang,
                "target": target_lang,
                "format": "text",
            }

            if self.api_key:
                payload["api_key"] = self.api_key

            if self.client:
                response = await self.client.post(self.api_url, json=payload)
            else:
                # Fallback for tests or if client not initialized
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.api_url, json=payload)

            response.raise_for_status()

            result = response.json()
            translated_text = result.get("translatedText", "")

            # Restore parenthesized text
            translated_text = restore_parenthesized_text(translated_text, extracted_items)

            logger.info(f"Translation successful: {source_lang} -> {target_lang}")
            return translated_text

        except httpx.HTTPError as e:
            logger.error(f"HTTP error during translation: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Translation error: {str(e)}")
            return None

    async def auto_translate(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Auto-detect language and translate Thai to English or English to Thai.

        Args:
            text: Text to translate

        Returns:
            Tuple of (translated_text, detected_language)
        """
        source_lang = await self.detect_language(text)

        if not source_lang:
            logger.warning("Could not detect language")
            return None, None

        # Determine target language
        target_lang = "en" if source_lang == "th" else "th"

        logger.info(f"Auto-translating: {source_lang} -> {target_lang}")

        # Translate
        translated = await self.translate(text, source_lang, target_lang)

        return translated, source_lang


# Singleton instance
translation_service = TranslationService()
