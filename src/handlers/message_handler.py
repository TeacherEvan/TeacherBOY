"""Handler for processing incoming LINE text messages."""

import logging
import asyncio
from linebot import LineBotApi
from linebot.models import TextSendMessage, FlexSendMessage

from src.services.translation_service import translation_service
from src.utils.flex import create_translation_flex

logger = logging.getLogger(__name__)


async def handle_text_message(event, line_bot_api: LineBotApi):
    """
    Handle incoming text messages and provide translation.
    
    Args:
        event: LINE message event
        line_bot_api: LINE Bot API instance
    """
    user_message = event.message.text
    logger.info(f"Received message: {user_message}")
    
    # Auto-translate the message
    translated_text, detected_lang = await translation_service.auto_translate(user_message)
    
    if translated_text and detected_lang:
        # Create Flex Message
        target_lang = "en" if detected_lang == "th" else "th"
        flex_content = create_translation_flex(
            user_message, 
            translated_text, 
            detected_lang, 
            target_lang
        )
        
        message = FlexSendMessage(
            alt_text=f"Translation: {translated_text[:20]}...",
            contents=flex_content
        )
        logger.info(f"Sending translation: {translated_text}")
    else:
        message = TextSendMessage(text="Sorry, I couldn't translate your message. Please try again.")
        logger.warning("Translation failed")
    
    # Reply to user (Run sync API call in thread pool)
    try:
        await asyncio.to_thread(
            line_bot_api.reply_message,
            event.reply_token,
            message
        )
    except Exception as e:
        logger.error(f"Error sending reply: {str(e)}")
