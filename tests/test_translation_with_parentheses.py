"""Tests for AI translation handling of parenthesized text."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.services.ai_translation_service import AITranslationService


def test_build_messages_mentions_parenthesized_text_preservation():
    service = AITranslationService(github_models=Mock(), openrouter=Mock())

    messages = service._build_messages("(Pim) had the day off", "en", "th")

    assert "parenthesized text" in messages[0]["content"]
    assert "Do not explain" in messages[0]["content"]


@pytest.mark.asyncio
async def test_translate_returns_parenthesized_text_unchanged_when_provider_does():
    github = Mock()
    github.is_configured.return_value = True
    github.chat_completion = AsyncMock(return_value="(Pim) มีวันหยุด")

    openrouter = Mock()
    openrouter.is_configured.return_value = False
    openrouter.chat_completion = AsyncMock()

    service = AITranslationService(github_models=github, openrouter=openrouter)

    result = await service.translate(
        "(Pim) had the day off",
        source_lang="en",
        target_lang="th",
    )

    assert result is not None
    assert result.text == "(Pim) มีวันหยุด"
    assert result.provider == "github_models"
