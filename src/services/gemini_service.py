"""Gemini Service - Google Generative AI API via native REST (OpenAI-compatible endpoint).

Uses the Google AI Studio / Vertex AI compatible endpoint:
- Base URL: https://generativelanguage.googleapis.com/v1beta
- Model: gemini-2.5-flash (free tier)
- Auth: GOOGLE_API_KEY or GEMINI_API_KEY (Bearer token)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class GeminiService:
    """Service for interacting with Google Gemini API (OpenAI-compatible)."""

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self._client = http_client
        self.api_key: str = ""
        self.base_url: str = "https://generativelanguage.googleapis.com/v1beta"
        self.model: str = "gemini-2.5-flash"
        self.vision_model: str = "gemini-2.5-flash"
        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_model: str | None = None

    @property
    def chat_url(self) -> str:
        """Build chat URL for the default model (backward compatibility)."""
        return self._build_url(self.model)

    @property
    def vision_url(self) -> str:
        """Build vision URL for the default vision model (backward compatibility)."""
        return self._build_url(self.vision_model)

    def _build_url(self, model: str) -> str:
        """Build API URL for a specific model."""
        base = (self.base_url or "").rstrip("/")
        if not base:
            return ""
        return f"{base}/models/{model}:generateContent"

    def is_configured(self) -> bool:
        return bool(self.api_key and self.chat_url and self.model)

    def is_vision_configured(self) -> bool:
        return bool(self.api_key and self.vision_url and (self.vision_model or self.model))

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
        if api_key is not None:
            self.api_key = api_key.strip()
        if base_url is not None:
            self.base_url = base_url.strip()
        if model is not None:
            self.model = model.strip() or "gemini-2.5-flash"
        if vision_model is not None:
            self.vision_model = vision_model.strip() or "gemini-2.5-flash"
        if not self.is_configured():
            logger.warning("Gemini fallback config is incomplete")

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    def _build_payload(
        self,
        messages: list[dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Build Gemini API payload from OpenAI-format messages."""
        # Convert OpenAI messages to Gemini format
        contents = []
        system_instruction = None

        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")

            if role == "system":
                system_instruction = content
            elif role == "user":
                parts = []
                if isinstance(content, str):
                    # Simple text message
                    parts.append({"text": content})
                elif isinstance(content, list):
                    # OpenAI format: list of text and image parts
                    for item in content:
                        if isinstance(item, dict):
                            item_type = item.get("type", "text")
                            if item_type == "text":
                                text = item.get("text", "")
                                if text:
                                    parts.append({"text": text})
                            elif item_type == "image_url":
                                image_url = item.get("image_url", {})
                                url = image_url.get("url", "")
                                if url:
                                    # Convert data URL to inline_data
                                    if url.startswith("data:"):
                                        # Format: data:image/jpeg;base64,<base64_data>
                                        try:
                                            header, b64_data = url.split(",", 1)
                                            mime_type = header.split(":")[1].split(";")[0]
                                            parts.append({"inline_data": {"mime_type": mime_type, "data": b64_data}})
                                        except Exception:
                                            logger.warning("Failed to parse data URL: %s", url[:100])
                if parts:
                    contents.append({"role": "user", "parts": parts})
            elif role == "assistant":
                # Assistant messages are typically text only
                if isinstance(content, str):
                    contents.append({"role": "model", "parts": [{"text": content}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": temperature,
            },
        }

        if max_tokens:
            payload["generationConfig"]["maxOutputTokens"] = max_tokens

        if system_instruction:
            payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        return payload

    def _parse_response(self, data: dict[str, Any]) -> str | None:
        """Parse Gemini response to extract text content."""
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                return None

            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if not parts:
                return None

            # Combine all text parts
            texts = [part.get("text", "") for part in parts if part.get("text")]
            return "".join(texts) if texts else None
        except Exception:
            return None

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ Gemini API key not configured")
            return None

        if not self._client:
            logger.warning("⚠️ HTTP client not available for Gemini")
            return None

        target_model = model or self.model
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        try:
            payload = self._build_payload(messages, temperature, max_tokens)

            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            response = await self._client.post(
                self._build_url(target_model),
                headers=headers,
                json=payload,
                timeout=30.0,
            )

            if response.status_code != 200:
                err_text = (response.text or "").strip()
                if len(err_text) > 1000:
                    err_text = err_text[:1000] + "..."
                self._last_status_code = response.status_code
                self._last_error = err_text
                logger.error(
                    "❌ Gemini error %s (model=%s): %s",
                    response.status_code,
                    target_model,
                    err_text,
                )
                return None

            data = response.json()
            content = self._parse_response(data)

            if isinstance(content, str) and content.strip():
                logger.info("🤖 Gemini response from %s (%s chars)", target_model, len(content))
                return content

            logger.warning("⚠️ Gemini response missing content: %s", data)
            return None

        except Exception as exc:
            logger.error("❌ Gemini request failed: %s", exc, exc_info=True)
            self._last_error = str(exc)
            return None

    async def chat_completion_with_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
    ) -> str | None:
        if not self.is_vision_configured():
            logger.warning("⚠️ Gemini vision not configured")
            return None

        if not self._client:
            logger.warning("⚠️ HTTP client not available for Gemini vision")
            return None

        target_model = model or self.vision_model
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        try:
            payload = self._build_payload(messages, temperature, max_tokens)

            headers = {
                "x-goog-api-key": self.api_key,
                "Content-Type": "application/json",
            }

            response = await self._client.post(
                self._build_url(target_model),
                headers=headers,
                json=payload,
                timeout=45.0,
            )

            if response.status_code != 200:
                err_text = (response.text or "").strip()
                if len(err_text) > 1000:
                    err_text = err_text[:1000] + "..."
                self._last_status_code = response.status_code
                self._last_error = err_text
                logger.error(
                    "❌ Gemini vision error %s (model=%s): %s",
                    response.status_code,
                    target_model,
                    err_text,
                )
                return None

            data = response.json()
            content = self._parse_response(data)

            if isinstance(content, str) and content.strip():
                logger.info("📸 Gemini vision response from %s (%s chars)", target_model, len(content))
                return content

            logger.warning("⚠️ Gemini vision response missing content: %s", data)
            return None

        except Exception as exc:
            logger.error("❌ Gemini vision request failed: %s", exc, exc_info=True)
            self._last_error = str(exc)
            return None


gemini_service = GeminiService()
