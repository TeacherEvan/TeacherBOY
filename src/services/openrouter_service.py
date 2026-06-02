"""
OpenRouter Service - LLM access via OpenRouter API.
"""

import logging
import httpx
from typing import List, Dict, Optional, Any
from src.config import settings

logger = logging.getLogger(__name__)


class OpenRouterService:
    """Service for interacting with OpenRouter API."""

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        """
        Initialize OpenRouter service.

        Args:
            http_client: Shared async HTTP client
        """
        self.client = http_client
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"
        self.api_key = settings.openrouter_api_key
        self.default_model = settings.openrouter_default_model

        # Best-effort diagnostics for the last request (useful for user-facing errors).
        self._last_error: Optional[str] = None
        self._last_status_code: Optional[int] = None
        self._last_model: Optional[str] = None

    def get_last_error(self) -> tuple[Optional[int], Optional[str], Optional[str]]:
        """Return (status_code, error_text, model) from the last request."""
        return self._last_status_code, self._last_error, self._last_model

    def set_client(self, client: httpx.AsyncClient):
        """Set the shared HTTP client."""
        self.client = client

    def is_configured(self) -> bool:
        """Check if OpenRouter is configured."""
        return settings.is_openrouter_configured()

    async def chat_completion(
        self, 
        messages: List[Dict[str, str]], 
        model: Optional[str] = None,
        temperature: float = 0.7
    ) -> Optional[str]:
        """
        Get chat completion from OpenRouter.

        Args:
            messages: List of message dicts (role, content)
            model: Model ID (optional, uses default if None)
            temperature: Sampling temperature

        Returns:
            Response text or None if failed
        """
        if not self.is_configured():
            logger.warning("⚠️ OpenRouter API key not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for OpenRouter")
            return None

        target_model = model or self.default_model

        # Reset diagnostics
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        try:
            headers = {
                "Authorization": f"Bearer {settings.openrouter_api_key}",
                "HTTP-Referer": "https://github.com/TeacherEvan/TeacherBOY",  # Optional (OpenRouter app attribution)
                "X-Title": "Ms. Green",  # Optional (OpenRouter app attribution)
                "Content-Type": "application/json",
            }
            
            payload = {
                "model": target_model,
                "messages": messages,
                "temperature": temperature,
            }

            response = await self.client.post(
                self.api_url, headers=headers, json=payload, timeout=30.0
            )
            
            if response.status_code != 200:
                # Keep a truncated copy of the error for user-facing diagnostics.
                err_text = (response.text or "").strip()
                if len(err_text) > 1000:
                    err_text = err_text[:1000] + "..."
                self._last_status_code = response.status_code
                self._last_error = err_text

                logger.error(
                    f"❌ OpenRouter error {response.status_code} (model={target_model}): {err_text}"
                )
                return None
                
            data = response.json()
            
            if "choices" in data and len(data["choices"]) > 0:
                content = data["choices"][0]["message"]["content"]
                logger.info(f"🤖 OpenRouter response from {target_model} ({len(content)} chars)")
                return content
            
            logger.warning(f"⚠️ OpenRouter response missing choices: {data}")
            return None

        except Exception as e:
            logger.error(f"❌ OpenRouter request failed: {e}", exc_info=True)
            return None


# Singleton instance
openrouter_service = OpenRouterService()
