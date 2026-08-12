from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.ai_translation_service import AITranslationService


@pytest.mark.asyncio
async def test_translate_uses_gemini_first_when_configured_without_google():
    """Without Google configured, Gemini should be used first via fallback chain."""
    with patch("src.services.ai_translation_service.settings") as mock_settings:
        mock_settings.google_translate_api_key = None

        mock_gemini = Mock()
        mock_gemini.is_configured.return_value = True
        mock_gemini.chat_completion = AsyncMock(return_value="สวัสดี")
        mock_gemini.get_last_error = Mock(return_value=(None, None, None))

        mock_openrouter = Mock()
        mock_openrouter.is_configured.return_value = True
        mock_openrouter.chat_completion = AsyncMock()
        mock_openrouter.get_last_error = Mock(return_value=(None, None, None))

        mock_hermes = Mock()
        mock_hermes.is_configured.return_value = False
        mock_hermes.chat_completion = AsyncMock()
        mock_hermes.get_last_error = Mock(return_value=(None, None, None))

        mock_nous = Mock()
        mock_nous.is_configured.return_value = False
        mock_nous.chat_completion = AsyncMock()
        mock_nous.get_last_error = Mock(return_value=(None, None, None))

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

                        result = await service.translate("Hello", source_lang="en", target_lang="th")

                        assert result is not None
                        assert result.text == "สวัสดี"
                        assert "gemini" in result.provider.lower()
                        mock_openrouter.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_translate_falls_back_to_openrouter_when_gemini_returns_none():
    """Should fall back to OpenRouter when Gemini returns None."""
    with patch("src.services.ai_translation_service.settings") as mock_settings:
        mock_settings.google_translate_api_key = None

        mock_gemini = Mock()
        mock_gemini.is_configured.return_value = True
        mock_gemini.chat_completion = AsyncMock(return_value=None)
        mock_gemini.get_last_error = Mock(return_value=(None, None, None))

        mock_openrouter = Mock()
        mock_openrouter.is_configured.return_value = True
        mock_openrouter.chat_completion = AsyncMock(return_value="Hello")
        mock_openrouter.get_last_error = Mock(return_value=(None, None, None))

        mock_hermes = Mock()
        mock_hermes.is_configured.return_value = False
        mock_hermes.chat_completion = AsyncMock()
        mock_hermes.get_last_error = Mock(return_value=(None, None, None))

        mock_nous = Mock()
        mock_nous.is_configured.return_value = False
        mock_nous.chat_completion = AsyncMock()
        mock_nous.get_last_error = Mock(return_value=(None, None, None))

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

                        result = await service.translate("สวัสดี", source_lang="th", target_lang="en")

                        assert result is not None
                        assert result.text == "Hello"
                        assert "openrouter" in result.provider.lower()
