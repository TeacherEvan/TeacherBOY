"""
HuggingFace Inference API Service - Free AI inference via HuggingFace Inference API.

This service provides access to AI models via HF's serverless inference API.
Endpoint: https://api-inference.huggingface.co/models/{model}

Available free-tier vision models include:
- meta/llama-3.2-90b-vision-instruct (default)
- And more at https://huggingface.co/models?pipeline_tag=image-text-to-text

Auth: Bearer token from https://huggingface.co/settings/tokens
"""

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Rate limit retry delays (exponential backoff)
RATE_LIMIT_RETRY_DELAYS = [1.0, 2.0, 5.0, 10.0]


class HFInferenceService:
    """
    Service for interacting with HuggingFace Inference API.

    Uses HF API token for authentication. Create a token at:
    https://huggingface.co/settings/tokens with 'read' access.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.client = http_client
        self.api_base_url = "https://api-inference.huggingface.co/models"
        self.default_vision_model = settings.hf_inference_vision_model

        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_model: str | None = None

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    def set_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def is_configured(self) -> bool:
        return settings.is_hf_inference_configured()

    def is_vision_configured(self) -> bool:
        return self.is_configured()

    def _get_headers(self) -> dict[str, str]:
        if not settings.hf_inference_api_key:
            return {}
        return {
            "Authorization": f"Bearer {settings.hf_inference_api_key}",
            "Content-Type": "application/json",
        }

    def _get_model_url(self, model: str | None) -> str:
        target_model = model or self.default_vision_model
        return f"{self.api_base_url}/{target_model}"

    async def chat_completion_with_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int | None = None,
        retry_on_rate_limit: bool = True,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ HF Inference API key not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for HF Inference")
            return None

        target_model = model or self.default_vision_model
        model_url = self._get_model_url(model)

        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        attempt = 0
        max_attempts = len(RATE_LIMIT_RETRY_DELAYS) + 1 if retry_on_rate_limit else 1

        while attempt < max_attempts:
            try:
                logger.info("📸 Sending vision request to HF Inference (%s)...", target_model)

                response = await self.client.post(
                    model_url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=120.0,
                )

                if response.status_code == 429:
                    self._last_status_code = 429
                    if retry_on_rate_limit and attempt < len(RATE_LIMIT_RETRY_DELAYS):
                        delay = RATE_LIMIT_RETRY_DELAYS[attempt]
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = min(float(retry_after), 60.0)
                            except ValueError:
                                pass
                        logger.warning(
                            "⏳ HF Inference rate limited (429). Retrying in %ss... (attempt %s/%s)",
                            delay,
                            attempt + 1,
                            max_attempts,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    err_text = "Vision rate limit exceeded. Please try again later."
                    self._last_error = err_text
                    logger.error(
                        "❌ HF Inference vision rate limit exceeded after %s attempts",
                        attempt + 1,
                    )
                    return None

                if response.status_code != 200:
                    err_text = (response.text or "").strip()
                    try:
                        err_json = response.json()
                    except Exception:
                        err_json = None

                    if isinstance(err_json, dict):
                        payload_err = err_json.get("error") if isinstance(err_json.get("error"), dict) else err_json
                        err_message = payload_err.get("message") if isinstance(payload_err, dict) else None
                        if isinstance(err_message, str) and err_message.strip():
                            err_text = err_message.strip()

                        details: dict[str, Any] = {}
                        for key in (
                            "type",
                            "code",
                            "param",
                            "request_id",
                            "event_id",
                        ):
                            val = payload_err.get(key) if isinstance(payload_err, dict) else None
                            if val is not None:
                                details[key] = val
                        self._last_error = f"{err_text} | details={details}" if details else err_text
                    else:
                        self._last_error = err_text

                    if len(err_text) > 1000:
                        err_text = err_text[:1000] + "..."
                    self._last_status_code = response.status_code

                    logger.error(
                        "❌ HF Inference vision error %s (model=%s): %s",
                        response.status_code,
                        target_model,
                        err_text,
                    )
                    return None

                data = response.json()

                if isinstance(data, list) and len(data) > 0 and "generated_text" in data[0]:
                    content = data[0]["generated_text"]
                    logger.info(
                        "📸 HF Inference vision response from %s (%s chars)",
                        target_model,
                        len(content),
                    )
                    return content

                if isinstance(data, dict) and "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"]
                    logger.info(
                        "📸 HF Inference vision response from %s (%s chars)",
                        target_model,
                        len(content),
                    )
                    return content

                logger.warning("⚠️ HF Inference vision response unexpected format: %s", data)
                return None

            except httpx.TimeoutException:
                logger.error("❌ HF Inference vision request timed out (model=%s)", target_model)
                self._last_error = "Vision request timed out"
                return None

            except Exception as exc:
                logger.error("❌ HF Inference vision request failed: %s", exc, exc_info=True)
                self._last_error = str(exc)
                return None

        return None


hf_inference_service = HFInferenceService()
