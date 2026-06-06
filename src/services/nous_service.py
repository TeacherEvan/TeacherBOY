"""
Nous Inference Service — reads the live OAuth token from ~/.hermes/auth.json
and calls the Nous Portal inference API. Uses free-tier models.

Token refresh is handled externally by the Hermes agent; we re-read auth.json
on every request so we never stale-out.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_AUTH_JSON_PATH = os.path.expanduser("~/.hermes/auth.json")
_DEFAULT_BASE_URL = "https://inference-api.nousresearch.com/v1"
_DEFAULT_MODEL = "stepfun/step-3.7-flash:free"


class NousInferenceService:
    """Thin wrapper around the Nous Portal OpenAI-compatible chat endpoint."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.client = http_client
        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_model: str | None = None

    # ------------------------------------------------------------------
    # Token helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _read_auth_json() -> dict[str, Any]:
        try:
            with open(_AUTH_JSON_PATH, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            return {}

    def _get_token(self) -> str | None:
        data = self._read_auth_json()
        providers = data.get("providers", {})
        nous = providers.get("nous", {})
        token = nous.get("agent_key") or nous.get("access_token")
        if isinstance(token, str) and token.strip():
            return token.strip()
        return None

    def _base_url(self) -> str:
        data = self._read_auth_json()
        providers = data.get("providers", {})
        nous = providers.get("nous", {})
        url = nous.get("inference_base_url", "")
        if isinstance(url, str) and url.strip():
            return url.rstrip("/")
        return _DEFAULT_BASE_URL

    # ------------------------------------------------------------------
    # Public API (mirrors github_models / openrouter signatures)
    # ------------------------------------------------------------------
    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    def set_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def is_configured(self) -> bool:
        return self._get_token() is not None

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        retry_on_rate_limit: bool = True,
    ) -> str | None:
        token = self._get_token()
        if not token:
            self._last_error = "Nous OAuth token not found in ~/.hermes/auth.json"
            logger.warning("⚠️ %s", self._last_error)
            return None

        target_model = model or _DEFAULT_MODEL
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        if max_tokens:
            payload["max_tokens"] = max_tokens

        client = self.client or httpx.AsyncClient(timeout=30.0)
        should_close = self.client is None
        url = f"{self._base_url()}/chat/completions"

        try:
            response = await client.post(url, headers=headers, json=payload)
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("❌ Nous inference request failed: %s", exc)
            return None
        finally:
            if should_close:
                await client.aclose()

        self._last_status_code = response.status_code

        if response.status_code != 200:
            err_text = (response.text or "").strip()
            if len(err_text) > 500:
                err_text = err_text[:500] + "..."
            self._last_error = err_text
            logger.error(
                "❌ Nous inference error %s (model=%s): %s",
                response.status_code,
                target_model,
                err_text,
            )
            return None

        try:
            data = response.json()
        except Exception as exc:
            self._last_error = f"Invalid JSON: {exc}"
            return None

        if "choices" in data and data["choices"]:
            content = data["choices"][0]["message"]["content"]
            logger.info(
                "🤖 Nous inference response from %s (%s chars)",
                target_model,
                len(content),
            )
            return content

        logger.warning("⚠️ Nous inference response missing choices: %s", data)
        return None

    async def chat_completion_with_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str | None:
        """Vision is not supported on the free model; fall back to text."""
        return await self.chat_completion(
            messages,  # type: ignore[arg-type]
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )


nous_inference_service = NousInferenceService()
