"""Handler for processing incoming LINE text messages using SDK v3."""

import logging
import asyncio
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from src.services.translation_service import translation_service

logger = logging.getLogger(__name__)


def create_translation_flex_dict(
    original_text: str,
    translated_text: str,
    source_lang: str,
    target_lang: str
) -> dict:
    """
    Create a Flex Message bubble dict for translation result.
    
    Args:
        original_text: The original message text
        translated_text: The translated text
        source_lang: Source language code ('th' or 'en')
        target_lang: Target language code ('th' or 'en')
        
    Returns:
        Dict representing FlexBubble
    """
    primary_color = "#0D8186"
    secondary_color = "#aaaaaa"
    
    source_label = "Thai" if source_lang == "th" else "English"
    target_label = "English" if source_lang == "th" else "Thai"
    
    source_flag = "🇹🇭" if source_lang == "th" else "🇬🇧"
    target_flag = "🇬🇧" if source_lang == "th" else "🇹🇭"

    return {
        "type": "bubble",
        "size": "giga",
        "header": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "contents": [
                        {"type": "text", "text": "TeacherBOY", "weight": "bold", "color": primary_color, "size": "sm"},
                        {"type": "text", "text": "TRANSLATOR", "weight": "bold", "color": secondary_color, "size": "xxs", "align": "end", "gravity": "center"}
                    ]
                }
            ]
        },
        "body": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "md",
                    "contents": [
                        {"type": "text", "text": source_flag, "size": "lg", "flex": 0},
                        {"type": "text", "text": source_label, "weight": "bold", "size": "sm", "margin": "sm", "gravity": "center"}
                    ]
                },
                {"type": "text", "text": original_text, "wrap": True, "color": "#555555", "size": "sm", "margin": "sm"},
                {"type": "separator", "margin": "xl", "color": "#eeeeee"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xl",
                    "contents": [
                        {"type": "text", "text": target_flag, "size": "lg", "flex": 0},
                        {"type": "text", "text": target_label, "weight": "bold", "size": "sm", "margin": "sm", "gravity": "center", "color": primary_color}
                    ]
                },
                {"type": "text", "text": translated_text, "wrap": True, "weight": "regular", "size": "md", "margin": "sm", "color": "#000000"}
            ]
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {"type": "text", "text": "Powered by LibreTranslate", "size": "xxs", "color": "#aaaaaa", "align": "center"}
            ]
        }
    }


async def handle_join_event(event, line_bot_api: MessagingApi):
    """
    Handle bot joining a group or multi-person chat.
    
    Args:
        event: LINE join event
        line_bot_api: MessagingApi instance (v3)
    """
    source_type = event.source.type
    
    if source_type == "group":
        chat_id = event.source.group_id
        logger.info(f"Bot joined group: {chat_id}")
    elif source_type == "room":
        chat_id = event.source.room_id
        logger.info(f"Bot joined room: {chat_id}")
    else:
        chat_id = "unknown"
        logger.info(f"Bot joined unknown chat type: {source_type}")
    
    welcome_text = (
        "👋 Hello! I'm TeacherBOY 🇹🇭↔️🇬🇧\n\n"
        "I automatically translate:\n"
        "• Thai → English\n"
        "• English → Thai\n\n"
        "Just send any message and I'll translate it!"
    )
    
    try:
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(  # type: ignore[call-arg]
                replyToken=event.reply_token,
                messages=[TextMessage(text=welcome_text)]  # type: ignore[call-arg]
            )
        )
    except Exception as e:
        logger.error(f"Error sending welcome message: {str(e)}")


async def handle_leave_event(event, line_bot_api: MessagingApi):
    """Handle bot leaving a group."""
    source_type = event.source.type
    if source_type == "group":
        logger.info(f"Bot left group: {event.source.group_id}")
    elif source_type == "room":
        logger.info(f"Bot left room: {event.source.room_id}")


async def handle_member_joined_event(event, line_bot_api: MessagingApi):
    """Handle new member joining the group."""
    logger.info(f"Member joined: {event.joined.members}")
    
    welcome_text = "Welcome! 👋 I can translate Thai ↔️ English for you."
    try:
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(  # type: ignore[call-arg]
                replyToken=event.reply_token,
                messages=[TextMessage(text=welcome_text)]  # type: ignore[call-arg]
            )
        )
    except Exception as e:
        logger.error(f"Error sending member welcome: {str(e)}")


async def handle_member_left_event(event, line_bot_api: MessagingApi):
    """Handle member leaving the group."""
    logger.info(f"Member left: {event.left.members}")


async def handle_text_message(event, line_bot_api: MessagingApi):
    """
    Handle incoming text messages and provide translation.
    
    Args:
        event: LINE message event
        line_bot_api: MessagingApi instance (v3)
    """
    user_message = event.message.text
    logger.info(f"Received message: {user_message}")
    
    # Auto-translate the message
    translated_text, detected_lang = await translation_service.auto_translate(user_message)
    
    if translated_text and detected_lang:
        # Create Flex Message dict
        target_lang = "en" if detected_lang == "th" else "th"
        flex_dict = create_translation_flex_dict(
            user_message, 
            translated_text, 
            detected_lang, 
            target_lang
        )
        
        alt_text = f"Translation: {translated_text[:40]}..."
        message = FlexMessage(  # type: ignore[call-arg]
            altText=alt_text, 
            contents=FlexContainer.from_dict(flex_dict)
        )
        logger.info(f"Sending translation: {translated_text}")
    else:
        message = TextMessage(text="Sorry, I couldn't translate your message. Please try again.")  # type: ignore[call-arg]
        logger.warning("Translation failed")
    
    # Reply to user using v3 SDK
    try:
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(  # type: ignore[call-arg]
                replyToken=event.reply_token,
                messages=[message]
            )
        )
    except Exception as e:
        logger.error(f"Error sending reply: {str(e)}")
