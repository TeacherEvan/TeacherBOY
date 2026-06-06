"""
Optional centralized fallback dispatcher for TeacherBOY.

Prefers configured providers in priority order. Routing in the active code path
is driven by LLMAgent; this module remains available for call sites that want
priority-based fallback without duplicating the loop.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Union

from src.config import settings
from src.services.github_models_service import github_models_service
from src.services.openrouter_service import openrouter_service
from src.services.hermes_service import hermes_service
from src.services.nous_service import nous_inference_service

logger = logging.getLogger(__name__)

VisionMessages = List[Dict[str, Any]]


async def _run_one_vision_provider(
    *,
    provider: str,
    messages: VisionMessages,
    model: Optional[str],
    temperature: float,
    max_tokens: Optional[int],
) -> Optional[str]:
    wrapper = {
        "hermes": lambda: hermes_service.is_vision_configured(),
        "openrouter": lambda: openrouter_service.is_configured(),
        "github": lambda: github_models_service.is_configured(),
    }.get(provider)

    if not wrapper or not wrapper():
        return None

    try:
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
        if provider == "github":
            return await github_models_service.chat_completion_with_vision(
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
    messages: List[Dict[str, str]],
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    priority = settings.get_llm_provider_priority()

    for provider in priority:
        if provider == "github" and github_models_service.is_configured():
            try:
                result = await github_models_service.chat_completion(
                    messages=messages,
                    model=settings.github_models_default_model or None,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    retry_on_rate_limit=False,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning("GitHub Models fallback failed: %s", exc)
            continue

        if provider == "openrouter" and openrouter_service.is_configured():
            try:
                result = await openrouter_service.chat_completion(
                    messages=messages,
                    model=settings.openrouter_default_model or None,
                    temperature=temperature,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning("OpenRouter fallback failed: %s", exc)
            continue

        if provider == "hermes" and hermes_service.is_configured():
            try:
                result = await hermes_service.chat_completion(
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                )
                if result:
                    return result
            except Exception as exc:
                logger.warning("Hermes fallback failed: %s", exc)

    return None


async def chat_completion_with_vision_fallback(
    messages: VisionMessages,
    *,
    model: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
) -> Optional[str]:
    """
    Provider-priority vision completion.

    Tries vision-capable providers in configured priority order. Currently this
    assumes Hermes, then OpenRouter, then GitHub Models if they report
    configured/vision-configured state. A provider can skip vision by leaving
    `chat_completion_with_vision(...)` unimplemented or returning None.
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
