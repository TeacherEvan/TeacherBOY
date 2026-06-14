"""OpenRouter Service - LLM access via OpenRouter API."""

import logging
import time
from typing import Any

import httpx
from pydantic import BaseModel

from src.config import settings
from src.services.metrics_service import metrics_service

logger = logging.getLogger(__name__)


class OpenRouterChoice(BaseModel):
    """Single choice from OpenRouter API response."""

    message: dict[str, Any]


class OpenRouterResponse(BaseModel):
    """OpenRouter API response model."""

    choices: list[OpenRouterChoice] = []


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

    def model_for_translation(self) -> str | None:
        """Return the OpenRouter model preferred for translation, or None."""
        return settings.openrouter_translation_model

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

        start_time = time.perf_counter()
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
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Record detailed latency metrics
            metrics_service.record_provider_latency("openrouter", elapsed_ms)
            metrics_service.record_provider_model_latency("openrouter", target_model, elapsed_ms)
            metrics_service.record_provider_request_type_latency("openrouter", "chat_completion", elapsed_ms)

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

            # Parse response with Pydantic for defensive parsing
            try:
                parsed = OpenRouterResponse.model_validate(response.json())
            except Exception as exc:
                logger.warning("⚠️ OpenRouter response parsing failed: %s", exc)
                return None

            if parsed.choices:
                content = parsed.choices[0].message.get("content", "")
                logger.info("🤖 OpenRouter response from %s (%s chars)", target_model, len(content))
                return content

            logger.warning("⚠️ OpenRouter response missing choices: %s", parsed)
            return None

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            metrics_service.record_provider_latency("openrouter", elapsed_ms)
            metrics_service.record_provider_model_latency("openrouter", target_model, elapsed_ms)
            metrics_service.record_provider_request_type_latency("openrouter", "chat_completion", elapsed_ms)
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

        start_time = time.perf_counter()
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
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Record detailed latency metrics
            metrics_service.record_provider_latency("openrouter", elapsed_ms)
            metrics_service.record_provider_model_latency("openrouter", target_model, elapsed_ms)
            metrics_service.record_provider_request_type_latency("openrouter", "chat_completion_vision", elapsed_ms)

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

            # Parse response with Pydantic for defensive parsing
            try:
                parsed = OpenRouterResponse.model_validate(response.json())
            except Exception as exc:
                logger.warning("⚠️ OpenRouter vision response parsing failed: %s", exc)
                return None

            if parsed.choices:
                content = parsed.choices[0].message.get("content", "")
                logger.info("📸 OpenRouter vision response from %s (%s chars)", target_model, len(content))
                return content

            logger.warning("⚠️ OpenRouter vision response missing choices: %s", parsed)
            return None

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            metrics_service.record_provider_latency("openrouter", elapsed_ms)
            metrics_service.record_provider_model_latency("openrouter", target_model, elapsed_ms)
            metrics_service.record_provider_request_type_latency("openrouter", "chat_completion_vision", elapsed_ms)
            logger.error("❌ OpenRouter vision request failed: %s", exc, exc_info=True)
            self._last_error = str(exc)
            return None


openrouter_service = OpenRouterService()
