"""Translation agent - Handles Thai/English translation with session management."""

import logging
import re
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
)

from .base_agent import BaseAgent
from src.services.translation_service import translation_service
from src.services.google_translation import google_translation_service
from src.services.session_manager import session_manager

logger = logging.getLogger(__name__)


class TranslationAgent(BaseAgent):
    """Agent for handling Thai/English translation with smart session management."""
    
    def __init__(self):
        super().__init__(
            name="TranslationAgent",
            description="Thai/English translation with continuous session mode"
        )
    
    def get_priority(self) -> int:
        """Translation has high priority."""
        return 10
    
    def contains_thai(self, text: str) -> bool:
        """Check if text contains Thai characters."""
        return bool(re.search(r'[\u0E00-\u0E7F]', text))
    
    def is_exit_command(self, text: str) -> bool:
        """Check if text is an exit command."""
        text_lower = text.lower().strip()
        exit_patterns = [
            r'thanks?\s+brown',
            r'thank\s+you\s+brown',
            r'thx\s+brown',
            r'ty\s+brown',
            r'ขอบคุณ\s*brown',
            r'ขอบใจ\s*brown',
        ]
        return any(re.search(pattern, text_lower) for pattern in exit_patterns)
    
    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Thai text detected (auto-start session)
        2. Session is active for this chat
        3. Exit command (to properly close session)
        """
        chat_id = self._get_chat_id(event)
        
        # Always handle exit commands if session is active
        if self.is_exit_command(text):
            return session_manager.is_session_active(chat_id)
        
        # Handle if Thai detected or session is active
        return self.contains_thai(text) or session_manager.is_session_active(chat_id)
    
    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process translation request."""
        chat_id = self._get_chat_id(event)
        user_id = event.source.user_id
        
        try:
            # Handle exit command
            if self.is_exit_command(text):
                session_manager.end_session(chat_id)
                goodbye_message = self._create_goodbye_message()
                
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[goodbye_message]
                    )
                )
                logger.info(f"✅ Translation session ended for chat {chat_id}")
                return True
            
            # Start session if Thai detected
            if self.contains_thai(text):
                if not session_manager.is_session_active(chat_id):
                    session_manager.start_session(chat_id, user_id)
                    logger.info(f"🔥 Translation session started for chat {chat_id}")
            
            # Translate the message
            translated_text = await self._translate_message(text)
            
            if translated_text:
                # Create Flex Message
                flex_message = self._create_translation_flex(
                    original_text=text,
                    translated_text=translated_text,
                    source_lang="Thai" if self.contains_thai(text) else "English",
                    target_lang="English" if self.contains_thai(text) else "Thai"
                )
                
                line_bot_api.reply_message(
                    ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[flex_message]
                    )
                )
                logger.info(f"✅ Translation sent for chat {chat_id}")
                return True
            else:
                logger.error("Translation failed - no result")
                return False
                
        except Exception as e:
            logger.error(f"❌ Translation agent error: {e}", exc_info=True)
            return False
    
    async def _translate_message(self, text: str) -> str:
        """Translate using Google (primary) or LibreTranslate (fallback)."""
        # Try Google Translate first
        if google_translation_service.is_configured():
            result = await google_translation_service.auto_translate(text)
            if result:
                return result
            logger.warning("⚠️  Google Translate failed, trying LibreTranslate...")
        
        # Fallback to LibreTranslate
        if self.contains_thai(text):
            return await translation_service.translate(text, "th", "en")
        else:
            return await translation_service.translate(text, "en", "th")
    
    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
        if hasattr(event.source, 'group_id'):
            return f"group_{event.source.group_id}"
        elif hasattr(event.source, 'room_id'):
            return f"room_{event.source.room_id}"
        else:
            return f"user_{event.source.user_id}"
    
    def _create_translation_flex(self, original_text: str, translated_text: str,
                                 source_lang: str, target_lang: str) -> FlexMessage:
        """Create Flex Message for translation result."""
        flex_dict = {
            "type": "bubble",
            "hero": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "🌐 Translation",
                        "weight": "bold",
                        "size": "xl",
                        "color": "#ffffff"
                    }
                ],
                "backgroundColor": "#4A90E2",
                "paddingAll": "20px"
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"📝 {source_lang}",
                                "size": "sm",
                                "color": "#888888",
                                "margin": "none"
                            },
                            {
                                "type": "text",
                                "text": original_text,
                                "size": "md",
                                "wrap": True,
                                "margin": "sm"
                            }
                        ],
                        "margin": "none"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "box",
                        "layout": "vertical",
                        "contents": [
                            {
                                "type": "text",
                                "text": f"✨ {target_lang}",
                                "size": "sm",
                                "color": "#4A90E2",
                                "margin": "md"
                            },
                            {
                                "type": "text",
                                "text": translated_text,
                                "size": "md",
                                "wrap": True,
                                "margin": "sm",
                                "weight": "bold"
                            }
                        ]
                    }
                ],
                "spacing": "md"
            },
            "footer": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "💡 Say 'thanks Brown' to stop translating",
                        "size": "xs",
                        "color": "#888888",
                        "align": "center"
                    }
                ],
                "paddingAll": "10px"
            }
        }
        
        return FlexMessage(alt_text="Translation", contents=flex_dict)
    
    def _create_goodbye_message(self) -> FlexMessage:
        """Create goodbye Flex Message."""
        flex_dict = {
            "type": "bubble",
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "👋 ลาก่อน (Goodbye!)",
                        "weight": "bold",
                        "size": "xl",
                        "align": "center",
                        "color": "#4A90E2"
                    },
                    {
                        "type": "text",
                        "text": "Translation mode OFF",
                        "size": "sm",
                        "color": "#888888",
                        "align": "center",
                        "margin": "md"
                    },
                    {
                        "type": "separator",
                        "margin": "lg"
                    },
                    {
                        "type": "text",
                        "text": "Send Thai text anytime to start again! 🚀",
                        "size": "sm",
                        "color": "#555555",
                        "align": "center",
                        "margin": "lg",
                        "wrap": True
                    }
                ],
                "paddingAll": "20px"
            }
        }
        
        return FlexMessage(alt_text="Session ended", contents=flex_dict)
