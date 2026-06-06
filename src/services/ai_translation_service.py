from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

import httpx

from src.config import settings
from src.services.github_models_service import github_models_service
from src.services.hermes_service import hermes_service
from src.services.nous_service import nous_inference_service
from src.services.openrouter_service import openrouter_service

logger = logging.getLogger(__name__)


@dataclass
class AITranslationResult:
    text: str
    provider: str
    reason: str | None = None


class LibreTranslateProvider:
    """Thin wrapper so LibreTranslate can participate in the provider chain."""

    def __init__(self) -> None:
        self._last_status_code: int | None = None
        self._last_error: str | None = None
        self._last_model: str | None = None

    def _base_url(self) -> str:
        url = getattr(settings, "libretranslate_api_url", None)
        if not url:
            return "https://libretranslate.de/translate"
        return url.rstrip("/")

    def _api_key(self) -> str | None:
        return getattr(settings, "libretranslate_api_key", None)

    def _headers(self) -> dict:
        headers = {"Content-Type": "application/json"}
        api_key = self._api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return headers

    def is_configured(self) -> bool:
        return bool(self._base_url())

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self._last_status_code, self._last_error, self._last_model

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        retry_on_rate_limit: bool = True,
    ) -> str | None:
        if not self.is_configured():
            return None

        user_text = ""
        for message in messages:
            if message.get("role") == "user":
                user_text = message.get("content", "")
                break

        if not user_text:
            self._last_error = "No user content"
            return None

        source_lang = "en"
        target_lang = "th"
        for message in messages:
            if message.get("role") == "user":
                content = message.get("content", "")
                if "Translate from th to en:" in content:
                    source_lang, target_lang = "th", "en"
                elif "Translate from en to th:" in content:
                    source_lang, target_lang = "en", "th"
                break

        payload: dict = {
            "q": user_text,
            "source": source_lang,
            "target": target_lang,
            "format": "text",
        }
        api_key = self._api_key()
        if api_key:
            payload["api_key"] = api_key

        url = f"{self._base_url()}"
        self._last_error = None
        self._last_status_code = None
        self._last_model = "libretranslate"

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
            ) as client:
                response = await client.post(
                    url,
                    headers=self._headers(),
                    json=payload,
                )
        except Exception as exc:
            self._last_error = str(exc)
            logger.error("❌ LibreTranslate request failed: %s", exc)
            return None

        self._last_status_code = response.status_code

        if response.status_code != 200:
            text = (response.text or "").strip()
            self._last_error = text or f"HTTP {response.status_code}"
            logger.error("❌ LibreTranslate error %s: %s", response.status_code, text[:1000])
            return None

        try:
            data = response.json()
        except Exception as exc:
            self._last_error = f"Invalid JSON: {exc}"
            logger.error("❌ LibreTranslate invalid JSON: %s", exc)
            return None

        translated = data.get("translatedText") if isinstance(data, dict) else None
        if not translated:
            self._last_error = "Missing translatedText"
            logger.warning("⚠️ LibreTranslate response missing translatedText: %s", data)
            return None

        return translated


class AITranslationService:
    MIN_TEXT_LENGTH = 30

    def __init__(
        self,
        github_models=github_models_service,
        openrouter=openrouter_service,
        libre_translate: LibreTranslateProvider | None = None,
        hermes=hermes_service,
        nous=nous_inference_service,
    ):
        self.github_models = github_models
        self.openrouter = openrouter
        self.libre_translate = libre_translate or LibreTranslateProvider()
        self.hermes = hermes
        self.nous = nous

    async def translate(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> AITranslationResult | None:
        messages = self._build_messages(text, source_lang, target_lang)
        attempt = 0
        max_attempts = 5
        last_reason = "No provider attempted"

        while attempt < max_attempts:
            attempt += 1

            g = self.github_models
            o = self.openrouter
            libre = self.libre_translate
            n = self.nous
            providers = []

            # Nous Portal (free) — PRIMARY
            if n.is_configured():
                providers.append(("nous", n, n.chat_completion, messages, {"temperature": 0.2}))

            # GitHub Models
            if g.is_configured():
                providers.append(("github_models", g, g.chat_completion, messages, {"temperature": 0.2}))

            # OpenRouter
            if o.is_configured():
                providers.append(("openrouter", o, o.chat_completion, messages, {"temperature": 0.2}))

            # LibreTranslate
            if libre.is_configured():
                providers.append(("libretranslate", libre, libre.chat_completion, messages, {"temperature": 0.2}))

            # Hermes fallback
            h = self.hermes
            if h.is_configured():
                providers.append(("hermes", h, h.chat_completion, messages, {"temperature": 0.2}))

            for provider_name, provider_obj, fn, msgs, kwargs in providers:
                try:
                    result = await fn(msgs, **kwargs)
                except Exception as exc:
                    last_reason = f"{provider_name} raised {type(exc).__name__}: {exc}"
                    logger.error("AI translation provider error (%s): %s", provider_name, exc)
                    continue

                if result:
                    result_text = result.strip()
                    if not result_text:
                        last_reason = f"{provider_name} returned empty content"
                        continue
                    return AITranslationResult(
                        text=result_text,
                        provider=provider_name,
                        reason=f"success after {attempt} attempt(s) - {provider_obj.__class__.__name__}",
                    )

                status, err, model = provider_obj.get_last_error()
                last_reason = f"{provider_name} failed ({provider_obj.__class__.__name__})"
                if status is not None:
                    last_reason += f" status={status}"
                if model:
                    last_reason += f" model={model}"
                if err:
                    last_reason += f" error={err}"

            await asyncio.sleep(min(0.5 * (2 ** (attempt - 1)), 2))

        logger.warning(
            "AI translation unavailable for %s -> %s: %s",
            source_lang,
            target_lang,
            last_reason,
        )
        return None

    def _build_messages(
        self,
        text: str,
        source_lang: str,
        target_lang: str,
    ) -> list[dict[str, str]]:
        return [
            {
                "role": "system",
                "content": (
                    "You are a translation engine. Translate faithfully and only return the translation. "
                    "Preserve line breaks, punctuation, parenthesized text, emojis, and URLs exactly. "
                    "Do not explain."
                ),
            },
            {
                "role": "user",
                "content": f"Translate from {source_lang} to {target_lang}:\n\n{text}",
            },
        ]


ai_translation_service = AITranslationService()
