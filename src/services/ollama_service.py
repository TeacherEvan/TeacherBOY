"""Ollama Service - OpenAI-compatible local LLM provider for TeacherBOY."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60.0
_DEFAULT_MODEL = "hermes2:latest"


class OllamaService:
    """Thin async client around Ollama's /v1/chat/completions endpoint."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        default_model: str = _DEFAULT_MODEL,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.default_model = default_model
        self.timeout = timeout
        self._client = self._build_client()

    def _build_client(self):
        import httpx

        return httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)

    def is_configured(self) -> bool:
        return True

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        retry_on_rate_limit: bool = False,
    ) -> str | None:
        import time as _time

        payload: dict[str, Any] = {
            "model": model or self.default_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        start = _time.perf_counter()
        response = await self._client.post("/v1/chat/completions", json=payload)
        elapsed = _time.perf_counter() - start
        response.raise_for_status()
        logger.debug("Ollama chat completed in %.3fs", elapsed)

        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return None
        return (choices[0].get("message") or {}).get("content")

    async def close(self) -> None:
        await self._client.aclose()


# Default singleton used by the app, consistent with other service modules.
ollama_service = OllamaService()
