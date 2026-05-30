import pytest
from unittest.mock import AsyncMock

from src.services.ai_review_service import AIReviewService


@pytest.mark.asyncio
async def test_ai_review_service_uses_github_models_first():
    github = AsyncMock()
    github.is_configured.return_value = True
    github.chat_completion.return_value = "translated text"

    openrouter = AsyncMock()
    openrouter.is_configured.return_value = True

    service = AIReviewService(
        github_service=github,
        openrouter_service=openrouter,
    )
    result = await service.translate_and_summarize("ข้อความภาษาไทย")

    assert result == "translated text"
    github.chat_completion.assert_awaited_once()
    openrouter.chat_completion.assert_not_awaited()


@pytest.mark.asyncio
async def test_ai_review_service_falls_back_to_openrouter():
    github = AsyncMock()
    github.is_configured.return_value = True
    github.chat_completion.return_value = None

    openrouter = AsyncMock()
    openrouter.is_configured.return_value = True
    openrouter.chat_completion.return_value = "fallback text"

    service = AIReviewService(
        github_service=github,
        openrouter_service=openrouter,
    )
    result = await service.translate_and_summarize("ข้อความภาษาไทย")

    assert result == "fallback text"
    openrouter.chat_completion.assert_awaited_once()
