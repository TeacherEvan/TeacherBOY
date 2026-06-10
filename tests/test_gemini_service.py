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

        assert result == "\u0e2a\u0e27\u0e31\u0e2a\u0e14\u0e35"

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

    @pytest.mark.asyncio
    async def test_gemini_chat_completion_uses_passed_model_without_mutation(self):
        """chat_completion should use passed model parameter without mutating instance state."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-key", model="gemini-2.5-flash")

        # Track which URL was called
        called_urls = []

        mock_client = Mock()

        async def mock_post(url, **kwargs):
            called_urls.append(url)
            return Mock(
                status_code=200,
                json=Mock(return_value={
                    "candidates": [{"content": {"parts": [{"text": "Response"}]}}]
                })
            )

        mock_client.post = mock_post
        service.set_client(mock_client)

        # Call with a different model
        await service.chat_completion(
            messages=[{"role": "user", "content": "Hello"}],
            model="gemini-2.5-pro",
            temperature=0.7
        )

        # Verify the instance model was NOT mutated
        assert service.model == "gemini-2.5-flash"

        # Verify the correct URL was called (with the passed model)
        assert len(called_urls) == 1
        assert "gemini-2.5-pro" in called_urls[0]
        assert "gemini-2.5-flash" not in called_urls[0]

    @pytest.mark.asyncio
    async def test_gemini_vision_completion_handles_image_parts(self):
        """chat_completion_with_vision should convert OpenAI image parts to Gemini format."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-key", model="gemini-2.5-flash", vision_model="gemini-2.5-flash")

        mock_client = Mock()

        async def mock_post(url, **kwargs):
            # Verify the payload has image parts converted
            payload = kwargs.get("json", {})
            contents = payload.get("contents", [])
            # Should have at least one content with image part
            assert len(contents) > 0
            # Check for inline_data in parts (Gemini format for images)
            found_image = False
            for content in contents:
                parts = content.get("parts", [])
                for part in parts:
                    if "inline_data" in part:
                        found_image = True
                        assert part["inline_data"]["mime_type"] == "image/jpeg"
                        break
            assert found_image, "Image not converted to Gemini inline_data format"

            return Mock(
                status_code=200,
                json=Mock(return_value={
                    "candidates": [{"content": {"parts": [{"text": "Image analysis result"}]}}]
                })
            )

        mock_client.post = mock_post
        service.set_client(mock_client)

        # OpenAI format with image_url
        result = await service.chat_completion_with_vision(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "Describe this image"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,/9j/4AAQSkZJRg=="}}
                ]
            }],
            temperature=0.7
        )

        assert result == "Image analysis result"

    @pytest.mark.asyncio
    async def test_gemini_vision_completion_uses_passed_model_without_mutation(self):
        """chat_completion_with_vision should use passed model without mutating instance state."""
        from src.services.gemini_service import GeminiService

        service = GeminiService()
        service.configure(api_key="test-key", model="gemini-2.5-flash", vision_model="gemini-2.5-flash")

        called_urls = []

        mock_client = Mock()

        async def mock_post(url, **kwargs):
            called_urls.append(url)
            return Mock(
                status_code=200,
                json=Mock(return_value={
                    "candidates": [{"content": {"parts": [{"text": "Vision response"}]}}]
                })
            )

        mock_client.post = mock_post
        service.set_client(mock_client)

        # Call with a different vision model
        await service.chat_completion_with_vision(
            messages=[{"role": "user", "content": "Describe image"}],
            model="gemini-2.5-pro",
            temperature=0.7
        )

        # Verify the instance vision_model was NOT mutated
        assert service.vision_model == "gemini-2.5-flash"

        # Verify the correct URL was called (with the passed model)
        assert len(called_urls) == 1
        assert "gemini-2.5-pro" in called_urls[0]
        assert "gemini-2.5-flash" not in called_urls[0]
