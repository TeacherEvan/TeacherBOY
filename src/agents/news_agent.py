"""News agent - Handles weather, air quality, and news headlines in multi-step flow.

Auto-detects language from trigger: 'news' = English, 'ข่าว' = Thai (no selection prompt).
"""

import logging
import re
from typing import List, Dict, Optional
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.messaging.exceptions import ApiException

from .base_agent import BaseAgent
from src.services.news_session_manager import news_session_manager
from src.services.news_data_service import NewsDataService
from src.services.rate_limiter import RateLimiter
from src.services.metrics_service import metrics_service
from src.config import settings

logger = logging.getLogger(__name__)

# Rate limiters for news requests
news_rate_limiter_friend = RateLimiter(max_requests=1, time_window_seconds=3600)  # 1/hour for friends


class NewsAgent(BaseAgent):
    """Agent for handling multi-step news conversations with weather and headlines."""

    _NEWS_TRIGGERS = {"news", "ข่าว", "นิวส์"}

    def __init__(self, news_data_service: NewsDataService):
        super().__init__(
            name="NewsAgent",
            description="Weather, air quality, and news headlines for Bangkok",
        )
        self.news_service = news_data_service
        self._admin_user_ids = settings.get_admin_user_ids()
        # Import translation services for headline translation
        from src.services.google_translation import google_translation_service
        from src.services.translation_service import translation_service as libre_translation
        self.google_translate = google_translation_service
        self.libre_translate = libre_translation

    def _is_admin(self, user_id: Optional[str]) -> bool:
        """Check if user is an admin (admins bypass rate limits)."""
        return user_id in self._admin_user_ids if user_id else False

    def get_priority(self) -> int:
        """News agent priority - runs after Translation (10)."""
        return 15

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract and normalize chat ID from event."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return f"group_{group_id}"
        if event.source and hasattr(event.source, "room_id"):
            room_id = getattr(event.source, "room_id", None)
            if room_id:
                return f"room_{room_id}"
        if event.source:
            user_id = getattr(event.source, "user_id", "unknown")
            return f"user_{user_id}"
        return "user_unknown"

    def _is_line_system_message(self, text: str) -> bool:
        """Check if message is a LINE system message (ignore bracketed text)."""
        # Pattern: [Name], [系統], etc.
        return bool(re.match(r"^\[.*\]$", text.strip()))

    def _normalize_trigger_text(self, text: str) -> str:
        """Normalize trigger text (lowercase, trimmed, strip trailing punctuation)."""
        text_clean = text.lower().strip()
        # Allow common punctuation after the trigger: "news!" / "ข่าว." / etc.
        return re.sub(r"[\s.!?]+$", "", text_clean)

    def _is_thai_text(self, text: str) -> bool:
        """Return True when text contains Thai characters."""
        return any("\u0E00" <= char <= "\u0E7F" for char in text)

    def _is_news_trigger(self, text: str) -> bool:
        """Check if text is a news trigger word."""
        text_clean = self._normalize_trigger_text(text)
        return text_clean in self._NEWS_TRIGGERS

    def _is_shutdown_phrase(self, text: str) -> bool:
        """
        Check if text is a shutdown phrase ("thank you teacherboy").
        
        This allows users to exit news flow immediately by thanking the bot.
        """
        text_lower = text.lower().strip()
        teacher_pattern = r"teacher(?:boy|boi|biy|boj|boii)"
        shutdown_patterns = [
            rf"^thanks?\s+{teacher_pattern}[\s.!]*$",
            rf"^thank\s+you\s+{teacher_pattern}[\s.!]*$",
            rf"^thx\s+{teacher_pattern}[\s.!]*$",
            rf"^ty\s+{teacher_pattern}[\s.!]*$",
            rf"^ขอบคุณ\s*{teacher_pattern}[\s.!]*$",
            rf"^ขอบใจ\s*{teacher_pattern}[\s.!]*$",
        ]
        return any(re.search(pattern, text_lower) for pattern in shutdown_patterns)

    def _is_group_chat(self, event: MessageEvent) -> bool:
        """Return True when message comes from a group or room."""
        if event.source and getattr(event.source, "group_id", None):
            return True
        if event.source and getattr(event.source, "room_id", None):
            return True
        return False

    async def _is_friend(self, event: MessageEvent, line_bot_api: MessagingApi) -> bool:
        """Check if user is a friend of the bot; LINE returns error for non-friends."""
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not user_id:
            logger.warning(f"📰 No user_id found for friendship check")
            return False

        try:
            line_bot_api.get_profile(user_id)
            logger.info(f"📰 User {user_id} is a friend (verified via LINE API)")
            return True
        except ApiException as e:
            status = getattr(e, 'status_code', 'unknown')
            logger.info(f"📰 User {user_id} is NOT a friend (ApiException: {status})", exc_info=False)
            return False
        except Exception as e:
            logger.warning(f"📰 Friendship check failed for {user_id}: {e}", exc_info=False)
            return False

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Chat is in active news flow
        2. News trigger ("news" or "ข่าว") in allowed contexts
        """
        # Ignore LINE system messages
        if self._is_line_system_message(text):
            return False

        chat_id = self._get_chat_id(event)

        # Handle if in active news flow
        if news_session_manager.is_in_news_flow(chat_id):
            return True

        # Private chats: let translation agent handle; this agent only translates trigger word
        if not self._is_group_chat(event):
            return self._is_news_trigger(text)

        # Group/room: handle translation-only for non-friends and full flow for friends
        if self._is_news_trigger(text):
            return True

        return False

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """Process news-related messages through multi-step flow."""
        chat_id = self._get_chat_id(event)
        session = news_session_manager.get_session_state(chat_id)
        user_id = getattr(event.source, "user_id", None) if event.source else None

        try:
            # ALWAYS check for shutdown phrase first - allows exit at any time
            if self._is_shutdown_phrase(text) and session:
                news_session_manager.end_news_flow(chat_id)
                # Send goodbye message
                goodbye_msg = TextMessage(text="👋 News session ended. Type 'news' or 'ข่าว' to start again!", quickReply=None, quoteToken=None)
                if event.reply_token:
                    line_bot_api.reply_message(
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[goodbye_msg],
                            notificationDisabled=False,
                        )
                    )
                logger.info(f"📰 User ended news session with shutdown phrase in chat {chat_id}")
                return True

            # Private chats: respond with translation of trigger only
            if not self._is_group_chat(event):
                if self._is_news_trigger(text):
                    await self._send_trigger_translation(event, line_bot_api, text)
                    return True
                return False

            # Check if user is session owner (only they can interact)
            if session and not news_session_manager.is_session_owner(chat_id, user_id):
                # Silently ignore - another user trying to interact with someone else's session
                logger.debug(f"📰 User {user_id} tried to interact with news session owned by {session.get('user_id')}")
                return True  # Handled but ignored

            # Step 1: News trigger - start flow with auto-detected language
            if not session and self._is_news_trigger(text):
                user_id = getattr(event.source, "user_id", None) if event.source else None
                
                # Admins bypass friendship check
                is_admin = self._is_admin(user_id)
                
                # Non-friends and non-admins: just translate trigger word
                if not is_admin:
                    is_friend = await self._is_friend(event, line_bot_api)
                    if not is_friend:
                        await self._send_trigger_translation(event, line_bot_api, text)
                        return True

                # Rate limit check (skip for admins)
                if not is_admin:
                    # Friends get 1/hour
                    limiter = news_rate_limiter_friend
                    max_requests = 1
                    
                    if not limiter.is_allowed(chat_id):
                        remaining = limiter.get_remaining_requests(chat_id)
                        reset_seconds = limiter.get_reset_time(chat_id)
                        await self._send_rate_limit_message(event, line_bot_api, max_requests, remaining, reset_seconds)
                        logger.warning(f"⚠️  Rate limited news request for chat {chat_id}")
                        return True
                elif user_id:
                    logger.debug(f"🔓 Admin {user_id} bypassed news rate limit")

                    # Track successful news request (menu will be shown)
                    metrics_service.record_news_request()

                # Auto-detect language from trigger word
                trigger_text = self._normalize_trigger_text(text)
                language = "th" if self._is_thai_text(trigger_text) else "en"
                
                # Start flow with detected language and go straight to menu
                news_session_manager.start_news_flow(chat_id, user_id)
                news_session_manager.set_language(chat_id, language)
                await self._send_main_menu(event, line_bot_api, language)
                return True

            # Step 2: Main menu - handle selections
            if session and session["step"] == "main_menu":
                return await self._handle_main_menu(event, text, line_bot_api, chat_id, session)

            # Step 3: Headline detail - return to menu
            if session and session["step"] == "headline_detail":
                news_session_manager.return_to_menu(chat_id)
                await self._send_main_menu(event, line_bot_api, session["language"])
                return True

            return False

        except Exception as e:
            logger.error(f"📰 Error in NewsAgent: {e}", exc_info=True)
            await self._send_error_message(event, line_bot_api)
            news_session_manager.end_news_flow(chat_id)
            return False

    async def _send_language_selection(self, event: MessageEvent, line_bot_api: MessagingApi):
        """Send language selection prompt."""
        message = "📰 News / ข่าว\n\nSelect language:\n1 = Thai (ไทย)\n2 = English"
        
        text_msg = TextMessage(text=message, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _send_main_menu(self, event: MessageEvent, line_bot_api: MessagingApi, language: str):
        """Fetch data and send main menu with weather and news."""
        chat_id = self._get_chat_id(event)
        
        # Fetch weather and Thailand-only headlines
        weather_data = await self.news_service.get_weather_data()
        # Bangkok Post Thailand RSS is English; Thai UI translates headlines.
        headlines = await self.news_service.get_news_headlines("th")
        
        # Translate headlines to Thai if Thai language selected
        if language == "th" and headlines:
            headlines = await self._translate_headlines_to_thai(headlines)
        
        # Fetch additional inline data
        holidays_data = await self.news_service.get_thai_holidays()
        indices_data = await self.news_service.get_market_indices()
        crypto_data = await self.news_service.get_crypto_prices()
        exchange_data = await self.news_service.get_exchange_rates()
        
        # Cache data in session
        news_session_manager.set_cached_data(chat_id, {
            "weather": weather_data,
            "headlines": headlines,
            "holidays": holidays_data,
            "indices": indices_data,
            "crypto": crypto_data,
            "exchange": exchange_data,
        })
        
        # Format message
        if language == "th":
            message = self._format_menu_thai(weather_data, headlines, holidays_data, indices_data, crypto_data, exchange_data)
        else:
            message = self._format_menu_english(weather_data, headlines, holidays_data, indices_data, crypto_data, exchange_data)
        
        text_msg = TextMessage(text=message, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _translate_headlines_to_thai(self, headlines: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Translate English headlines to Thai."""
        translated_headlines = []
        
        for headline in headlines:
            title = headline.get("title", "")
            url = headline.get("url", "")
            
            if not title or title in ["News unavailable", "Visit Bangkok Post"]:
                # Don't translate fallback messages
                translated_headlines.append(headline)
                continue
            
            # Try Google Translate first, fallback to LibreTranslate
            translated_title = None
            if self.google_translate.is_configured():
                try:
                    translated_title = await self.google_translate.translate(
                        text=title,
                        target_lang="th",
                        source_lang="en"
                    )
                except Exception as e:
                    logger.warning(f"Google Translate failed for headline: {e}")
            
            # Fallback to LibreTranslate
            if not translated_title:
                try:
                    translated_title = await self.libre_translate.translate(
                        text=title,
                        source_lang="en",
                        target_lang="th"
                    )
                except Exception as e:
                    logger.warning(f"LibreTranslate failed for headline: {e}")
                    # Use original English if translation fails
                    translated_title = title
            
            translated_headlines.append({
                "title": translated_title or title,
                "url": url
            })
        
        return translated_headlines

    def _format_menu_thai(
        self,
        weather: dict,
        headlines: list,
        holidays: list,
        indices: dict,
        crypto: dict,
        exchange: dict,
    ) -> str:
        """Format main menu in Thai with all inline data."""
        temp = weather.get("temperature", "N/A")
        pm25 = weather.get("pm25", "N/A")
        will_rain = weather.get("will_rain")
        rain_text = "ใช่ (Yes)" if will_rain else "ไม่ (No)" if will_rain is not None else "N/A"
        
        msg = "📰 Bangkok\n\n"
        msg += f"🌡️ อุณหภูมิ: {temp}°C | 💨 PM2.5: {pm25}\n"
        msg += f"🌧️ 5 ชม.ข้างหน้า: {rain_text}\n"
        
        # Next holiday (first upcoming only)
        if holidays and len(holidays) > 0:
            holiday = holidays[0]
            msg += f"📅 วันหยุดถัดไป: {holiday.get('date', 'N/A')} - {holiday.get('name_th', 'N/A')}\n"

        # Indices
        spx = indices.get("S&P 500", "N/A")
        dji = indices.get("DJIA", "N/A")
        ftse = indices.get("FTSE 100", "N/A")
        msg += f"📈 ดัชนี: S&P 500 {spx} | DJIA {dji} | FTSE {ftse}\n"

        # Crypto
        btc = crypto.get("btc", {})
        eth = crypto.get("eth", {})
        usdt = crypto.get("usdt", {})
        msg += (
            "₿ Crypto: "
            f"BTC {btc.get('price_usd', 'N/A')} ({btc.get('change_24h_percent', 'N/A')}), "
            f"ETH {eth.get('price_usd', 'N/A')} ({eth.get('change_24h_percent', 'N/A')}), "
            f"USDT {usdt.get('price_usd', 'N/A')} ({usdt.get('change_24h_percent', 'N/A')})\n"
        )

        # Exchange rates (1 THB)
        msg += (
            "💱 อัตราแลก (1 THB): "
            f"USD {exchange.get('usd', 'N/A')}, "
            f"JPY {exchange.get('jpy', 'N/A')}, "
            f"ZAR {exchange.get('zar', 'N/A')}, "
            f"AUD {exchange.get('aud', 'N/A')}, "
            f"GBP {exchange.get('gbp', 'N/A')}, "
            f"RUB {exchange.get('rub', 'N/A')}\n\n"
        )
        
        msg += "📰 หัวข้อข่าว (Thailand):\n"

        for i, headline in enumerate(headlines[:5], 1):
            title = headline.get("title", "ไม่มีหัวข้อ")[:80]
            msg += f"{i}. {title}\n"
        
        return msg

    def _format_menu_english(
        self,
        weather: dict,
        headlines: list,
        holidays: list,
        indices: dict,
        crypto: dict,
        exchange: dict,
    ) -> str:
        """Format main menu in English with all inline data."""
        temp = weather.get("temperature", "N/A")
        pm25 = weather.get("pm25", "N/A")
        will_rain = weather.get("will_rain")
        rain_text = "Yes" if will_rain else "No" if will_rain is not None else "N/A"
        
        msg = "📰 Bangkok\n\n"
        msg += f"🌡️ Temp: {temp}°C | 💨 PM2.5: {pm25}\n"
        msg += f"🌧️ Next 5h rain: {rain_text}\n"
        
        # Next holiday (first upcoming only)
        if holidays and len(holidays) > 0:
            holiday = holidays[0]
            msg += f"📅 Next Holiday: {holiday.get('date', 'N/A')} - {holiday.get('name_en', 'N/A')}\n"

        # Indices
        spx = indices.get("S&P 500", "N/A")
        dji = indices.get("DJIA", "N/A")
        ftse = indices.get("FTSE 100", "N/A")
        msg += f"📈 Indices: S&P 500 {spx} | DJIA {dji} | FTSE {ftse}\n"

        # Crypto
        btc = crypto.get("btc", {})
        eth = crypto.get("eth", {})
        usdt = crypto.get("usdt", {})
        msg += (
            "₿ Crypto: "
            f"BTC {btc.get('price_usd', 'N/A')} ({btc.get('change_24h_percent', 'N/A')}), "
            f"ETH {eth.get('price_usd', 'N/A')} ({eth.get('change_24h_percent', 'N/A')}), "
            f"USDT {usdt.get('price_usd', 'N/A')} ({usdt.get('change_24h_percent', 'N/A')})\n"
        )

        # Exchange rates (1 THB)
        msg += (
            "💱 FX (1 THB): "
            f"USD {exchange.get('usd', 'N/A')}, "
            f"JPY {exchange.get('jpy', 'N/A')}, "
            f"ZAR {exchange.get('zar', 'N/A')}, "
            f"AUD {exchange.get('aud', 'N/A')}, "
            f"GBP {exchange.get('gbp', 'N/A')}, "
            f"RUB {exchange.get('rub', 'N/A')}\n\n"
        )
        
        msg += "📰 Headlines (Thailand):\n"

        for i, headline in enumerate(headlines[:5], 1):
            title = headline.get("title", "No title")[:80]
            msg += f"{i}. {title}\n"
        
        return msg

    async def _handle_main_menu(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi, 
        chat_id: str, session: dict
    ) -> bool:
        """Handle main menu selections (1-5 for headlines only)."""
        text_clean = text.strip()
        
        # Normalize Thai numerals to Arabic numerals
        thai_to_arabic = {
            "๑": "1", "๒": "2", "๓": "3", "๔": "4", "๕": "5",
        }
        normalized = thai_to_arabic.get(text_clean, text_clean)
        
        # Handle headline selection (1-5)
        if normalized in ["1", "2", "3", "4", "5"]:
            try:
                index = int(normalized) - 1
            except ValueError:
                await self._send_invalid_choice(event, line_bot_api, session["language"])
                return True
            
            cached_data = session.get("cached_data", {})
            headlines = cached_data.get("headlines", [])
            
            if index < len(headlines):
                headline = headlines[index]
                news_session_manager.select_headline(chat_id, index)
                await self._send_headline_detail(event, line_bot_api, headline, session["language"])
                return True
            else:
                await self._send_invalid_choice(event, line_bot_api, session["language"])
                return True
        
        else:
            await self._send_invalid_choice(event, line_bot_api, session["language"])
            return True

    async def _send_headline_detail(
        self, event: MessageEvent, line_bot_api: MessagingApi, 
        headline: dict, language: str
    ):
        """Send detailed headline with link."""
        title = headline.get("title", "")
        url = headline.get("url", "")
        
        if language == "th":
            msg = f"📰 {title}\n"
            if url:
                msg += f"🔗 {url}\n"
        else:
            msg = f"📰 {title}\n"
            if url:
                msg += f"🔗 {url}\n"
        
        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _send_color_sunset_sunrise(
        self, event: MessageEvent, line_bot_api: MessagingApi, language: str
    ):
        """Send lucky color of day + sunset/sunrise times."""
        try:
            color_data = await self.news_service.get_color_of_day()
            time_data = await self.news_service.get_sunset_sunrise_times()

            if language == "th":
                color_name = color_data.get("color_name_th", "ไม่ทราบ")
                msg = f"🎨 สีแม่น้ำวันนี้: {color_name}\n"
                msg += f"   (ฐานะดี / Lucky)\n\n"
                msg += f"🌅 พระอาทิตย์ขึ้น: {time_data.get('sunrise', 'N/A')}\n"
                msg += f"🌇 พระอาทิตย์ตก: {time_data.get('sunset', 'N/A')}"
            else:
                color_name = color_data.get("color_name_en", "Unknown")
                msg = f"🎨 Lucky color: {color_name}\n\n"
                msg += f"🌅 Sunrise: {time_data.get('sunrise', 'N/A')}\n"
                msg += f"🌇 Sunset: {time_data.get('sunset', 'N/A')}"

            text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
            if event.reply_token:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[text_msg],
                        notificationDisabled=False,
                    )
                )
        except Exception as e:
            logger.error(f"📰 Error sending color/sunset: {e}", exc_info=True)
            await self._send_error_message(event, line_bot_api)

    async def _send_holidays_markets(
        self, event: MessageEvent, line_bot_api: MessagingApi, language: str
    ):
        """Send Thai holidays + SET market info."""
        try:
            holidays = await self.news_service.get_thai_holidays()

            if language == "th":
                msg = "📅 วันหยุดราชการ (ต.ค.-ธ.ค.):\n"
                for holiday in holidays[:3]:  # Top 3 holidays
                    date = holiday.get("date", "")
                    name = holiday.get("name_th", "")
                    msg += f"• {date}: {name}\n"
                msg += "\n🏛️ ตลาดหุ้น SET (ปิด):\n"
                msg += "• วันเสาร์-อาทิตย์\n"
                msg += "• วันหยุดราชการ"
            else:
                msg = "📅 Thai Holidays (Oct-Dec):\n"
                for holiday in holidays[:3]:  # Top 3 holidays
                    date = holiday.get("date", "")
                    name = holiday.get("name_en", "")
                    msg += f"• {date}: {name}\n"
                msg += "\n🏛️ SET Market (Closed):\n"
                msg += "• Saturday-Sunday\n"
                msg += "• Thai holidays"

            text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
            if event.reply_token:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[text_msg],
                        notificationDisabled=False,
                    )
                )
        except Exception as e:
            logger.error(f"📰 Error sending holidays/markets: {e}", exc_info=True)
            await self._send_error_message(event, line_bot_api)

    async def _send_crypto_exchange(
        self, event: MessageEvent, line_bot_api: MessagingApi, language: str
    ):
        """Send Bitcoin price + exchange rates."""
        try:
            btc_data = await self.news_service.get_bitcoin_price()
            rates_data = await self.news_service.get_exchange_rates()

            if language == "th":
                msg = f"₿ Bitcoin (USD): {btc_data.get('price_usd', 'N/A')}\n"
                msg += f"   24h: {btc_data.get('change_24h_percent', 'N/A')}\n\n"
                msg += "💱 อัตราแลก (1 THB):\n"
                msg += f"• USD: {rates_data.get('thb_usd', 'N/A')}\n"
                msg += f"• ZAR: {rates_data.get('thb_zar', 'N/A')}\n"
                msg += f"• CNY: {rates_data.get('thb_cny', 'N/A')}"
            else:
                msg = f"₿ Bitcoin (USD): {btc_data.get('price_usd', 'N/A')}\n"
                msg += f"   24h: {btc_data.get('change_24h_percent', 'N/A')}\n\n"
                msg += "💱 Exchange (1 THB):\n"
                msg += f"• USD: {rates_data.get('thb_usd', 'N/A')}\n"
                msg += f"• ZAR: {rates_data.get('thb_zar', 'N/A')}\n"
                msg += f"• CNY: {rates_data.get('thb_cny', 'N/A')}"

            text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
            if event.reply_token:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[text_msg],
                        notificationDisabled=False,
                    )
                )
        except Exception as e:
            logger.error(f"📰 Error sending crypto/exchange: {e}", exc_info=True)
            await self._send_error_message(event, line_bot_api)

    async def _send_festivals(
        self, event: MessageEvent, line_bot_api: MessagingApi, language: str
    ):
        """Send upcoming festivals."""
        try:
            festivals = await self.news_service.get_upcoming_festivals()

            if language == "th":
                msg = "🎉 เทศกาลที่กำลังจะมาถึง (กทม./พัทยา):\n\n"
                for fest in festivals:
                    name = fest.get("name", "")
                    date = fest.get("date", "")
                    msg += f"• {name}\n  📅 {date}\n"
            else:
                msg = "🎉 Upcoming Festivals (BKK/Pattaya):\n\n"
                for fest in festivals:
                    name = fest.get("name", "")
                    date = fest.get("date", "")
                    msg += f"• {name}\n  📅 {date}\n"

            text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
            if event.reply_token:
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[text_msg],
                        notificationDisabled=False,
                    )
                )
        except Exception as e:
            logger.error(f"📰 Error sending festivals: {e}", exc_info=True)
            await self._send_error_message(event, line_bot_api)

    async def _send_resources(self, event: MessageEvent, line_bot_api: MessagingApi, language: str):
        """Send API resources list."""
        msg = ""
        if language == "th":
            msg = "📚 แหล่งข้อมูล / Resources:\n\n"
            msg += "🌡️ สภาพอากาศ: Open-Meteo\n"
            msg += "https://open-meteo.com\n\n"
            msg += "📰 ข่าว:\n"
            msg += "• ThaiPBS: https://news.thaipbs.or.th\n"
            msg += "• Bangkok Post: https://bangkokpost.com\n"
            msg += "• The Nation: https://nationthailand.com\n\n"
            msg += "ขอบคุณที่ใช้บริการ! 🙏"
        else:
            msg = "📚 Resources:\n\n"
            msg += "🌡️ Weather: Open-Meteo\n"
            msg += "https://open-meteo.com\n\n"
            msg += "📰 News:\n"
            msg += "• ThaiPBS: https://news.thaipbs.or.th/en\n"
            msg += "• Bangkok Post: https://bangkokpost.com\n"
            msg += "• The Nation: https://nationthailand.com\n\n"
            msg += "Thank you for using TeacherBOY! 🙏"
        
        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )


    async def _send_trigger_translation(
        self, event: MessageEvent, line_bot_api: MessagingApi, text: str
    ):
        """Translate the trigger word to the other language (group/non-friend or private)."""
        trigger_text = self._normalize_trigger_text(text)
        if trigger_text == "news":
            translated = "ข่าว"
            msg = f"news → {translated}"
        else:
            translated = "news"
            msg = f"{text.strip()} → {translated}"

        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)

        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _send_invalid_choice(self, event: MessageEvent, line_bot_api: MessagingApi, language: str):
        """Send invalid choice message."""
        if language == "th":
            msg = "❌ กรุณาเลือก 1-5 (หัวข้อข่าว)"
        else:
            msg = "❌ Please pick 1-5 (headlines)"
        
        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _send_rate_limit_message(
        self, event: MessageEvent, line_bot_api: MessagingApi, 
        max_requests: int, remaining: int, reset_seconds: int
    ):
        """Send rate limit message to user."""
        reset_minutes = (reset_seconds + 59) // 60  # Round up to nearest minute
        
        msg = (
            f"⏳ Only {max_requests} news request per hour\n"
            f"Total requests left: {remaining}\n\n"
            f"Try again in ~{reset_minutes} minute{'s' if reset_minutes != 1 else ''}\n\n"
            f"คุณขอข่าวเร็วเกินไปค่ะ! 📰\n"
            f"เหลืออีก: {remaining} ครั้ง\n"
            f"กรุณารอ ~{reset_minutes} นาที 😊"
        )
        
        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _send_error_message(self, event: MessageEvent, line_bot_api: MessagingApi):
        """Send error message when something goes wrong."""
        msg = "❌ Sorry, something went wrong. Please try again later.\n"
        msg += "ขออภัย เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง"
        
        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )
