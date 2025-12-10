"""Tests for translation service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from src.services.translation_service import TranslationService


class TestTranslationService:
    """Test cases for TranslationService."""

    @pytest.fixture
    def service(self):
        """Create a TranslationService instance."""
        return TranslationService()

    @pytest.mark.asyncio
    async def test_detect_language_thai(self, service):
        """Test language detection for Thai text."""
        text = "สวัสดีครับ"

        with patch("src.services.translation_service.detect", return_value="th"):
            lang = await service.detect_language(text)
            assert lang == "th"

    @pytest.mark.asyncio
    async def test_detect_language_english(self, service):
        """Test language detection for English text."""
        text = "Hello, how are you?"

        with patch("src.services.translation_service.detect", return_value="en"):
            lang = await service.detect_language(text)
            assert lang == "en"

    @pytest.mark.asyncio
    async def test_detect_language_failure(self, service):
        """Test language detection failure handling - returns 'en' for ASCII fallback."""
        from langdetect import LangDetectException

        text = "..."

        with patch(
            "src.services.translation_service.detect",
            side_effect=LangDetectException("Error", "Error"),
        ):
            lang = await service.detect_language(text)
            # Updated: ASCII text returns 'en' as fallback, not None
            assert lang == "en"

    @pytest.mark.asyncio
    async def test_translate_success(self, service):
        """Test successful translation."""
        text = "Hello"
        source_lang = "en"
        target_lang = "th"
        expected_translation = "สวัสดี"

        mock_response = MagicMock()
        mock_response.json.return_value = {"translatedText": expected_translation}
        mock_response.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await service.translate(text, source_lang, target_lang)
            assert result == expected_translation

    @pytest.mark.asyncio
    async def test_translate_http_error(self, service):
        """Test translation with HTTP error."""
        text = "Hello"
        source_lang = "en"
        target_lang = "th"

        with patch("httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("HTTP Error")
            )

            result = await service.translate(text, source_lang, target_lang)
            assert result is None

    @pytest.mark.asyncio
    async def test_auto_translate_thai_to_english(self, service):
        """Test auto-translation from Thai to English."""
        text = "สวัสดีครับ"
        expected_translation = "Hello"

        with patch.object(service, "detect_language", return_value="th"), patch.object(
            service, "translate", return_value=expected_translation
        ):
            translated, detected_lang = await service.auto_translate(text)

            assert translated == expected_translation
            assert detected_lang == "th"

    @pytest.mark.asyncio
    async def test_auto_translate_english_to_thai(self, service):
        """Test auto-translation from English to Thai."""
        text = "Hello"
        expected_translation = "สวัสดี"

        with patch.object(service, "detect_language", return_value="en"), patch.object(
            service, "translate", return_value=expected_translation
        ):
            translated, detected_lang = await service.auto_translate(text)

            assert translated == expected_translation
            assert detected_lang == "en"

    @pytest.mark.asyncio
    async def test_auto_translate_detection_failure(self, service):
        """Test auto-translation when language detection fails."""
        text = "..."

        with patch.object(service, "detect_language", return_value=None):
            translated, detected_lang = await service.auto_translate(text)

            assert translated is None
            assert detected_lang is None
