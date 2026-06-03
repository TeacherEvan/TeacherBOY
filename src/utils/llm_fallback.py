"""Optional centralized fallback dispatcher for TeacherBOY.

Prefers configured providers in priority order. Routing in the active code path
is driven by LLMAgent; this module remains available for call sites that want
priority-based fallback without duplicating the loop.
"""

from __future__ import annotations

import logging
from typing import List, Dict, Optional

from src.config import settings
from src.services.github_models_service import github_models_service
from src.services.openrouter_service import openrouter_service
from src.services.hermes_service import hermes_service

logger = logging.getLogger(__name__)


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

        elif provider == "openrouter" and openrouter_service.is_configured():
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

        elif provider == "hermes" and hermes_service.is_configured():
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
