"""News data retrieval service with caching for weather and news APIs."""

import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import httpx
import feedparser
import holidays
import csv
import io

logger = logging.getLogger(__name__)

# Constants
TITLE_TRUNCATE_LENGTH = 50  # Max characters to show in log messages

# Import metrics service at module level to avoid repeated imports
try:
    from src.services.metrics_service import metrics_service

    METRICS_AVAILABLE = True
except ImportError:
    METRICS_AVAILABLE = False
    logger.warning("⚠️  metrics_service not available, cache tracking disabled")


class DataCache:
    """Simple TTL cache for weather and news data."""

    def __init__(self):
        """Initialize cache with TTL settings."""
        self._cache: Dict[str, Tuple[Any, datetime]] = {}
        # Keep cache TTLs aligned with config defaults/env overrides.
        try:
            from src.config import settings

            self._ttl_seconds = {
                "weather": settings.weather_cache_ttl_seconds,
                "news_th": settings.news_cache_ttl_seconds,
                "news_en": settings.news_cache_ttl_seconds,
                "thai_holidays": settings.holiday_cache_ttl_seconds,
                "bitcoin_price": settings.bitcoin_cache_ttl_seconds,
                "crypto_prices": settings.bitcoin_cache_ttl_seconds,
                "exchange_rates": settings.exchange_cache_ttl_seconds,
                "market_indices": settings.exchange_cache_ttl_seconds,
                "color_of_day": settings.color_cache_ttl_seconds,
                "sunset_sunrise": settings.sunset_cache_ttl_seconds,
                # Festivals aren't separately configurable; use news cache TTL.
                "festivals": settings.news_cache_ttl_seconds,
            }
        except Exception:
            # Conservative fallback if settings can't be imported (e.g., in unusual test contexts)
            self._ttl_seconds = {
                "weather": 1800,  # 30 minutes
                "news_th": 7200,  # 2 hours
                "news_en": 7200,  # 2 hours
                "thai_holidays": 604800,  # 7 days
                "bitcoin_price": 300,  # 5 minutes
                "crypto_prices": 300,  # 5 minutes
                "exchange_rates": 3600,  # 1 hour
                "market_indices": 3600,  # 1 hour
                "color_of_day": 86400,  # 24 hours
                "sunset_sunrise": 86400,  # 24 hours
                "festivals": 3600,  # 1 hour
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
                # Record cache hit
                if METRICS_AVAILABLE:
                    metrics_service.record_cache_hit()
                return data
            else:
                del self._cache[key]

        # Record cache miss
        if METRICS_AVAILABLE:
            metrics_service.record_cache_miss()
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

    def __init__(
        self, http_client: Optional[httpx.AsyncClient], news_api_key: Optional[str] = None
    ):
        """
        Initialize news data service.

        Args:
            http_client: Shared async HTTP client
            news_api_key: Optional NewsAPI.org API key (kept for backward compatibility)
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
            will_rain = (
                any(p > 0 for p in hourly_precip[:5]) if hourly_precip else False
            )

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
        Fetch top 5 news headlines for Thailand using RSS feeds.

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
        """Fetch Thai news from Bangkok Post RSS (Thailand section)."""
        # Note: Bangkok Post RSS is in English, but covers local Thai news.
        # Ideally we would use a Thai language RSS feed, but for now this ensures reliability.
        rss_url = "https://www.bangkokpost.com/rss/data/thailand.xml"
        return self._parse_rss_feed(rss_url)

    async def _fetch_english_news(self) -> List[Dict[str, str]]:
        """Fetch English news from Bangkok Post RSS (Top Stories)."""
        rss_url = "https://www.bangkokpost.com/rss/data/topstories.xml"
        return self._parse_rss_feed(rss_url)

    def _parse_rss_feed(self, url: str) -> List[Dict[str, str]]:
        """Parse RSS feed and return top 5 items."""
        try:
            feed = feedparser.parse(url)
            logger.info(f"📰 Parsed RSS feed from {url}: {len(feed.entries)} entries")
            
            articles = []
            for i, entry in enumerate(feed.entries[:5]):
                title = getattr(entry, 'title', '')
                link = getattr(entry, 'link', '')
                
                if not link or not link.strip():
                    logger.warning(f"📰 Entry {i+1} '{title[:TITLE_TRUNCATE_LENGTH]}...' has no URL")
                
                articles.append({"title": title, "url": link})
                logger.debug(f"📰 Entry {i+1}: title='{title[:TITLE_TRUNCATE_LENGTH]}...', url={link}")
            
            return articles
        except Exception as e:
            logger.error(f"📰 RSS parse error for {url}: {e}", exc_info=True)
            return [
                {"title": "News unavailable", "url": ""},
                {"title": "Visit Bangkok Post", "url": "https://www.bangkokpost.com"},
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
            logger.info(
                f"🎨 Color of day: {result['color_name_en']} ({result['color_name_th']})"
            )
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
            sunrise_full = daily.get("sunrise", [""])[
                0
            ]  # ISO format: "2024-12-16T06:30"
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
        Get major Thai holidays and observances for current year using 'holidays' library.

        Returns:
            List of dicts with 'date', 'name_th', 'name_en' keys
        """
        cache_key = "thai_holidays"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("📅 Using cached Thai holidays")
            return cached

        try:
            # Get holidays for current year in both languages
            # Note: We create two holiday objects to support bilingual output.
            # The holidays library doesn't provide a native method to get names in multiple languages,
            # so this is the recommended approach. The objects are lightweight and only created once per cache TTL.
            year = datetime.now().year
            # Get Thai names
            th_holidays_th = holidays.country_holidays("TH", years=year, language="th")
            # Get English names
            th_holidays_en = holidays.country_holidays(
                "TH", years=year, language="en_US"
            )

            # Sort by date (use Thai version for dates)
            sorted_holidays = sorted(th_holidays_th.items())

            # Filter for upcoming holidays (or recent ones if near end of year)
            # For simplicity, we return the next 5 holidays from today
            today = datetime.now().date()
            upcoming = []

            for date_obj, name_th in sorted_holidays:
                if date_obj >= today:
                    name_en = th_holidays_en.get(
                        date_obj, name_th
                    )  # Fallback to Thai if English missing
                    upcoming.append(
                        {
                            "date": date_obj.strftime("%b %d"),
                            "name_th": name_th,
                            "name_en": name_en,
                        }
                    )

            # If fewer than 3 upcoming, add next year's
            if len(upcoming) < 3:
                th_holidays_next_th = holidays.country_holidays(
                    "TH", years=year + 1, language="th"
                )
                th_holidays_next_en = holidays.country_holidays(
                    "TH", years=year + 1, language="en_US"
                )
                sorted_next = sorted(th_holidays_next_th.items())
                for date_obj, name_th in sorted_next:
                    name_en = th_holidays_next_en.get(date_obj, name_th)
                    upcoming.append(
                        {
                            "date": date_obj.strftime("%b %d"),
                            "name_th": name_th,
                            "name_en": name_en,
                        }
                    )
                    if len(upcoming) >= 5:
                        break

            result = upcoming[:5]
            self.cache.set(cache_key, result)
            logger.info(f"📅 Fetched {len(result)} Thai holidays from library")
            return result

        except Exception as e:
            logger.error(f"📅 Error fetching Thai holidays: {e}")
            # Fallback
            return [
                {
                    "date": "N/A",
                    "name_th": "ไม่สามารถดึงข้อมูลวันหยุดได้",
                    "name_en": "Unable to fetch holidays",
                }
            ]

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
            logger.info(
                f"₿ Bitcoin: {result['price_usd']} ({result['change_24h_percent']})"
            )
            return result

        except Exception as e:
            logger.error(f"₿ Error fetching Bitcoin price: {e}")
            return {
                "price_usd": "N/A",
                "change_24h_percent": "N/A",
            }

    async def get_exchange_rates(self) -> Dict[str, str]:
        """
        Get exchange rates: 1 THB → USD, JPY, ZAR, AUD, GBP, RUB.

        Uses ExchangeRate-API if key available, otherwise falls back to hardcoded rates.

        Returns:
            Dict with currency keys (rates per 1 THB)
        """
        cache_key = "exchange_rates"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("💱 Using cached exchange rates")
            return cached

        # Hardcoded fallback rates (approximate as of Dec 2024)
        FALLBACK_RATES = {
            "usd": "0.027",  # 1 THB ≈ 0.027 USD
            "jpy": "4.00",  # 1 THB ≈ 4.00 JPY
            "zar": "0.49",  # 1 THB ≈ 0.49 ZAR
            "aud": "0.041",  # 1 THB ≈ 0.041 AUD
            "gbp": "0.021",  # 1 THB ≈ 0.021 GBP
            "rub": "2.40",  # 1 THB ≈ 2.40 RUB
            # Backward-compat for older tests/menu paths
            "cny": "0.19",  # 1 THB ≈ 0.19 CNY
        }

        def _with_legacy_keys(rates: Dict[str, str]) -> Dict[str, str]:
            """Return rates with both short and legacy thb_* keys."""
            combined = dict(rates)
            for k, v in rates.items():
                combined[f"thb_{k}"] = v
            return combined

        try:
            from src.config import settings

            if not settings.exchange_rate_api_key:
                logger.warning("💱 No EXCHANGE_RATE_API_KEY, using fallback rates")
                result = _with_legacy_keys(FALLBACK_RATES)
                self.cache.set(cache_key, result)
                return result

            url = f"https://v6.exchangerate-api.com/v6/{settings.exchange_rate_api_key}/latest/THB"

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            rates = data.get("conversion_rates", {})
            short_result = {
                "usd": f"{rates.get('USD', 0):.3f}",
                "jpy": f"{rates.get('JPY', 0):.3f}",
                "zar": f"{rates.get('ZAR', 0):.3f}",
                "aud": f"{rates.get('AUD', 0):.3f}",
                "gbp": f"{rates.get('GBP', 0):.3f}",
                "rub": f"{rates.get('RUB', 0):.3f}",
                # Backward-compat for older tests/menu paths
                "cny": f"{rates.get('CNY', 0):.3f}",
            }

            result = _with_legacy_keys(short_result)

            self.cache.set(cache_key, result)
            logger.info(f"💱 Exchange rates: THB→USD {result['usd']}")
            return result

        except Exception as e:
            logger.error(f"💱 Error fetching exchange rates: {e}, using fallback")
            result = _with_legacy_keys(FALLBACK_RATES)
            self.cache.set(cache_key, result)
            return result

    async def get_crypto_prices(self) -> Dict[str, Dict[str, str]]:
        """
        Get crypto prices (USD): BTC, ETH, USDT.

        Uses CoinGecko (free, no key required). Returns formatted strings.

        Returns:
            Dict like {"btc": {"price_usd": "...", "change_24h_percent": "..."}, ...}
        """
        cache_key = "crypto_prices"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("₿ Using cached crypto prices")
            return cached

        # Conservative fallback
        fallback = {
            "btc": {"price_usd": "N/A", "change_24h_percent": "N/A"},
            "eth": {"price_usd": "N/A", "change_24h_percent": "N/A"},
            "usdt": {"price_usd": "N/A", "change_24h_percent": "N/A"},
        }

        try:
            url = (
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=bitcoin,ethereum,tether"
                "&vs_currencies=usd"
                "&include_24hr_change=true"
            )

            response = await self.client.get(url, timeout=10.0)
            response.raise_for_status()
            data = response.json()

            def _fmt(asset: dict) -> Dict[str, str]:
                price = asset.get("usd", None)
                change = asset.get("usd_24h_change", None)
                if isinstance(price, (int, float)):
                    price_str = f"${price:,.2f}"
                else:
                    price_str = "N/A"
                if isinstance(change, (int, float)):
                    change_str = f"{change:+.2f}%"
                else:
                    change_str = "N/A"
                return {"price_usd": price_str, "change_24h_percent": change_str}

            result = {
                "btc": _fmt(data.get("bitcoin", {})),
                "eth": _fmt(data.get("ethereum", {})),
                "usdt": _fmt(data.get("tether", {})),
            }

            self.cache.set(cache_key, result)
            logger.info("₿ Fetched fresh crypto prices")
            return result
        except Exception as e:
            logger.error(f"₿ Error fetching crypto prices: {e}")
            self.cache.set(cache_key, fallback)
            return fallback

    async def get_market_indices(self) -> Dict[str, str]:
        """
        Get headline market indices (best-effort, no API key).

        Source: stooq.com CSV endpoint.

        Returns:
            Dict of index labels to formatted strings.
        """
        cache_key = "market_indices"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("📈 Using cached market indices")
            return cached

        # Symbols are best-effort; stooq uses caret-prefixed names for indices.
        symbol_map = {
            "S&P 500": "^spx",
            "DJIA": "^dji",
            "FTSE 100": "^ftse",
        }

        result: Dict[str, str] = {label: "N/A" for label in symbol_map}

        try:
            for label, symbol in symbol_map.items():
                url = f"https://stooq.com/q/l/?s={symbol}&f=sd2t2ohlcv&h&e=csv"
                resp = await self.client.get(url, timeout=10.0)
                resp.raise_for_status()

                # CSV is usually: Symbol,Date,Time,Open,High,Low,Close,Volume
                content = resp.text.strip()
                if not content:
                    continue

                reader = csv.DictReader(io.StringIO(content))
                row = next(reader, None)
                if not row:
                    continue

                close_raw = row.get("Close")
                open_raw = row.get("Open")

                try:
                    close_val = (
                        float(close_raw) if close_raw not in (None, "", "N/A") else None
                    )
                except ValueError:
                    close_val = None

                try:
                    open_val = (
                        float(open_raw) if open_raw not in (None, "", "N/A") else None
                    )
                except ValueError:
                    open_val = None

                if close_val is None:
                    continue

                if open_val and open_val != 0:
                    change_pct = ((close_val - open_val) / open_val) * 100.0
                    result[label] = f"{close_val:,.2f} ({change_pct:+.2f}%)"
                else:
                    result[label] = f"{close_val:,.2f}"

            self.cache.set(cache_key, result)
            logger.info("📈 Fetched fresh market indices")
            return result
        except Exception as e:
            logger.error(f"📈 Error fetching market indices: {e}")
            self.cache.set(cache_key, result)
            return result

    async def get_upcoming_festivals(self) -> List[Dict[str, str]]:
        """
        Get upcoming major festivals in Bangkok/Pattaya.

        Uses TAT API if available, otherwise returns static major festivals.
        Layout: Name: ""; Date: ""
        """
        cache_key = "festivals"
        cached = self.cache.get(cache_key)
        if cached:
            logger.info("🎉 Using cached festivals")
            return cached

        # Static fallback list (Major events)
        # Note: Dates are approximate/examples for 2025
        FALLBACK_FESTIVALS = [
            {"name": "Chinese New Year (Bangkok)", "date": "Jan 29, 2025"},
            {"name": "Makha Bucha (Nationwide)", "date": "Feb 12, 2025"},
            {"name": "Pattaya Music Festival", "date": "Mar 2025 (TBC)"},
            {"name": "Songkran (Thai New Year)", "date": "Apr 13-15, 2025"},
            {"name": "Wan Lai (Pattaya Songkran)", "date": "Apr 19, 2025"},
        ]

        try:
            from src.config import settings

            if not settings.tat_api_key:
                logger.info("🎉 No TAT_API_KEY, using fallback festivals")
                self.cache.set(cache_key, FALLBACK_FESTIVALS)
                return FALLBACK_FESTIVALS

            # TAT API Implementation (Placeholder - requires valid endpoint verification)
            # Endpoint: https://tatapi.tourismthailand.org/tat/api/v1/events
            url = "https://tatapi.tourismthailand.org/tat/api/v1/events"
            headers = {
                "Authorization": f"Bearer {settings.tat_api_key}",
                "Accept-Language": "en",
            }

            # We would fetch here. For now, return fallback to avoid breaking if key is invalid.
            # response = await self.client.get(url, headers=headers, timeout=10.0)
            # ... process response ...

            # Returning fallback for now until API is verified
            self.cache.set(cache_key, FALLBACK_FESTIVALS)
            return FALLBACK_FESTIVALS

        except Exception as e:
            logger.error(f"🎉 Error fetching festivals: {e}")
            return FALLBACK_FESTIVALS
