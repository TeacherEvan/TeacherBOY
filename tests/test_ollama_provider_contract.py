from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.utils.llm_fallback as lf


@pytest.mark.asyncio
async def test_chat_completion_with_fallback_routes_openrouter_before_gemini():
    """Priority fallback should skip openrouter if gemini succeeds first (Gemini is first in priority)."""
    fake_gemini = MagicMock()
    fake_gemini.is_configured.return_value = True
    fake_gemini.chat_completion = AsyncMock(return_value="from gemini")

    fake_openrouter = MagicMock()
    fake_openrouter.is_configured.return_value = True
    fake_openrouter.chat_completion = AsyncMock(return_value="from openrouter")

    mock_settings = MagicMock()
    mock_settings.get_llm_provider_priority.return_value = ["gemini", "openrouter"]
    mock_settings.gemini_model = None
    mock_settings.openrouter_default_model = None

    with patch.object(lf, "settings", mock_settings):
        with patch.object(lf, "gemini_service", fake_gemini):
            with patch.object(lf, "openrouter_service", fake_openrouter):
                result = await lf.chat_completion_with_fallback(
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=0.0,
                    max_tokens=1,
                )

    assert result == "from gemini"
    fake_gemini.chat_completion.assert_awaited_once()
    fake_openrouter.chat_completion.assert_not_called()
