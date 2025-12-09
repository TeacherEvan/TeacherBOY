"""Handler for processing incoming LINE text messages."""

import logging
from linebot import LineBotApi
from linebot.models import TextSendMessage

from src.services.translation_service import translation_service

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
    
    if translated_text:
        # Format response with detected language info
        lang_name = "Thai" if detected_lang == "th" else "English"
        target_lang_name = "English" if detected_lang == "th" else "Thai"
        
        response = f"🌐 Detected: {lang_name}\n📝 {target_lang_name} Translation:\n\n{translated_text}"
        
        logger.info(f"Sending translation: {translated_text}")
    else:
        response = "Sorry, I couldn't translate your message. Please try again."
        logger.warning("Translation failed")
    
    # Reply to user
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=response)
    )


# Synchronous wrapper for the handler (LINE SDK expects sync function)
def handle_text_message_sync(event, line_bot_api: LineBotApi):
    """Synchronous wrapper for async handler."""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    
    loop.run_until_complete(handle_text_message(event, line_bot_api))
