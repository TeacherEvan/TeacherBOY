"""News data retrieval service with caching for weather and news APIs."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import httpx

logger = logging.getLogger(__name__)


class DataCache:
    """Simple TTL cache for weather and news data."""

    def __init__(self):
        """Initialize cache with TTL settings."""
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        self._ttl_seconds = {
            "weather": 1800,  # 30 minutes
            "news_th": 3600,  # 1 hour
            "news_en": 3600,  # 1 hour
        }

    def get(self, key: str) -> Optional[Any]:
        """
        Get cached value if not expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if expired/missing
        """
        if key in self._cache:
            data, cached_at = self._cache[key]
            ttl = self._ttl_seconds.get(key, 3600)

            if (datetime.now() - cached_at).total_seconds() < ttl:
                return data
            else:
                del self._cache[key]
        return None

    def set(self, key: str, value: Any):
        """
        Cache a value with current timestamp.

        Args:
            key: Cache key
            value: Value to cache
        """
        self._cache[key] = (value, datetime.now())


class NewsDataService:
    """Service for fetching weather, air quality, and news data."""

    def __init__(self, http_client: httpx.AsyncClient, news_api_key: Optional[str] = None):
        """
        Initialize news data service.

        Args:
            http_client: Shared async HTTP client
            news_api_key: Optional NewsAPI.org API key
        """
        self.client = http_client
        self.news_api_key = news_api_key
        self.cache = DataCache()

        # Bangkok coordinates
        self.BANGKOK_LAT = 13.7563
        self.BANGKOK_LON = 100.5018

    async def get_weather_data(self) -> Dict[str, Any]:
        """
        Fetch current weather data for Bangkok from Open-Meteo.

        Returns:
            Dict with temperature, pm2.5, and rain forecast
        """
        cached = self.cache.get("weather")
        if cached:
            logger.info("📰 Using cached weather data")
            return cached

        try:
            # Fetch weather and forecast
            weather_url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.BANGKOK_LAT}"
                f"&longitude={self.BANGKOK_LON}"
                f"&current=temperature_2m"
                f"&hourly=precipitation"
                f"&forecast_hours=5"
            )

            weather_response = await self.client.get(weather_url, timeout=10.0)
            weather_response.raise_for_status()
            weather_data = weather_response.json()

            # Fetch air quality
            air_url = (
                f"https://air-quality-api.open-meteo.com/v1/air-quality"
                f"?latitude={self.BANGKOK_LAT}"
                f"&longitude={self.BANGKOK_LON}"
                f"&current=pm2_5"
            )

            air_response = await self.client.get(air_url, timeout=10.0)
            air_response.raise_for_status()
            air_data = air_response.json()

            # Process data
            temp_c = weather_data.get("current", {}).get("temperature_2m", "N/A")
            pm25 = air_data.get("current", {}).get("pm2_5", "N/A")

            # Check rain in next 5 hours
            hourly_precip = weather_data.get("hourly", {}).get("precipitation", [])
            will_rain = any(p > 0 for p in hourly_precip[:5]) if hourly_precip else False

            result = {
                "temperature": temp_c,
                "pm25": pm25,
                "will_rain": will_rain,
            }

            self.cache.set("weather", result)
            logger.info("📰 Fetched fresh weather data")
            return result

        except Exception as e:
            logger.error(f"📰 Error fetching weather data: {e}")
            return {
                "temperature": "N/A",
                "pm25": "N/A",
                "will_rain": None,
            }

    async def get_news_headlines(self, language: str = "en") -> List[Dict[str, str]]:
        """
        Fetch top 5 news headlines for Thailand.

        Args:
            language: Language code ('th' or 'en')

        Returns:
            List of dicts with 'title' and 'url' keys
        """
        cache_key = f"news_{language}"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info(f"📰 Using cached {language} news headlines")
            return cached

        try:
            if language == "th":
                headlines = await self._fetch_thai_news()
            else:
                headlines = await self._fetch_english_news()

            self.cache.set(cache_key, headlines)
            logger.info(f"📰 Fetched fresh {language} news headlines")
            return headlines

        except Exception as e:
            logger.error(f"📰 Error fetching {language} news: {e}")
            return []

    async def _fetch_thai_news(self) -> List[Dict[str, str]]:
        """Fetch Thai news from NewsAPI.org if key available."""
        if not self.news_api_key:
            logger.warning("📰 No NEWS_API_KEY configured, returning placeholder Thai news")
            return self._get_placeholder_headlines("th")

        try:
            url = (
                f"https://newsapi.org/v2/top-headlines"
                f"?country=th"
                f"&apiKey={self.news_api_key}"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            articles = data.get("articles", [])[:5]
            return [
                {
                    "title": article.get("title", "ไม่มีหัวข้อ"),
                    "url": article.get("url", ""),
                }
                for article in articles
            ]

        except Exception as e:
            logger.error(f"📰 NewsAPI error: {e}")
            return self._get_placeholder_headlines("th")

    async def _fetch_english_news(self) -> List[Dict[str, str]]:
        """Fetch English news from NewsAPI.org or fallback to placeholder."""
        if not self.news_api_key:
            logger.warning("📰 No NEWS_API_KEY configured, returning placeholder English news")
            return self._get_placeholder_headlines("en")

        try:
            url = (
                f"https://newsapi.org/v2/top-headlines"
                f"?country=th"
                f"&language=en"
                f"&apiKey={self.news_api_key}"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            articles = data.get("articles", [])[:5]
            return [
                {
                    "title": article.get("title", "No title"),
                    "url": article.get("url", ""),
                }
                for article in articles
            ]

        except Exception as e:
            logger.error(f"📰 NewsAPI error: {e}")
            return self._get_placeholder_headlines("en")

    def _get_placeholder_headlines(self, language: str) -> List[Dict[str, str]]:
        """Return placeholder headlines when API is unavailable."""
        if language == "th":
            return [
                {"title": "ข่าวไม่พร้อมใช้งาน - กรุณาตั้งค่า NEWS_API_KEY", "url": ""},
                {"title": "สามารถดูข่าวได้ที่ ThaiPBS", "url": "https://news.thaipbs.or.th"},
                {"title": "หรือ Bangkok Post", "url": "https://www.bangkokpost.com"},
                {"title": "หรือ The Nation", "url": "https://www.nationthailand.com"},
                {"title": "กด 9 เพื่อดูแหล่งข้อมูล", "url": ""},
            ]
        else:
            return [
                {"title": "News unavailable - Please set NEWS_API_KEY", "url": ""},
                {"title": "Visit ThaiPBS for news", "url": "https://news.thaipbs.or.th/en"},
                {"title": "Or Bangkok Post", "url": "https://www.bangkokpost.com"},
                {"title": "Or The Nation", "url": "https://www.nationthailand.com"},
                {"title": "Press 9 for resources", "url": ""},
            ]
