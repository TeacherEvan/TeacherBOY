"""
OpenRouter Service - LLM access via OpenRouter API.
"""

import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)


class OpenRouterService:
    """Service for interacting with OpenRouter API."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.client = http_client
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.api_key = settings.openrouter_api_key
        self.default_model = settings.openrouter_default_model

        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_model: str | None = None

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    def set_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def is_configured(self) -> bool:
        return settings.is_openrouter_configured()

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ OpenRouter API key not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for OpenRouter")
            return None

        target_model = model or self.default_model
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        try:
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/TeacherEvan/TeacherBOY",
                "X-Title": "Ms. Green",
                "Content-Type": "application/json",
            }

            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
            }

            response = await self.client.post(self.api_url, headers=headers, json=payload, timeout=30.0)

            if response.status_code != 200:
                err_text = (response.text or "").strip()
                if len(err_text) > 1000:
                    err_text = err_text[:1000] + "..."
                self._last_status_code = response.status_code
                self._last_error = err_text
                logger.error(
                    "❌ OpenRouter error %s (model=%s): %s",
                    response.status_code,
                    target_model,
                    err_text,
                )
                return None

            data = response.json()

            if "choices" in data and data["choices"]:
                content = data["choices"][0]["message"]["content"]
                logger.info("🤖 OpenRouter response from %s (%s chars)", target_model, len(content))
                return content

            logger.warning("⚠️ OpenRouter response missing choices: %s", data)
            return None

        except Exception as exc:
            logger.error("❌ OpenRouter request failed: %s", exc, exc_info=True)
            self._last_error = str(exc)
            return None

    async def chat_completion_with_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ OpenRouter API key not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for OpenRouter")
            return None

        target_model = model or self.default_model
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        try:
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/TeacherEvan/TeacherBOY",
                "X-Title": "Ms. Green",
                "Content-Type": "application/json",
            }

            payload: dict[str, Any] = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
            }

            if max_tokens:
                payload["max_tokens"] = max_tokens

            response = await self.client.post(self.api_url, headers=headers, json=payload, timeout=30.0)

            if response.status_code != 200:
                err_text = (response.text or "").strip()
                if len(err_text) > 1000:
                    err_text = err_text[:1000] + "..."
                self._last_status_code = response.status_code
                self._last_error = err_text
                logger.error(
                    "❌ OpenRouter vision error %s (model=%s): %s",
                    response.status_code,
                    target_model,
                    err_text,
                )
                return None

            data = response.json()

            if "choices" in data and data["choices"]:
                content = data["choices"][0]["message"]["content"]
                logger.info("📸 OpenRouter vision response from %s (%s chars)", target_model, len(content))
                return content

            logger.warning("⚠️ OpenRouter vision response missing choices: %s", data)
            return None

        except Exception as exc:
            logger.error("❌ OpenRouter vision request failed: %s", exc, exc_info=True)
            self._last_error = str(exc)
            return None


openrouter_service = OpenRouterService()
