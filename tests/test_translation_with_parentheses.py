"""Tests for AI translation handling of parenthesized text."""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.ai_translation_service import AITranslationService


def test_build_messages_mentions_parenthesized_text_preservation():
    service = AITranslationService(
        openrouter=Mock(),
        hermes=Mock(),
        gemini=Mock(),
        nous=Mock(),
    )

    messages = service._build_messages("(Pim) had the day off", "en", "th")

    assert "parenthesized text" in messages[0]["content"]
    assert "Do not explain" in messages[0]["content"]


@pytest.mark.asyncio
async def test_translate_returns_parenthesized_text_unchanged_when_provider_does():
    mock_gemini = Mock()
    mock_gemini.is_configured.return_value = True
    mock_gemini.chat_completion = AsyncMock(return_value="(Pim) มีวันหยุด")

    mock_openrouter = Mock()
    mock_openrouter.is_configured.return_value = False
    mock_openrouter.chat_completion = AsyncMock()

    mock_hermes = Mock()
    mock_hermes.is_configured.return_value = False
    mock_hermes.chat_completion = AsyncMock()

    mock_nous = Mock()
    mock_nous.is_configured.return_value = False
    mock_nous.chat_completion = AsyncMock()

    with patch("src.services.ai_translation_service.gemini_service", mock_gemini):
        with patch("src.services.ai_translation_service.openrouter_service", mock_openrouter):
            with patch("src.services.ai_translation_service.hermes_service", mock_hermes):
                with patch("src.services.ai_translation_service.nous_inference_service", mock_nous):
                    service = AITranslationService(
                        openrouter=mock_openrouter,
                        hermes=mock_hermes,
                        gemini=mock_gemini,
                        nous=mock_nous,
                    )

                    result = await service.translate(
                        "(Pim) had the day off",
                        source_lang="en",
                        target_lang="th",
                    )

                    assert result is not None
                    assert result.text == "(Pim) มีวันหยุด"
                    assert "gemini" in result.provider.lower()
