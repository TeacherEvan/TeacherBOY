from unittest.mock import AsyncMock, Mock

import pytest

from src.services.ai_translation_service import AITranslationService


@pytest.mark.asyncio
async def test_translate_uses_github_models_first():
    github = Mock()
    github.is_configured.return_value = True
    github.chat_completion = AsyncMock(return_value="สวัสดี")

    openrouter = Mock()
    openrouter.is_configured.return_value = True
    openrouter.chat_completion = AsyncMock()

    service = AITranslationService(github_models=github, openrouter=openrouter)

    result = await service.translate("Hello", source_lang="en", target_lang="th")

    assert result.text == "สวัสดี"
    assert result.provider == "github_models"
    openrouter.chat_completion.assert_not_called()


@pytest.mark.asyncio
async def test_translate_falls_back_to_openrouter_when_github_models_returns_none():
    github = Mock()
    github.is_configured.return_value = True
    github.chat_completion = AsyncMock(return_value=None)
    github.get_last_error = Mock(return_value=(None, None, None))

    openrouter = Mock()
    openrouter.is_configured.return_value = True
    openrouter.chat_completion = AsyncMock(return_value="Hello")
    openrouter.get_last_error = Mock(return_value=(None, None, None))

    service = AITranslationService(github_models=github, openrouter=openrouter)

    result = await service.translate("สวัสดี", source_lang="th", target_lang="en")

    assert result.text == "Hello"
    assert result.provider == "openrouter"
