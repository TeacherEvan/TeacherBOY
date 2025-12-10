"""
Google Cloud Translation Service - Professional grade Thai-English translation.

This service provides high-quality translation using Google Cloud Translation API
with built-in retry logic, error handling, and performance optimizations.
"""

import logging
from typing import Optional, Tuple
import httpx
import asyncio
from functools import wraps

logger = logging.getLogger(__name__)


def with_retry(max_retries: int = 3, backoff_factor: float = 0.5):
    """
    Decorator for retrying async functions with exponential backoff.
    
    Args:
        max_retries: Maximum number of retry attempts
        backoff_factor: Multiplier for exponential backoff delay
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except (httpx.HTTPError, asyncio.TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = backoff_factor * (2 ** attempt)
                        logger.warning(
                            f"Translation attempt {attempt + 1} failed: {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(f"Translation failed after {max_retries} attempts: {e}")
            raise last_exception
        return wrapper
    return decorator


class GoogleTranslationService:
    """
    Google Cloud Translation API service for high-quality Thai-English translation.
    
    To use:
    1. Create Google Cloud project: https://console.cloud.google.com/
    2. Enable Cloud Translation API
    3. Create API key
    4. Add GOOGLE_TRANSLATE_API_KEY to .env
    """
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.api_url = "https://translation.googleapis.com/language/translate/v2"
        self.client: Optional[httpx.AsyncClient] = None
    
    def set_client(self, client: httpx.AsyncClient):
        """Set the shared HTTP client."""
        self.client = client
    
    def is_configured(self) -> bool:
        """Check if Google Translate API is properly configured."""
        return bool(self.api_key)
    
    @with_retry(max_retries=3, backoff_factor=0.5)
    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None
    ) -> Optional[str]:
        """
        Translate text using Google Cloud Translation API with automatic retry.
        
        This method implements exponential backoff retry logic for resilient
        translation in production environments.
        
        Args:
            text: Text to translate (max 30,000 characters)
            target_lang: Target language code ('th' or 'en')
            source_lang: Source language (optional, auto-detected if None)
        
        Returns:
            Translated text or None if translation fails after all retries
            
        Raises:
            ValueError: If text exceeds maximum length
        """
        if not self.is_configured():
            logger.warning("⚠️ Google Translate API key not configured")
            return None
        
        # Validate input length (Google API limit is 30k characters)
        if len(text) > 30000:
            raise ValueError(f"Text too long ({len(text)} chars). Maximum is 30,000 characters.")
        
        params = {
            "q": text,
            "target": target_lang,
            "key": self.api_key,
            "format": "text"
        }
        
        if source_lang:
            params["source"] = source_lang
        
        if self.client:
            response = await self.client.post(self.api_url, params=params)
        else:
            # Fallback client for tests or non-initialized scenarios
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(self.api_url, params=params)
        
        response.raise_for_status()
        data = response.json()
        
        if "data" in data and "translations" in data["data"]:
            translated = data["data"]["translations"][0]["translatedText"]
            detected_lang = data["data"]["translations"][0].get("detectedSourceLanguage", "")
            
            logger.info(
                f"✅ Google Translate success: {source_lang or detected_lang} → {target_lang} "
                f"({len(text)} → {len(translated)} chars)"
            )
            return translated
        
        logger.error(f"❌ Unexpected Google Translate response format: {data}")
        return None
    
    async def auto_translate(self, text: str) -> Optional[str]:
        """
        Auto-detect language and translate Thai ↔ English.
        
        This method intelligently detects Thai characters and translates
        to/from English accordingly.
        
        Args:
            text: Text to translate
            
        Returns:
            Translated text, or None if translation fails
        """
        # Efficient Thai character detection
        has_thai = any('\u0E00' <= char <= '\u0E7F' for char in text)
        
        if has_thai:
            # Thai → English
            logger.debug(f"Detected Thai text, translating to English")
            return await self.translate(text, target_lang="en", source_lang="th")
        else:
            # English → Thai
            logger.debug(f"Detected English text, translating to Thai")
            return await self.translate(text, target_lang="th", source_lang="en")


# Singleton instance (optional, requires API key in config)
google_translation_service = GoogleTranslationService()
