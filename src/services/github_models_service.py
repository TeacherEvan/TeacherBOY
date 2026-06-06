"""
GitHub Models Service - Free AI inference via GitHub Models API.

This service provides access to AI models (GPT-4o, Grok, DeepSeek, etc.)
using your GitHub Personal Access Token (PAT) with models:read scope.

API Documentation: https://docs.github.com/en/github-models
Endpoint: https://models.github.ai/inference/chat/completions

Available free-tier models include:
- openai/gpt-4o, openai/gpt-4o-mini, openai/gpt-4.1
- xai/grok-3, xai/grok-3-mini
- deepseek/deepseek-r1
- meta/llama-3.3-70b-instruct
- And more at https://github.com/marketplace/models
"""

import asyncio
import logging
from typing import Any

import httpx

from src.config import settings

logger = logging.getLogger(__name__)

# Rate limit tiers (requests per minute / requests per day)
# Low tier models: 15 rpm / 150 rpd
# High tier models: 10 rpm / 50 rpd
# Grok-3: 1 rpm / 15 rpd
RATE_LIMIT_RETRY_DELAYS = [1.0, 2.0, 5.0, 10.0]  # Exponential backoff delays


class GitHubModelsService:
    """
    Service for interacting with GitHub Models API.

    Uses GitHub PAT for authentication. Create a token at:
    https://github.com/settings/tokens with 'models:read' scope.
    """

    def __init__(self, http_client: httpx.AsyncClient | None = None) -> None:
        self.client = http_client
        self.api_url = "https://models.github.ai/inference/chat/completions"
        self.api_version = "2022-11-28"

        self._last_error: str | None = None
        self._last_status_code: int | None = None
        self._last_model: str | None = None

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    def set_client(self, client: httpx.AsyncClient) -> None:
        self.client = client

    def is_configured(self) -> bool:
        return settings.is_github_models_configured()

    def is_vision_configured(self) -> bool:
        return self.is_configured()

    def _get_headers(self) -> dict[str, str]:
        if not settings.github_models_pat:
            return {}
        return {
            "Authorization": f"Bearer {settings.github_models_pat}",
            "X-GitHub-Api-Version": self.api_version,
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        temperature: float = 0.9,
        max_tokens: int | None = None,
        retry_on_rate_limit: bool = True,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ GitHub Models PAT not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for GitHub Models")
            return None

        target_model = model or settings.github_models_default_model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }

        if max_tokens:
            payload["max_tokens"] = max_tokens

        attempt = 0
        max_attempts = len(RATE_LIMIT_RETRY_DELAYS) + 1 if retry_on_rate_limit else 1
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        while attempt < max_attempts:
            try:
                response = await self.client.post(
                    self.api_url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=60.0,
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
                            "⏳ GitHub Models rate limited (429). Retrying in %ss... (attempt %s/%s)",
                            delay,
                            attempt + 1,
                            max_attempts,
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    err_text = "Rate limit exceeded. Please try again later."
                    self._last_error = err_text
                    logger.error("❌ GitHub Models rate limit exceeded after %s attempts", attempt + 1)
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
                        "❌ GitHub Models error %s (model=%s): %s",
                        response.status_code,
                        target_model,
                        err_text,
                    )
                    return None

                data = response.json()

                if "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"]
                    logger.info(
                        "🤖 GitHub Models response from %s (%s chars)",
                        target_model,
                        len(content),
                    )
                    return content

                logger.warning("⚠️ GitHub Models response missing choices: %s", data)
                return None

            except httpx.TimeoutException:
                logger.error("❌ GitHub Models request timed out (model=%s)", target_model)
                self._last_error = "Request timed out"
                return None

            except Exception as exc:
                logger.error("❌ GitHub Models request failed: %s", exc, exc_info=True)
                self._last_error = str(exc)
                return None

        return None

    async def chat_completion_with_vision(
        self,
        messages: list[dict[str, Any]],
        model: str | None = None,
        temperature: float = 0.9,
        max_tokens: int | None = 4096,
        retry_on_rate_limit: bool = True,
    ) -> str | None:
        if not self.is_configured():
            logger.warning("⚠️ GitHub Models PAT not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for GitHub Models")
            return None

        target_model = model or "openai/gpt-4o"
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        payload: dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        attempt = 0
        max_attempts = len(RATE_LIMIT_RETRY_DELAYS) + 1 if retry_on_rate_limit else 1

        while attempt < max_attempts:
            try:
                logger.info("📸 Sending vision request to %s...", target_model)

                response = await self.client.post(
                    self.api_url,
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
                            "⏳ GitHub Models vision rate limited (429). Retrying in %ss... (attempt %s/%s)",
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
                        "❌ GitHub Models vision rate limit exceeded after %s attempts",
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
                        "❌ GitHub Models vision error %s (model=%s): %s",
                        response.status_code,
                        target_model,
                        err_text,
                    )
                    return None

                data = response.json()

                if "choices" in data and data["choices"]:
                    content = data["choices"][0]["message"]["content"]
                    logger.info(
                        "📸 GitHub Models vision response from %s (%s chars)",
                        target_model,
                        len(content),
                    )
                    return content

                logger.warning("⚠️ GitHub Models vision response missing choices: %s", data)
                return None

            except httpx.TimeoutException:
                logger.error("❌ GitHub Models vision request timed out (model=%s)", target_model)
                self._last_error = "Vision request timed out"
                return None

            except Exception as exc:
                logger.error("❌ GitHub Models vision request failed: %s", exc, exc_info=True)
                self._last_error = str(exc)
                return None

        return None

    async def list_models(self) -> list[dict[str, Any]] | None:
        if not self.is_configured():
            return None

        if not self.client:
            return None

        try:
            response = await self.client.get(
                "https://models.github.ai/catalog",
                headers=self._get_headers(),
                timeout=30.0,
            )

            if response.status_code == 200:
                return response.json()

            logger.warning("⚠️ Failed to list GitHub Models: %s", response.status_code)
            return None

        except Exception as exc:
            logger.error("❌ Failed to list GitHub Models: %s", exc)
            return None


github_models_service = GitHubModelsService()
