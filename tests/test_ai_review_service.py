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


class _FailingGithubService:
    def is_configured(self):
        return True

    async def chat_completion(self, **kwargs):
        raise RuntimeError("github failure")


class _OpenRouterService:
    def is_configured(self):
        return True

    async def chat_completion(self, **kwargs):
        return "fallback after exception"


@pytest.mark.asyncio
async def test_ai_review_service_falls_back_when_github_raises():
    service = AIReviewService(
        github_service=_FailingGithubService(),
        openrouter_service=_OpenRouterService(),
    )

    result = await service.translate_and_summarize("ข้อความภาษาไทย")

    assert result == "fallback after exception"


class _FailingOpenRouterService:
    def is_configured(self):
        return True

    async def chat_completion(self, **kwargs):
        raise RuntimeError("openrouter failure")


@pytest.mark.asyncio
async def test_ai_review_service_returns_none_when_both_providers_fail():
    service = AIReviewService(
        github_service=_FailingGithubService(),
        openrouter_service=_FailingOpenRouterService(),
    )

    result = await service.translate_and_summarize("ข้อความภาษาไทย")

    assert result is None
