"""NOUS Portal Service - LLM access via NOUS Portal API."""

import logging
from typing import Any

import httpx
from pydantic import BaseModel

from src.config import settings

logger = logging.getLogger(__name__)


class NousChoice(BaseModel):
    """Single choice from NOUS Portal API response."""

    message: dict[str, Any]


class NousResponse(BaseModel):
    """NOUS Portal API response model."""

    choices: list[NousChoice] = []


class NousService:
    """Service for interacting with NOUS Portal API."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.client = http_client
        self.api_url = (settings.nous_base_url or "https://api.nousresearch.com/v1").rstrip("/") + "/chat/completions"
        self.api_key = settings.nous_api_key
        self.default_model = settings.nous_model or "Hermes-3-Llama-3.1-70B"
        self.default_vision_model = settings.nous_vision_model or "Hermes-3-Llama-3.1-70B-Vision"

        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_model: str | None = None

    def model_for_translation(self) -> str | None:
        """Return the NOUS model preferred for translation, or None."""
        return self.default_model

    def model_for_vision(self) -> str | None:
        """Return the NOUS model preferred for vision tasks, or None."""
        return self.default_vision_model

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    def set_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def is_configured(self) -> bool:
        return settings.is_nous_configured()

    def is_vision_configured(self) -> bool:
        return self.is_configured() and bool(self.default_vision_model)

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ NOUS Portal API key not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for NOUS Portal")
            return None

        target_model = model or self.default_model
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        try:
            headers = {
                "Authorization": f"Bearer {settings.nous_api_key}",
                "HTTP-Referer": "https://github.com/TeacherEvan/TeacherBOY",
                "X-Title": "Ms. Green",
                "Content-Type": "application/json",
            }

            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": 4096,
            }

            logger.debug(f"🔮 NOUS Portal request: model={target_model}, messages={len(messages)}")
            response = await self.client.post(self.api_url, headers=headers, json=payload, timeout=60.0)
            response.raise_for_status()

            data = response.json()
            result = NousResponse(**data)

            if result.choices and result.choices[0].message.get("content"):
                content = result.choices[0].message["content"]
                logger.debug(f"🔮 NOUS Portal response: {len(content)} chars")
                return content

            logger.warning("⚠️ NOUS Portal returned empty content")
            return None

        except httpx.HTTPStatusError as e:
            self._last_error = e.response.text
            self._last_status_code = e.response.status_code
            logger.error(f"❌ NOUS Portal HTTP error {e.response.status_code}: {e.response.text}")
            return None
        except Exception as e:
            self._last_error = str(e)
            logger.error(f"❌ NOUS Portal error: {e}", exc_info=True)
            return None


# Singleton instance
nous_service = NousService()

# Alias for backward compatibility
nous_inference_service = nous_service