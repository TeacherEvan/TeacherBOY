"""
THIN Hermes/OpenAI-compatible fallback client.

Toggle via env/config:
- HERMES_API_KEY
- HERMES_BASE_URL
- HERMES_MODEL
- HERMES_VISION_MODEL
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class HermesService:
    def __init__(self) -> None:
        self.api_key = ""
        self.base_url = ""
        self.model = ""
        self.vision_model = ""
        self._client: httpx.AsyncClient | None = None

    @property
    def chat_url(self) -> str:
        base = (self.base_url or "").rstrip("/")
        if not base:
            return ""
        return f"{base}/v1/chat/completions"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.chat_url and self.model)

    def is_vision_configured(self) -> bool:
        return bool(self.api_key and self.chat_url and (self.vision_model or self.model))

    def set_client(self, client: httpx.AsyncClient | None) -> None:
        self._client = client

    def configure(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        vision_model: str | None = None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.base_url = (base_url or "").strip()
        self.model = (model or "").strip()
        self.vision_model = (vision_model or "").strip()
        if not self.is_configured():
            logger.warning("Hermes fallback config is incomplete")

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str | None:
        if not self.is_configured():
            return None

        target_model = model or self.model or ""
        if not target_model:
            return None

        client = self._client or httpx.AsyncClient(timeout=30.0)
        should_close = self._client is None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            response = await client.post(
                self.chat_url,
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.warning(
                    "Hermes fallback error %s: %s",
                    response.status_code,
                    response.text[:220],
                )
                return None
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(content, str) and content.strip():
                return content
            return None
        except Exception as exc:  # pragma: no cover
            logger.warning("Hermes fallback request failed: %s", exc)
            return None
        finally:
            if should_close:
                await client.aclose()

    async def chat_completion_with_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str | None:
        if not (self.api_key and self.chat_url and (self.vision_model or self.model)):
            logger.warning("Hermes vision is not configured")
            return None

        target_model = model or self.vision_model or self.model or ""
        if not target_model:
            return None

        client = self._client or httpx.AsyncClient(timeout=45.0)
        should_close = self._client is None
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        try:
            response = await client.post(
                self.chat_url,
                headers=headers,
                json=payload,
            )
            if response.status_code != 200:
                logger.warning(
                    "Hermes vision error %s: %s",
                    response.status_code,
                    response.text[:220],
                )
                return None
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content")
            if isinstance(content, str) and content.strip():
                return content
            return None
        except Exception as exc:  # pragma: no cover
            logger.warning("Hermes vision request failed: %s", exc)
            return None
        finally:
            if should_close:
                await client.aclose()


    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        """Return last error detail. HermesService doesn't track errors, returns None."""
        return (None, None, None)


hermes_service = HermesService()
