from unittest.mock import AsyncMock, Mock

import pytest

from src.services.ai_translation_service import AITranslationService


@pytest.mark.asyncio
async def test_translate_uses_first_configured_provider():
    github = Mock()
    github.is_configured.return_value = True
    github.chat_completion = AsyncMock(return_value="สวัสดี")
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

    result = await service.translate("Hello", source_lang="en", target_lang="th")
    assert result is not None
    assert isinstance(result.text, str)
    assert result.text == "สวัสดี"
