"""Optional centralized fallback dispatcher for TeacherBOY.

Prefers configured providers in priority order. Routing in the active code path
is driven by LLMAgent; this module remains available for call sites that want
priority-based fallback without duplicating the loop.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from src.config import settings
from src.services.gemini_service import gemini_service
from src.services.hermes_service import hermes_service
from src.services.hf_inference_service import hf_inference_service
from src.services.openrouter_service import openrouter_service

logger = logging.getLogger(__name__)

# Circuit breaker state: tracks consecutive failures per provider
_provider_failure_counts: dict[str, int] = {}
# Circuit breaker timestamps: when a provider was last opened (unblocked)
_provider_circuit_open_until: dict[str, float] = {}

# Circuit breaker configuration
_CIRCUIT_BREAKER_THRESHOLD = 3  # consecutive failures before opening circuit
_CIRCUIT_BREAKER_COOLDOWN_SECONDS = 300  # 5 minutes
_TIMEOUT_SECONDS = 10  # per provider call timeout
_RETRY_BACKOFF_SECONDS = [2, 4]  # exponential backoff: 2s, then 4s


def _is_circuit_open(provider: str) -> bool:
    """Check if circuit breaker is open for a provider."""
    open_until = _provider_circuit_open_until.get(provider, 0)
    if time.time() < open_until:
        return True
    # Circuit cooldown expired, reset failure count and allow retry
    # Only reset if circuit was actually open (key exists in _provider_circuit_open_until)
    if provider in _provider_circuit_open_until:
        _provider_failure_counts[provider] = 0
        del _provider_circuit_open_until[provider]
    return False


def _record_success(provider: str) -> None:
    """Record a successful call, resetting failure count."""
    _provider_failure_counts[provider] = 0
    if provider in _provider_circuit_open_until:
        del _provider_circuit_open_until[provider]


def _record_failure(provider: str) -> None:
    """Record a failure, potentially opening the circuit breaker."""
    count = _provider_failure_counts.get(provider, 0) + 1
    _provider_failure_counts[provider] = count
    if count >= _CIRCUIT_BREAKER_THRESHOLD:
        _provider_circuit_open_until[provider] = time.time() + _CIRCUIT_BREAKER_COOLDOWN_SECONDS
        logger.warning(
            "Circuit breaker OPENED for %s after %d consecutive failures. Provider blocked for %d seconds.",
            provider,
            count,
            _CIRCUIT_BREAKER_COOLDOWN_SECONDS,
        )


async def _call_provider_with_resilience(
    provider: str,
    call_fn: Callable[[], Awaitable[str | None]],
) -> str | None:
    """
    Call a provider with timeout, retry (exponential backoff), and circuit breaker.
    Returns the result on success, None on failure (after retries exhausted).
    """
    if _is_circuit_open(provider):
        logger.info("Skipping %s: circuit breaker is open", provider)
        return None

    last_exception = None
    start_time = time.time()

    # Initial attempt + retries (len(_RETRY_BACKOFF_SECONDS) retries = 1 retry with 2 backoffs)
    for attempt in range(len(_RETRY_BACKOFF_SECONDS) + 1):
        attempt_start = time.time()
        try:
            # Apply 10-second timeout per call
            result = await asyncio.wait_for(call_fn(), timeout=_TIMEOUT_SECONDS)
            latency = time.time() - attempt_start
            total_latency = time.time() - start_time

            if result:
                _record_success(provider)
                logger.info(
                    "%s succeeded (attempt %d/%d, latency: %.2fs, total: %.2fs)",
                    provider,
                    attempt + 1,
                    len(_RETRY_BACKOFF_SECONDS) + 1,
                    latency,
                    total_latency,
                )
                return result
            else:
                logger.warning(
                    "%s returned empty result (attempt %d/%d)", provider, attempt + 1, len(_RETRY_BACKOFF_SECONDS) + 1
                )

        except TimeoutError:
            latency = time.time() - attempt_start
            last_exception = TimeoutError(f"{provider} timed out after {_TIMEOUT_SECONDS}s")
            logger.warning(
                "%s timed out after %.2fs (attempt %d/%d)", provider, latency, attempt + 1, len(_RETRY_BACKOFF_SECONDS) + 1
            )

        except Exception as exc:
            latency = time.time() - attempt_start
            last_exception = exc
            logger.warning(
                "%s failed after %.2fs (attempt %d/%d): %s",
                provider,
                latency,
                attempt + 1,
                len(_RETRY_BACKOFF_SECONDS) + 1,
                exc,
            )

        # If not the last attempt, wait before retry with exponential backoff
        if attempt < len(_RETRY_BACKOFF_SECONDS):
            backoff = _RETRY_BACKOFF_SECONDS[attempt]
            logger.info("Retrying %s in %ds (backoff)", provider, backoff)
            await asyncio.sleep(backoff)

    # All attempts failed
    total_latency = time.time() - start_time
    _record_failure(provider)
    logger.error(
        "%s failed after %d attempts (total latency: %.2fs). Last error: %s",
        provider,
        len(_RETRY_BACKOFF_SECONDS) + 1,
        total_latency,
        last_exception,
    )
    return None


VisionMessages = list[dict[str, Any]]


async def _run_one_vision_provider(
    *,
    provider: str,
    messages: VisionMessages,
    model: str | None,
    temperature: float,
    max_tokens: int | None,
) -> str | None:
    wrapper = {
        "gemini": lambda: gemini_service.is_vision_configured(),
        "hermes": lambda: hermes_service.is_vision_configured(),
        "openrouter": lambda: openrouter_service.is_configured(),
        "hf_inference": lambda: hf_inference_service.is_configured(),
    }.get(provider)

    if not wrapper or not wrapper():
        return None

    try:
        if provider == "gemini":
            return await gemini_service.chat_completion_with_vision(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == "hermes":
            return await hermes_service.chat_completion_with_vision(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == "openrouter":
            return await openrouter_service.chat_completion_with_vision(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        if provider == "hf_inference":
            return await hf_inference_service.chat_completion_with_vision(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                retry_on_rate_limit=False,
            )
    except Exception as exc:
        logger.warning("%s vision fallback failed: %s", provider.capitalize(), exc)

    return None


async def chat_completion_with_fallback(
    messages: list[dict[str, str]],
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str | None:
    priority = settings.get_llm_provider_priority()

    for provider in priority:
        if provider == "gemini" and gemini_service.is_configured():
            result = await _call_provider_with_resilience(
                "gemini",
                lambda: gemini_service.chat_completion(
                    messages=messages,
                    model=settings.gemini_model or None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
            if result:
                return result
            continue

        if provider == "ollama" and settings.ollama_enabled:
            from src.services.ollama_service import ollama_service

            result = await _call_provider_with_resilience(
                "ollama",
                lambda: ollama_service.chat_completion(
                    messages=messages,
                    model=settings.ollama_default_model or None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
            if result:
                return result
            continue

        if provider == "openrouter" and openrouter_service.is_configured():
            result = await _call_provider_with_resilience(
                "openrouter",
                lambda: openrouter_service.chat_completion(
                    messages=messages,
                    model=settings.openrouter_default_model or None,
                    temperature=temperature,
                ),
            )
            if result:
                return result
            continue

        if provider == "hermes" and hermes_service.is_configured():
            result = await _call_provider_with_resilience(
                "hermes",
                lambda: hermes_service.chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                ),
            )
            if result:
                return result

    return None


async def chat_completion_with_vision_fallback(
    messages: VisionMessages,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str | None:
    """
    Provider-priority vision completion.

    Tries vision-capable providers in the configured priority order
    (`settings.get_llm_provider_priority()`, default: Gemini first). A provider
    can skip vision by leaving `chat_completion_with_vision(...)` unimplemented
    or returning None.
    """
    priority = settings.get_llm_provider_priority()

    for provider in priority:
        result = await _run_one_vision_provider(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if result:
            return result

    return None
