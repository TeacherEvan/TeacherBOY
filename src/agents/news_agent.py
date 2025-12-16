"""News agent - Handles weather, air quality, and news headlines in multi-step flow."""

import logging
import re
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

logger = logging.getLogger(__name__)

# Legal information constants (as of Dec 2024 - update if laws change)
LEGAL_INFO = {
    "cannabis": {"th": "ถูกกฎหมาย (Legal)", "en": "Legal"},
    "ecig": {"th": "*ผิดกฎหมาย* (NOT LEGAL)", "en": "*NOT LEGAL*"},
    "alcohol": {"th": "ควรระวัง (Prescriptive)", "en": "Prescriptive"},
}


class NewsAgent(BaseAgent):
    """Agent for handling multi-step news conversations with weather and headlines."""

    def __init__(self, news_data_service: NewsDataService):
        super().__init__(
            name="NewsAgent",
            description="Weather, air quality, and news headlines for Bangkok",
        )
        self.news_service = news_data_service

    def get_priority(self) -> int:
        """News agent priority - between Translation (10) and Calendar (20)."""
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

    def _is_news_trigger(self, text: str) -> bool:
        """Check if text is a news trigger word."""
        text_clean = text.lower().strip()
        return text_clean in ["news", "ข่าว"]

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
            return False

        try:
            line_bot_api.get_profile(user_id)
            return True
        except ApiException:
            logger.info("📰 Non-friend user attempted news flow", exc_info=False)
            return False
        except Exception:
            logger.info("📰 Unable to verify friendship; treating as non-friend", exc_info=False)
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

        try:
            # Private chats: respond with translation of trigger only
            if not self._is_group_chat(event):
                if self._is_news_trigger(text):
                    await self._send_trigger_translation(event, line_bot_api, text)
                    return True
                return False

            # Step 1: News trigger - start flow
            if not session and self._is_news_trigger(text):
                is_friend = await self._is_friend(event, line_bot_api)
                if not is_friend:
                    await self._send_trigger_translation(event, line_bot_api, text)
                    return True

                news_session_manager.start_news_flow(chat_id)
                await self._send_language_selection(event, line_bot_api)
                return True

            # Step 2: Language selection
            if session and session["step"] == "language_selection":
                if text.strip() in ["1", "๑"]:  # Thai
                    news_session_manager.set_language(chat_id, "th")
                    await self._send_main_menu(event, line_bot_api, "th")
                    return True
                elif text.strip() in ["2", "๒"]:  # English
                    news_session_manager.set_language(chat_id, "en")
                    await self._send_main_menu(event, line_bot_api, "en")
                    return True
                else:
                    await self._send_invalid_choice(event, line_bot_api, session["language"])
                    return True

            # Step 3: Main menu - handle selections
            if session and session["step"] == "main_menu":
                return await self._handle_main_menu(event, text, line_bot_api, chat_id, session)

            # Step 4: Headline detail - return to menu
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
        
        # Fetch weather and news data
        weather_data = await self.news_service.get_weather_data()
        headlines = await self.news_service.get_news_headlines(language)
        
        # Cache data in session
        news_session_manager.set_cached_data(chat_id, {
            "weather": weather_data,
            "headlines": headlines
        })
        
        # Format message
        if language == "th":
            message = self._format_menu_thai(weather_data, headlines)
        else:
            message = self._format_menu_english(weather_data, headlines)
        
        text_msg = TextMessage(text=message, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    def _format_menu_thai(self, weather: dict, headlines: list) -> str:
        """Format main menu in Thai."""
        temp = weather.get("temperature", "N/A")
        pm25 = weather.get("pm25", "N/A")
        will_rain = weather.get("will_rain")
        rain_text = "ใช่ (Yes)" if will_rain else "ไม่ (No)" if will_rain is not None else "N/A"
        
        msg = "📰 ข่าว Bangkok (ทั้งหมด 8 หัวข้อ)\n\n"
        msg += f"1️⃣ 🌡️ อุณหภูมิ: {temp}°C | 💨 PM2.5: {pm25}\n"
        msg += f"2️⃣ 🌧️ 5 ชม.ข้างหน้า: {rain_text}\n"
        msg += f"3️⃣ 🍃 กัญชา: {LEGAL_INFO['cannabis']['th']}\n"
        msg += f"4️⃣ 🚭 บุหรี่ไฟฟ้า: {LEGAL_INFO['ecig']['th']}\n"
        msg += f"5️⃣ 🍺 แอลกอฮอล์: {LEGAL_INFO['alcohol']['th']}\n"
        msg += "6️⃣ 🎨 สีแม่น้ำ + 🌅 อาทิตย์\n"
        msg += "7️⃣ 📅 วันหยุด + 🏛️ ตลาด\n"
        msg += "8️⃣ ₿ Bitcoin + 💱 อัตราแลก\n\n"
        msg += "📰 หัวข้อข่าว:\n"

        for i, headline in enumerate(headlines[:5], 1):
            title = headline.get("title", "ไม่มีหัวข้อ")[:80]
            msg += f"{i}. {title}\n"
        
        return msg

    def _format_menu_english(self, weather: dict, headlines: list) -> str:
        """Format main menu in English."""
        temp = weather.get("temperature", "N/A")
        pm25 = weather.get("pm25", "N/A")
        will_rain = weather.get("will_rain")
        rain_text = "Yes" if will_rain else "No" if will_rain is not None else "N/A"
        
        msg = "📰 Bangkok News (8 items)\n\n"
        msg += f"1️⃣ 🌡️ Temp: {temp}°C | 💨 PM2.5: {pm25}\n"
        msg += f"2️⃣ 🌧️ Next 5h: {rain_text}\n"
        msg += f"3️⃣ 🍃 Cannabis: {LEGAL_INFO['cannabis']['en']}\n"
        msg += f"4️⃣ 🚭 E-Cigs: {LEGAL_INFO['ecig']['en']}\n"
        msg += f"5️⃣ 🍺 Alcohol: {LEGAL_INFO['alcohol']['en']}\n"
        msg += "6️⃣ 🎨 Color + 🌅 Sunset\n"
        msg += "7️⃣ 📅 Holidays + 🏛️ Markets\n"
        msg += "8️⃣ ₿ Bitcoin + 💱 Exchange\n\n"
        msg += "📰 Headlines:\n"

        for i, headline in enumerate(headlines[:5], 1):
            title = headline.get("title", "No title")[:80]
            msg += f"{i}. {title}\n"
        
        return msg

    async def _handle_main_menu(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi, 
        chat_id: str, session: dict
    ) -> bool:
        """Handle main menu selections (1-8)."""
        text_clean = text.strip()
        
        # Normalize Thai numerals to Arabic numerals
        thai_to_arabic = {
            "๑": "1", "๒": "2", "๓": "3", "๔": "4", "๕": "5",
            "๖": "6", "๗": "7", "๘": "8"
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
        
        # Handle item 6: Color + Sunset/Sunrise
        elif normalized == "6":
            await self._send_color_sunset_sunrise(event, line_bot_api, session["language"])
            return True
        
        # Handle item 7: Holidays + Markets
        elif normalized == "7":
            await self._send_holidays_markets(event, line_bot_api, session["language"])
            return True
        
        # Handle item 8: Bitcoin + Exchange Rates
        elif normalized == "8":
            await self._send_crypto_exchange(event, line_bot_api, session["language"])
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
        text_lower = text.lower().strip()
        if text_lower == "news":
            translated = "ข่าว"
        else:
            translated = "news"

        msg = f"news → {translated}" if text_lower == "news" else f"ข่าว → {translated}"

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
            msg = "❌ กรุณาเลือก 1-5"
        else:
            msg = "❌ Pick 1-5"
        
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
