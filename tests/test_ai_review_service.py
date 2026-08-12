from unittest.mock import AsyncMock, patch

import pytest

from src.services.ai_review_service import AIReviewService


@pytest.mark.asyncio
async def test_ai_review_service_uses_fallback_chain():
    """Should use fallback chain (Gemini first) for translation."""
    with patch("src.services.ai_review_service.chat_completion_with_fallback") as mock_fallback:
        mock_fallback.return_value = "translated text"

        service = AIReviewService()
        result = await service.translate_and_summarize("ข้อความภาษาไทย")

        assert result == "translated text"
        mock_fallback.assert_awaited_once()


@pytest.mark.asyncio
async def test_ai_review_service_falls_back_to_openrouter():
    """Should fall back to OpenRouter when fallback chain returns None."""
    with patch("src.services.ai_review_service.chat_completion_with_fallback") as mock_fallback:
        with patch("src.services.openrouter_service.openrouter_service") as mock_openrouter:
            mock_fallback.return_value = None
            mock_openrouter.is_configured.return_value = True
            mock_openrouter.chat_completion = AsyncMock(return_value="fallback text")

            service = AIReviewService(openrouter_service=mock_openrouter)
            result = await service.translate_and_summarize("ข้อความภาษาไทย")

            assert result == "fallback text"
            mock_openrouter.chat_completion.assert_awaited_once()
