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

import logging
import asyncio
import httpx
from typing import List, Dict, Optional, Any
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

    def __init__(self, http_client: Optional[httpx.AsyncClient] = None):
        """
        Initialize GitHub Models service.

        Args:
            http_client: Shared async HTTP client
        """
        self.client = http_client
        self.api_url = "https://models.github.ai/inference/chat/completions"
        self.api_version = "2022-11-28"
        
        # Diagnostics for last request (useful for user-facing errors)
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
        """Check if GitHub Models is configured with a PAT."""
        return settings.is_github_models_configured()

    def _get_headers(self) -> Dict[str, str]:
        """Build request headers with authentication."""
        return {
            "Authorization": f"Bearer {settings.github_models_pat}",
            "X-GitHub-Api-Version": self.api_version,
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
        }

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        retry_on_rate_limit: bool = True,
    ) -> Optional[str]:
        """
        Get chat completion from GitHub Models API.

        Args:
            messages: List of message dicts (role, content)
            model: Model ID (e.g., "openai/gpt-4o"). Uses default if None.
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens in response (optional)
            retry_on_rate_limit: Whether to retry on 429 errors

        Returns:
            Response text or None if failed
        """
        if not self.is_configured():
            logger.warning("⚠️ GitHub Models PAT not configured")
            return None

        if not self.client:
            logger.warning("⚠️ HTTP client not available for GitHub Models")
            return None

        target_model = model or settings.github_models_default_model

        # Reset diagnostics
        self._last_error = None
        self._last_status_code = None
        self._last_model = target_model

        # Build payload (OpenAI-compatible format)
        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": messages,
            "temperature": temperature,
        }
        
        if max_tokens:
            payload["max_tokens"] = max_tokens

        # Attempt request with optional retry on rate limit
        attempt = 0
        max_attempts = len(RATE_LIMIT_RETRY_DELAYS) + 1 if retry_on_rate_limit else 1

        while attempt < max_attempts:
            try:
                response = await self.client.post(
                    self.api_url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=60.0,  # GitHub Models can be slower
                )

                # Handle rate limiting (429)
                if response.status_code == 429:
                    self._last_status_code = 429
                    
                    if retry_on_rate_limit and attempt < len(RATE_LIMIT_RETRY_DELAYS):
                        delay = RATE_LIMIT_RETRY_DELAYS[attempt]
                        
                        # Check for Retry-After header
                        retry_after = response.headers.get("Retry-After")
                        if retry_after:
                            try:
                                delay = min(float(retry_after), 60.0)  # Cap at 60s
                            except ValueError:
                                pass
                        
                        logger.warning(
                            f"⏳ GitHub Models rate limited (429). "
                            f"Retrying in {delay}s... (attempt {attempt + 1}/{max_attempts})"
                        )
                        await asyncio.sleep(delay)
                        attempt += 1
                        continue
                    else:
                        err_text = "Rate limit exceeded. Please try again later."
                        self._last_error = err_text
                        logger.error(f"❌ GitHub Models rate limit exceeded after {attempt + 1} attempts")
                        return None

                # Handle other errors
                if response.status_code != 200:
                    err_text = (response.text or "").strip()
                    if len(err_text) > 1000:
                        err_text = err_text[:1000] + "..."
                    self._last_status_code = response.status_code
                    self._last_error = err_text

                    logger.error(
                        f"❌ GitHub Models error {response.status_code} "
                        f"(model={target_model}): {err_text}"
                    )
                    return None

                # Parse successful response
                data = response.json()

                if "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0]["message"]["content"]
                    
                    # Log usage stats if available
                    usage = data.get("usage", {})
                    prompt_tokens = usage.get("prompt_tokens", "?")
                    completion_tokens = usage.get("completion_tokens", "?")
                    
                    logger.info(
                        f"🤖 GitHub Models response from {target_model} "
                        f"({len(content)} chars, {prompt_tokens}+{completion_tokens} tokens)"
                    )
                    return content

                logger.warning(f"⚠️ GitHub Models response missing choices: {data}")
                return None

            except httpx.TimeoutException:
                logger.error(f"❌ GitHub Models request timed out (model={target_model})")
                self._last_error = "Request timed out"
                return None

            except Exception as e:
                logger.error(f"❌ GitHub Models request failed: {e}", exc_info=True)
                self._last_error = str(e)
                return None

        return None

    async def list_models(self) -> Optional[List[Dict[str, Any]]]:
        """
        List available models from GitHub Models catalog.
        
        Returns:
            List of model info dicts or None if failed
        """
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
            
            logger.warning(f"⚠️ Failed to list GitHub Models: {response.status_code}")
            return None
            
        except Exception as e:
            logger.error(f"❌ Failed to list GitHub Models: {e}")
            return None


# Singleton instance
github_models_service = GitHubModelsService()
