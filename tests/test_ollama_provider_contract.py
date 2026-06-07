from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import src.utils.llm_fallback as lf


@pytest.mark.asyncio
async def test_chat_completion_with_fallback_routes_openrouter_before_github():
    """Priority fallback should skip github because openrouter succeeds first."""
    fake_openrouter = MagicMock()
    fake_openrouter.is_configured.return_value = True
    fake_openrouter.chat_completion = AsyncMock(return_value="from openrouter")

    fake_github = MagicMock()
    fake_github.is_configured.return_value = True
    fake_github.chat_completion = AsyncMock(return_value="from github")

    mock_settings = MagicMock()
    mock_settings.get_llm_provider_priority.return_value = ["openrouter", "github"]
    mock_settings.openrouter_default_model = None
    mock_settings.github_models_default_model = None

    with patch.object(lf, "settings", mock_settings):
        with patch.object(lf, "openrouter_service", fake_openrouter):
            with patch.object(lf, "github_models_service", fake_github):
                result = await lf.chat_completion_with_fallback(
                    messages=[{"role": "user", "content": "hi"}],
                    temperature=0.0,
                    max_tokens=1,
                )

    assert result == "from openrouter"
    fake_openrouter.chat_completion.assert_awaited_once()
    fake_github.chat_completion.assert_not_called()
