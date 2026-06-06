from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import dataclass

import httpx

from src.config import settings
from src.services.github_models_service import github_models_service
from src.services.hermes_service import hermes_service
from src.services.nous_service import nous_inference_service
from src.services.openrouter_service import openrouter_service

try:
    from src.services.google_translation import google_translation_service
except Exception:  # pragma: no cover
    google_translation_service = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)


@dataclass
class AITranslationResult:
    text: str
    provider: str
    reason: str | None = None


class _LazyGoogleTranslationProvider:
    """Adapter that exposes TranslateResult-compatible interface."""
    _service_name = "google_cloud_translation"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self.last_status_code: int | None = None
        self.last_error: str | None = None

    def is_configured(self) -> bool:
        return bool(self._api_key and len(self._api_key.strip()) > 10)

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self.last_status_code, self.last_error, self._service_name

    async def chat_completion(self, messages, temperature=0.2, max_tokens=None, **_kwargs):
        if not self.is_configured():
            return None
        user_text = ""
        for message in messages or []:
            if message.get("role") == "user":
                user_text = message.get("content", "")
                break
        if not user_text:
            self.last_error = "Empty user message"
            return None

        source_lang, target_lang = "en", "th"
        for line in user_text.splitlines():
            if line.lower().startswith("translate from "):
                try:
                    parts = line.split(" to ", 1)[1].split(":", 1)
                    target_lang = parts[0].strip().lower() if parts else target_lang
                    source_lang = line.split(" from ", 1)[1].split(" to ", 1)[0].strip().lower() if " to " in line else source_lang
                except Exception:
                    pass
                break

        payload = {
            "contents": [{"parts": [{"text": user_text}]}],
            "mimeType": "text/plain",
        }
        url = (
            "https://translation.googleapis.com/language/translate/v2"
            if "translate/v2" not in str(self._api_key)
            else "https://translation.googleapis.com/language/translate/v2"
        )
        params = {
            "q": user_text,
            "source": source_lang if source_lang != "auto" else "auto",
            "target": target_lang,
            "format": "text",
            "key": self._api_key,
        }
        self.last_error = None
        self.last_status_code = None
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.post(url, data=params)
        except Exception as exc:
            self.last_error = str(exc)
            logger.error("Google translate request failed: %s", exc)
            return None

        self.last_status_code = response.status_code
        if response.status_code != 200:
            text = (response.text or "").strip()
            self.last_error = text or f"HTTP {response.status_code}"
            logger.error("Google translate error %s: %s", response.status_code, text[:200])
            return None

        try:
            data = response.json()
        except Exception as exc:
            self.last_error = f"Invalid JSON: {exc}"
            return None

        translated = ""
        try:
            translated = data["data"]["translations"][0]["translatedText"]
        except Exception as exc:
            self.last_error = f"Missing translation field: {exc}"
            logger.error("Google translate missing translation: %s", data)
            return None

        return translated or None


class _LazyGoogleTranslateProviderV2:
    """Thin adapter around google_translation.translate() when available."""
    _service_name = "google_cloud_translation_v2"

    def __init__(self, service) -> None:
        self._service = service
        self.last_status_code: int | None = None
        self.last_error: str | None = None

    def is_configured(self) -> bool:
        return getattr(self._service, "api_key", None) is not None and bool(self._service.api_key)

    def get_last_error(self) -> tuple[int | None, str | None, str | None]:
        return self.last_status_code, self.last_error, self._service_name

    async def chat_completion(self, messages, temperature=0.2, max_tokens=None, **_kwargs):
        if not self.is_configured():
            return None
        user_text = ""
        for message in messages or []:
            if message.get("role") == "user":
                user_text = message.get("content", "")
                break
        if not user_text:
            self.last_error = "Empty user message"
            return None
        source_lang, target_lang = "en", "th"
        for line in user_text.splitlines():
            if line.lower().startswith("translate from "):
                try:
                    parts = line.split(" to ", 1)[1].split(":", 1)
                    target_lang = parts[0].strip().lower() if parts else target_lang
                    source_lang = line.split(" from ", 1)[1].split(" to ", 1)[0].strip().lower() if " to " in line else source_lang
                except Exception:
                    pass
                break
        source_lang = None if source_lang == "auto" else source_lang
        try:
            result = self._service.translate(
                user_text,
                source_language=source_lang,
                target_language=target_lang,
                format_type="text",
            )
            if isinstance(result, str):
                return result.strip() or None
            text = getattr(result, "translated_text", None) or getattr(result, "translatedText", None)
            if isinstance(text, str) and text.strip():
                return text.strip()
            self.last_error = "Translation result empty"
            return None
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            message = str(exc)
            if status is None:
                message = str(exc)
            self.last_status_code = status
            self.last_error = message
            logger.exception("google_translation.translate failed")
            return None


