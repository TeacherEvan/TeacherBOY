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

    async def get_color_of_day(self) -> Dict[str, str]:
        """
        Get Thai lucky color of the day.

        Thai culture assigns a lucky color to each day of the week and year.
        This implementation uses day-of-year modulo to cycle through 5 colors.

        Returns:
            Dict with 'color_name_th', 'color_name_en', 'hex_code' keys
        """
        cache_key = "color_of_day"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("🎨 Using cached color of day")
            return cached

        # Thai lucky colors mapping (5-color cycle)
        # Note: Thai zodiac uses 12 colors; simplified to 5 primary colors
        THAI_COLORS = [
            {"th": "เหลือง", "en": "Yellow", "hex": "#FFD700"},  # Monday
            {"th": "ชมพู", "en": "Pink", "hex": "#FFC0CB"},  # Tuesday
            {"th": "เขียว", "en": "Green", "hex": "#32CD32"},  # Wednesday
            {"th": "ส้ม", "en": "Orange", "hex": "#FFA500"},  # Thursday
            {"th": "แดง", "en": "Red", "hex": "#FF0000"},  # Friday
        ]

        try:
            day_of_year = datetime.now().timetuple().tm_yday
            color_index = (day_of_year - 1) % len(THAI_COLORS)
            color_info = THAI_COLORS[color_index]

            result = {
                "color_name_th": color_info["th"],
                "color_name_en": color_info["en"],
                "hex_code": color_info["hex"],
            }

            self.cache.set(cache_key, result)
            logger.info(f"🎨 Color of day: {result['color_name_en']} ({result['color_name_th']})")
            return result

        except Exception as e:
            logger.error(f"🎨 Error getting color of day: {e}")
            return {
                "color_name_th": "ไม่ทราบ",
                "color_name_en": "Unknown",
                "hex_code": "#808080",
            }

    async def get_sunset_sunrise_times(self) -> Dict[str, str]:
        """
        Get sunset and sunrise times for Bangkok.

        Uses Open-Meteo API (same call as weather).
        Returns times in HH:MM format (24-hour).

        Returns:
            Dict with 'sunrise', 'sunset' keys in HH:MM format
        """
        cache_key = "sunset_sunrise"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("🌅 Using cached sunset/sunrise times")
            return cached

        try:
            url = (
                f"https://api.open-meteo.com/v1/forecast"
                f"?latitude={self.BANGKOK_LAT}"
                f"&longitude={self.BANGKOK_LON}"
                f"&daily=sunrise,sunset"
                f"&timezone=Asia%2FBangkok"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            daily = data.get("daily", {})
            sunrise_full = daily.get("sunrise", [""])[0]  # ISO format: "2024-12-16T06:30"
            sunset_full = daily.get("sunset", [""])[0]

            # Extract HH:MM
            sunrise = sunrise_full.split("T")[1][:5] if "T" in sunrise_full else "06:30"
            sunset = sunset_full.split("T")[1][:5] if "T" in sunset_full else "18:00"

            result = {
                "sunrise": sunrise,
                "sunset": sunset,
            }

            self.cache.set(cache_key, result)
            logger.info(f"🌅 Sunset/sunrise: {sunrise} - {sunset}")
            return result

        except Exception as e:
            logger.error(f"🌅 Error fetching sunset/sunrise: {e}")
            return {
                "sunrise": "06:30",
                "sunset": "18:00",
            }

    async def get_thai_holidays(self) -> List[Dict[str, str]]:
        """
        Get major Thai holidays and observances for current month.

        Falls back to static list if Calendarific API is unavailable.

        Returns:
            List of dicts with 'date', 'name_th', 'name_en' keys
        """
        cache_key = "thai_holidays"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("📅 Using cached Thai holidays")
            return cached

        # Fallback: Major Thai holidays (2024-2025)
        THAI_HOLIDAYS_STATIC = [
            {"date": "Dec 5", "name_th": "วันคล้ายวันพระราชสมภพพระบาทสมเด็จพระเจ้าอยู่หัว", "name_en": "King Bhumibol Commemoration"},
            {"date": "Dec 10", "name_th": "วันรัฐธรรมนูญ", "name_en": "Constitution Day"},
            {"date": "Dec 31", "name_th": "วันสิ้นปี", "name_en": "New Year's Eve"},
            {"date": "Jan 1", "name_th": "วันปีใหม่", "name_en": "New Year's Day"},
            {"date": "Feb 26", "name_th": "วันมาฆบูชา", "name_en": "Magha Bucha"},
            {"date": "Apr 6", "name_th": "วันจักรี", "name_en": "Chakri Memorial Day"},
            {"date": "Apr 13-15", "name_th": "สงกรานต์ (วันปีใหม่ไทย)", "name_en": "Songkran (Thai New Year)"},
            {"date": "May 1", "name_th": "วันแรงงาน", "name_en": "Labor Day"},
            {"date": "May 22", "name_th": "วันวิสาขบูชา", "name_en": "Visakha Bucha"},
        ]

        try:
            from src.config import settings
            if not settings.calendarific_api_key:
                logger.warning("📅 No CALENDARIFIC_API_KEY, using static holiday list")
                self.cache.set(cache_key, THAI_HOLIDAYS_STATIC)
                return THAI_HOLIDAYS_STATIC

            url = (
                f"https://calendarific.com/api/v2/holidays"
                f"?country=TH"
                f"&year={datetime.now().year}"
                f"&api_key={settings.calendarific_api_key}"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            holidays = []
            for holiday in data.get("response", {}).get("holidays", [])[:5]:  # Top 5
                holidays.append({
                    "date": holiday.get("date", {}).get("iso", ""),
                    "name_th": holiday.get("name", ""),
                    "name_en": holiday.get("description", ""),
                })

            self.cache.set(cache_key, holidays)
            logger.info(f"📅 Fetched {len(holidays)} Thai holidays from Calendarific")
            return holidays

        except Exception as e:
            logger.error(f"📅 Error fetching Thai holidays: {e}, using fallback")
            self.cache.set(cache_key, THAI_HOLIDAYS_STATIC)
            return THAI_HOLIDAYS_STATIC

    async def get_bitcoin_price(self) -> Dict[str, str]:
        """
        Get current Bitcoin price in USD.

        Uses CoinGecko API (free, no key required).
        Returns both price and 24-hour change percentage.

        Returns:
            Dict with 'price_usd', 'change_24h_percent' keys
        """
        cache_key = "bitcoin_price"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("₿ Using cached Bitcoin price")
            return cached

        try:
            url = (
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=bitcoin"
                "&vs_currencies=usd"
                "&include_24hr_change=true"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            bitcoin_data = data.get("bitcoin", {})
            price_usd = bitcoin_data.get("usd", 0)
            change_24h = bitcoin_data.get("usd_24h_change", 0)

            result = {
                "price_usd": f"${price_usd:,.2f}",
                "change_24h_percent": f"{change_24h:+.2f}%",
            }

            self.cache.set(cache_key, result)
            logger.info(f"₿ Bitcoin: {result['price_usd']} ({result['change_24h_percent']})")
            return result

        except Exception as e:
            logger.error(f"₿ Error fetching Bitcoin price: {e}")
            return {
                "price_usd": "N/A",
                "change_24h_percent": "N/A",
            }

    async def get_exchange_rates(self) -> Dict[str, str]:
        """
        Get exchange rates: THB → USD, THB → ZAR, THB → CNY.

        Uses ExchangeRate-API if key available, otherwise falls back to hardcoded rates.

        Returns:
            Dict with 'thb_usd', 'thb_zar', 'thb_cny' keys (rates per 1 THB)
        """
        cache_key = "exchange_rates"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("💱 Using cached exchange rates")
            return cached

        # Hardcoded fallback rates (approximate as of Dec 2024)
        FALLBACK_RATES = {
            "thb_usd": "0.027",      # 1 THB ≈ 0.027 USD
            "thb_zar": "0.49",       # 1 THB ≈ 0.49 ZAR
            "thb_cny": "0.19",       # 1 THB ≈ 0.19 CNY
        }

        try:
            from src.config import settings
            if not settings.exchange_rate_api_key:
                logger.warning("💱 No EXCHANGE_RATE_API_KEY, using fallback rates")
                self.cache.set(cache_key, FALLBACK_RATES)
                return FALLBACK_RATES

            url = (
                f"https://v6.exchangerate-api.com/v6/{settings.exchange_rate_api_key}/latest/THB"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            rates = data.get("conversion_rates", {})
            result = {
                "thb_usd": f"{rates.get('USD', 0):.3f}",
                "thb_zar": f"{rates.get('ZAR', 0):.3f}",
                "thb_cny": f"{rates.get('CNY', 0):.3f}",
            }

            self.cache.set(cache_key, result)
            logger.info(f"💱 Exchange rates: THB→USD {result['thb_usd']}")
            return result

        except Exception as e:
            logger.error(f"💱 Error fetching exchange rates: {e}, using fallback")
            self.cache.set(cache_key, FALLBACK_RATES)
            return FALLBACK_RATES
