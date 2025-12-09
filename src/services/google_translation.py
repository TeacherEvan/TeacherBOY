"""Google Cloud Translation Service - Professional grade Thai-English translation."""

import logging
from typing import Optional, Tuple
import httpx

logger = logging.getLogger(__name__)


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
    
    async def translate(
        self,
        text: str,
        target_lang: str,
        source_lang: Optional[str] = None
    ) -> Optional[str]:
        """
        Translate text using Google Cloud Translation API.
        
        Args:
            text: Text to translate
            target_lang: Target language code ('th' or 'en')
            source_lang: Source language (optional, auto-detected if None)
        
        Returns:
            Translated text or None if translation fails
        """
        if not self.is_configured():
            logger.warning("Google Translate API key not configured")
            return None
        
        try:
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
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(self.api_url, params=params)
            
            response.raise_for_status()
            data = response.json()
            
            if "data" in data and "translations" in data["data"]:
                translated = data["data"]["translations"][0]["translatedText"]
                detected_lang = data["data"]["translations"][0].get("detectedSourceLanguage", "")
                
                logger.info(f"Google Translate: {source_lang or detected_lang} -> {target_lang}")
                return translated
            
            logger.error(f"Unexpected Google Translate response format: {data}")
            return None
                
        except httpx.HTTPError as e:
            logger.error(f"HTTP error during Google translation: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Google translation error: {str(e)}")
            return None
    
    async def auto_translate(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Auto-detect language and translate Thai to English or English to Thai.
        
        Args:
            text: Text to translate
            
        Returns:
            Tuple of (translated_text, detected_language)
        """
        # Detect if Thai (simple check for Thai characters)
        has_thai = any('\u0E00' <= char <= '\u0E7F' for char in text)
        
        if has_thai:
            # Thai -> English
            translated = await self.translate(text, target_lang="en", source_lang="th")
            return translated, "th"
        else:
            # English -> Thai
            translated = await self.translate(text, target_lang="th", source_lang="en")
            return translated, "en"


# Singleton instance (optional, requires API key in config)
google_translation_service = GoogleTranslationService()
