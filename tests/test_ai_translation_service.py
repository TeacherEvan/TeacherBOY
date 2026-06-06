from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.services.ai_translation_service import AITranslationService


@pytest.mark.asyncio
async def test_translate_uses_github_models_first_when_configured_without_google():
    """Without Google configured, GitHub Models should be used first."""
    with patch("src.services.ai_translation_service.settings") as mock_settings:
        mock_settings.google_translate_api_key = None

        github = Mock()
        github.is_configured.return_value = True
        github.chat_completion = AsyncMock(return_value="สวัสดี")
        github.get_last_error = Mock(return_value=(None, None, None))

        openrouter = Mock()
        openrouter.is_configured.return_value = True
        openrouter.chat_completion = AsyncMock()
        openrouter.get_last_error = Mock(return_value=(None, None, None))

        hermes = Mock()
        hermes.is_configured.return_value = False
        hermes.chat_completion = AsyncMock()
        hermes.get_last_error = Mock(return_value=(None, None, None))

        nous = Mock()
        nous.is_configured.return_value = False
        nous.chat_completion = AsyncMock()
        nous.get_last_error = Mock(return_value=(None, None, None))

        service = AITranslationService(
            github_models=github,
            openrouter=openrouter,
            hermes=hermes,
            nous=nous,
        )

        result = await service.translate("Hello", source_lang="en", target_lang="th")

        assert result is not None
        assert result.text == "สวัสดี"
        assert result.provider == "github_models"
        openrouter.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_translate_falls_back_to_openrouter_when_github_models_returns_none():
    """Should fall back to OpenRouter when GitHub Models returns None."""
    with patch("src.services.ai_translation_service.settings") as mock_settings:
        mock_settings.google_translate_api_key = None

        github = Mock()
        github.is_configured.return_value = True
        github.chat_completion = AsyncMock(return_value=None)
        github.get_last_error = Mock(return_value=(None, None, None))

        openrouter = Mock()
        openrouter.is_configured.return_value = True
        openrouter.chat_completion = AsyncMock(return_value="Hello")
        openrouter.get_last_error = Mock(return_value=(None, None, None))

        hermes = Mock()
        hermes.is_configured.return_value = False
        hermes.chat_completion = AsyncMock()
        hermes.get_last_error = Mock(return_value=(None, None, None))

        nous = Mock()
        nous.is_configured.return_value = False
        nous.chat_completion = AsyncMock()
        nous.get_last_error = Mock(return_value=(None, None, None))

        service = AITranslationService(
            github_models=github,
            openrouter=openrouter,
            hermes=hermes,
            nous=nous,
        )

        result = await service.translate("สวัสดี", source_lang="th", target_lang="en")

        assert result is not None
        assert result.text == "Hello"
        assert result.provider == "openrouter"