class LibreTranslateProvider:
    """Thin wrapper so LibreTranslate can participate in the provider chain."""

    def __init__(self) -> None:
        self._last_status_code: int | None = None
        self._last_error: str | None = None
        self._last_model: str | None = None

    def _base_url(self) -> str:
        url = getattr(settings, "libretranslate_api_url", None)
        if not url:
            return ""
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
        source_lang, target_lang = "en", "th"
        for message in messages:
            if message.get("role") == "user":
                user_text = message.get("content", "")
                if "Translate from th to en:" in user_text:
                    source_lang, target_lang = "th", "en"
                elif "Translate from en to th:" in user_text:
                    source_lang, target_lang = "en", "th"
                break

        if not user_text:
            self._last_error = "No user content"
            return None

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
            logger.error("LibreTranslate request failed: %s", exc)
            return None

        self._last_status_code = response.status_code

        if response.status_code != 200:
            text = (response.text or "").strip()
            self._last_error = text or f"HTTP {response.status_code}"
            logger.error("LibreTranslate error %s: %s", response.status_code, text[:1000])
            return None

        try:
            data = response.json()
        except Exception as exc:
            self._last_error = f"Invalid JSON: {exc}"
            logger.error("LibreTranslate invalid JSON: %s", exc)
            return None

        translated = data.get("translatedText") if isinstance(data, dict) else None
        if not translated:
            self._last_error = "Missing translatedText"
            logger.warning("LibreTranslate response missing translatedText: %s", data)
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

    def _github_providers(self):
        if not self.github_models.is_configured():
            return []
        return [("github_models", self.github_models, self.github_models.chat_completion, {"temperature": 0.2})]

    def _google_providers(self):
        providers = []
        google_key = getattr(settings, "google_translate_api_key", None)
        if google_key:
            providers.append(_LazyGoogleTranslationProvider(api_key=google_key))
        if google_translation_service is not None:
            providers.append(_LazyGoogleTranslateProviderV2(service=google_translation_service))
        return providers

    def _openrouter_providers(self):
        providers = []
        if not self.openrouter.is_configured():
            return providers
        model = self.openrouter.model_for_translation() or self.openrouter.default_model
        if not model:
            return providers
        self.openrouter._last_model = model
        providers.append(
            ("openrouter", self.openrouter, self.openrouter.chat_completion, {"temperature": 0.2, "model": model})
        )
        if self.openrouter.default_model and self.openrouter.default_model != model:
            providers.append(
                (
                    "openrouter",
                    self.openrouter,
                    self.openrouter.chat_completion,
                    {"temperature": 0.2, "model": self.openrouter.default_model},
                )
            )
        return providers

    def _nous_providers(self):
        if not self.nous.is_configured():
            return []
        return [("nous", self.nous, self.nous.chat_completion, {"temperature": 0.2})]

    def _hermes_providers(self):
        if not self.hermes.is_configured():
            return []
        selected = settings.hermes_model or self.hermes.model or ""
        items = [(
            'hermes',
            self.hermes,
            self.hermes.chat_completion,
            {'temperature': 0.2, 'model': selected} if selected else {'temperature': 0.2},
        )]
        fallback = getattr(settings, 'hermes_fallback_model', None) or getattr(self, '_hermes_fallback_model', None)
        if fallback and fallback != selected:
            items.append(('hermes', self.hermes, self.hermes.chat_completion, {'temperature': 0.2, 'model': fallback}))
        return items

    def _libre_providers(self):
        if not self.libre_translate.is_configured():
            return []
        return [
            ("libretranslate", self.libre_translate, self.libre_translate.chat_completion, {"temperature": 0.2})
        ]

    def _build_provider_tuples(self):
        providers = []
        providers.extend([(p._service_name, p, p.chat_completion, {"temperature": 0.2}) for p in self._google_providers()])
        providers.extend(self._github_providers())
        providers.extend(self._nous_providers())
        providers.extend(self._openrouter_providers())
        providers.extend(self._hermes_providers())
        providers.extend(self._libre_providers())
        return providers

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
            providers = self._build_provider_tuples()

            provider_state = []
            for provider_name, provider_obj, _fn, _msgs, *_rest in providers:
                provider_state.append(
                    {
                        "name": provider_name,
                        "configured": provider_obj.is_configured(),
                        "before_error": provider_obj.get_last_error(),
                    }
                )
            logger.debug(
                "AI translation provider state attempt=%s source=%s target=%s providers=%s",
                attempt,
                source_lang,
                target_lang,
                provider_state,
            )

            for provider_name, provider_obj, fn, kwargs in providers:
                try:
                    if asyncio.iscoroutinefunction(fn):
                        result = await fn(messages, **kwargs)
                    else:
                        result = fn(messages, **kwargs)
                        if asyncio.iscoroutine(result):
                            result = await result
                except TypeError:
                    result = await fn(messages, **kwargs)

                if result:
                    result_text = result.strip()
                    if not result_text:
                        last_reason = f"{provider_name} returned empty content"
                        continue
                    return AITranslationResult(
                        text=result_text,
                        provider=provider_name,
                        reason=f"success after {attempt} attempt(s) - {type(provider_obj).__name__}",
                    )

                status, err, model = provider_obj.get_last_error()
                last_reason = f"{provider_name} failed ({type(provider_obj).__name__})"
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
