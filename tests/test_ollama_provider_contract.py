"""Provider contract test specifically for Ollama routing in the fallback loop."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.config import Settings
from src.utils.llm_fallback import chat_completion_with_fallback

pytestmark = pytest.mark.asyncio


@pytest.fixture()
def ollama_priority_settings() -> Settings:
    s = Settings()
    s.llm_provider_priority = "ollama,openrouter,github,hermes"
    s.ollama_enabled = True
    s.ollama_default_model = "ollama-test-model"
    s.ollama_base_url = "http://localhost:11434"
    return s


async def test_ollama_provider_routes_first(
    ollama_priority_settings: Settings,
) -> None:
    fake_result = "ollama-first"
    with patch("src.utils.llm_fallback.settings", ollama_priority_settings), patch(
        "src.services.ollama_service.ollama_service"
    ) as ollama_svc:
        ollama_svc.chat_completion = AsyncMock(return_value=fake_result)

        result = await chat_completion_with_fallback(
            messages=[{"role": "user", "content": "hello"}]
        )

    assert result == fake_result
    ollama_svc.chat_completion.assert_awaited_once()
    model_arg = ollama_svc.chat_completion.call_args.kwargs["model"]
    assert model_arg == "ollama-test-model"
