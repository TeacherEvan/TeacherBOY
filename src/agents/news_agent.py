"""News agent - Handles weather, air quality, and news headlines in multi-step flow."""

import logging
import re
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

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

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Text is news trigger ("news" or "ข่าว")
        2. Chat is in active news flow
        """
        # Ignore LINE system messages
        if self._is_line_system_message(text):
            return False

        chat_id = self._get_chat_id(event)

        # Handle if in active news flow
        if news_session_manager.is_in_news_flow(chat_id):
            return True

        # Handle if news trigger
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
            # Step 1: News trigger - start flow
            if not session and self._is_news_trigger(text):
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
        
        msg = f"📰 ข่าวและสภาพอากาศ\n\n"
        msg += f"🌡️ อุณหภูมิ (Bangkok): {temp}°C\n"
        msg += f"💨 PM2.5 (Bangkok): {pm25}\n"
        msg += f"🌧️ จะฝนตกใน 5 ชั่วโมงข้างหน้า: {rain_text}\n\n"
        msg += f"🍃 กัญชา: {LEGAL_INFO['cannabis']['th']}\n"
        msg += f"🚭 บุหรี่ไฟฟ้า: {LEGAL_INFO['ecig']['th']}\n"
        msg += f"🍺 แอลกอฮอล์: {LEGAL_INFO['alcohol']['th']}\n\n"
        msg += f"📰 ข่าวสำคัญวันนี้:\n"
        
        for i, headline in enumerate(headlines[:5], 1):
            title = headline.get("title", "ไม่มีหัวข้อ")[:80]
            msg += f"{i} - {title}\n"
        
        msg += f"\n💡 กด 1-5 เพื่ออ่านข่าวเพิ่มเติม\n💡 กด 9 เพื่อดูแหล่งข้อมูล"
        
        return msg

    def _format_menu_english(self, weather: dict, headlines: list) -> str:
        """Format main menu in English."""
        temp = weather.get("temperature", "N/A")
        pm25 = weather.get("pm25", "N/A")
        will_rain = weather.get("will_rain")
        rain_text = "Yes" if will_rain else "No" if will_rain is not None else "N/A"
        
        msg = f"📰 News & Weather\n\n"
        msg += f"🌡️ Temperature (Bangkok): {temp}°C\n"
        msg += f"💨 PM2.5 (Bangkok): {pm25}\n"
        msg += f"🌧️ Will it rain in next 5 hours: {rain_text}\n\n"
        msg += f"🍃 Cannabis: {LEGAL_INFO['cannabis']['en']}\n"
        msg += f"🚭 E-Cigarettes: {LEGAL_INFO['ecig']['en']}\n"
        msg += f"🍺 Alcohol: {LEGAL_INFO['alcohol']['en']}\n\n"
        msg += f"📰 Top 5 Headlines Today:\n"
        
        for i, headline in enumerate(headlines[:5], 1):
            title = headline.get("title", "No title")[:80]
            msg += f"{i} - {title}\n"
        
        msg += f"\n💡 Press 1-5 to read more\n💡 Press 9 for resources"
        
        return msg

    async def _handle_main_menu(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi, 
        chat_id: str, session: dict
    ) -> bool:
        """Handle main menu selections (1-5 for headlines, 9 for resources)."""
        text_clean = text.strip()
        
        # Handle headline selection (1-5)
        if text_clean in ["1", "2", "3", "4", "5", "๑", "๒", "๓", "๔", "๕"]:
            # Normalize Thai numerals
            thai_to_arabic = {"๑": "1", "๒": "2", "๓": "3", "๔": "4", "๕": "5"}
            try:
                index = int(thai_to_arabic.get(text_clean, text_clean)) - 1
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
        
        # Handle resources (9)
        elif text_clean in ["9", "๙"]:
            await self._send_resources(event, line_bot_api, session["language"])
            news_session_manager.end_news_flow(chat_id)
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
            msg = f"📰 {title}\n\n"
            if url:
                msg += f"🔗 อ่านเพิ่มเติม: {url}\n\n"
            msg += "กดข้อความใดก็ได้เพื่อกลับไปเมนู"
        else:
            msg = f"📰 {title}\n\n"
            if url:
                msg += f"🔗 Read more: {url}\n\n"
            msg += "Send any message to return to menu"
        
        text_msg = TextMessage(text=msg, quickReply=None, quoteToken=None)
        
        if event.reply_token:
            line_bot_api.reply_message(
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[text_msg],
                    notificationDisabled=False,
                )
            )

    async def _send_resources(self, event: MessageEvent, line_bot_api: MessagingApi, language: str):
        """Send API resources list."""
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

    async def _send_invalid_choice(self, event: MessageEvent, line_bot_api: MessagingApi, language: str):
        """Send invalid choice message."""
        if language == "th":
            msg = "❌ กรุณาเลือกตัวเลือกที่ถูกต้อง (1-5 หรือ 9)"
        else:
            msg = "❌ Please select a valid option (1-5 or 9)"
        
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
