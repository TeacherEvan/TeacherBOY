"""Tests for Gemini Service - TDD: Write test first, watch it fail."""

from unittest.mock import AsyncMock, Mock

import pytest


class TestGeminiService:
    """Test Gemini service for LLM completion and translation."""

    @pytest.mark.asyncio
    async def test_gemini_chat_completion_returns_result_when_configured(self):
        """Gemini service should return completion when properly configured."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-api-key-12345", model="gemini-2.5-flash")

        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=Mock(
            status_code=200,
            json=Mock(return_value={
                "candidates": [{"content": {"parts": [{"text": "Hello from Gemini"}]}}]
            })
        ))
        service.set_client(mock_client)

        result = await service.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7
        )

        assert result == "Hello from Gemini"

    @pytest.mark.asyncio
    async def test_gemini_chat_completion_returns_none_when_not_configured(self):
        """Gemini service should return None when not configured."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        # Don't configure - api_key remains empty

        result = await service.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_gemini_translation_works(self):
        """Gemini service should handle translation requests."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-api-key-12345", model="gemini-2.5-flash")

        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=Mock(
            status_code=200,
            json=Mock(return_value={
                "candidates": [{"content": {"parts": [{"text": "สวัสดี"}]}}]
            })
        ))
        service.set_client(mock_client)

        result = await service.chat_completion(
            messages=[
                {"role": "system", "content": "Translate to Thai"},
                {"role": "user", "content": "Translate from en to th: Hello"}
            ],
            temperature=0.2
        )

        assert result == "สวัสดี"

    @pytest.mark.asyncio
    async def test_gemini_is_configured_returns_true_when_configured(self):
        """is_configured should return True when api_key and model are set."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-key", model="gemini-2.5-flash")

        assert service.is_configured() is True

    @pytest.mark.asyncio
    async def test_gemini_is_configured_returns_false_when_not_configured(self):
        """is_configured should return False when api_key is missing."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()

        assert service.is_configured() is False

    @pytest.mark.asyncio
    async def test_gemini_error_handling(self):
        """Gemini service should handle API errors gracefully."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-key", model="gemini-2.5-flash")

        mock_client = Mock()
        mock_client.post = AsyncMock(return_value=Mock(
            status_code=400,
            text="Bad Request"
        ))
        service.set_client(mock_client)

        result = await service.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            temperature=0.7
        )

        assert result is None
        status, error, model = service.get_last_error()
        assert status == 400
        assert error is not None
        assert "Bad Request" in error
