"""Handler for processing incoming LINE text messages using SDK v3."""

import logging
import asyncio
import re
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    FlexMessage,
    FlexContainer,
)

from src.services.translation_service import translation_service
from src.services.google_translation import google_translation_service
from src.services.session_manager import session_manager

logger = logging.getLogger(__name__)


def contains_thai(text: str) -> bool:
    """Check if text contains Thai characters."""
    return bool(re.search(r"[\u0E00-\u0E7F]", text))


def is_sleep_command(text: str) -> bool:
    """Check if text is a sleep command (amen)."""
    text_lower = text.lower().strip()
    sleep_pattern = r"^amen[\s.!]*$"
    return bool(re.search(sleep_pattern, text_lower))


def is_wake_command(text: str) -> bool:
    """Check if text is a wake command (Dear Zeus alone)."""
    return text.lower().strip() == "dear zeus"


def is_exit_command(text: str) -> bool:
    """Check if text is an exit command (same as sleep command)."""
    return is_sleep_command(text)


def create_translation_flex_dict(
    original_text: str, translated_text: str, source_lang: str, target_lang: str
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
                        {
                            "type": "text",
                            "text": "Zeus",
                            "weight": "bold",
                            "color": primary_color,
                            "size": "sm",
                        },
                        {
                            "type": "text",
                            "text": "TRANSLATOR",
                            "weight": "bold",
                            "color": secondary_color,
                            "size": "xxs",
                            "align": "end",
                            "gravity": "center",
                        },
                    ],
                }
            ],
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
                        {
                            "type": "text",
                            "text": source_label,
                            "weight": "bold",
                            "size": "sm",
                            "margin": "sm",
                            "gravity": "center",
                        },
                    ],
                },
                {
                    "type": "text",
                    "text": original_text,
                    "wrap": True,
                    "color": "#555555",
                    "size": "sm",
                    "margin": "sm",
                },
                {"type": "separator", "margin": "xl", "color": "#eeeeee"},
                {
                    "type": "box",
                    "layout": "horizontal",
                    "margin": "xl",
                    "contents": [
                        {"type": "text", "text": target_flag, "size": "lg", "flex": 0},
                        {
                            "type": "text",
                            "text": target_label,
                            "weight": "bold",
                            "size": "sm",
                            "margin": "sm",
                            "gravity": "center",
                            "color": primary_color,
                        },
                    ],
                },
                {
                    "type": "text",
                    "text": translated_text,
                    "wrap": True,
                    "weight": "regular",
                    "size": "md",
                    "margin": "sm",
                    "color": "#000000",
                },
            ],
        },
        "footer": {
            "type": "box",
            "layout": "vertical",
            "contents": [
                {
                    "type": "text",
                    "text": "Powered by LibreTranslate",
                    "size": "xxs",
                    "color": "#aaaaaa",
                    "align": "center",
                }
            ],
        },
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

    # Silent join - only log
    pass


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

    # Silent join - only log
    pass


async def handle_member_left_event(event, line_bot_api: MessagingApi):
    """Handle member leaving the group."""
    logger.info(f"Member left: {event.left.members}")


async def handle_text_message(event, line_bot_api: MessagingApi):
    """
    Handle incoming text messages with smart Thai detection and session management.

    This handler auto-detects Thai characters and starts translation mode,
    keeps translating continuously until the user says "amen" (sleeping the chat
    for 24 hours), and can be woken up by sending "Dear Zeus" alone.

    Args:
        event: LINE message event containing the incoming text message.
        line_bot_api: MessagingApi instance (v3) used to send replies.
    """
    text = event.message.text
    reply_token = event.reply_token

    # Get chat ID (works for 1-on-1, group, and room chats)
    source = event.source
    if source.type == "group":
        chat_id = source.group_id
    elif source.type == "room":
        chat_id = source.room_id
    else:
        chat_id = source.user_id

    logger.info(f"Message from chat {chat_id}: {text[:50]}...")

    # Check for exit command
    if is_exit_command(text):
        if session_manager.is_session_active(chat_id):
            session_manager.end_session(chat_id)
            goodbye_messages = [
                TextMessage(text="ลาก่อน 👋 (Goodbye!)"),  # type: ignore[call-arg]
                TextMessage(text="Translation mode ended. Send Thai text to start again!"),  # type: ignore[call-arg]
            ]
            try:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(  # type: ignore[call-arg]
                        replyToken=reply_token, messages=goodbye_messages
                    ),
                )
                logger.info(f"Ended translation session for chat {chat_id}")
            except Exception as e:
                logger.error(f"Error sending goodbye: {str(e)}")
            return
        else:
            # Not in a session, just ignore
            return

    # Auto-detect Thai and start session if not active
    if contains_thai(text) and not session_manager.is_session_active(chat_id):
        session_manager.start_session(chat_id, source.user_id)
        logger.info(f"Auto-started translation mode for chat {chat_id} (Thai detected)")

    # Only translate if session is active
    if not session_manager.is_session_active(chat_id):
        # Not in translation mode, ignore silently
        return

    # Increment message counter
    session_manager.increment_message_count(chat_id)

    # Try Google Translate first, fall back to LibreTranslate
    translated_text = None
    source_lang = None

    if google_translation_service.is_configured():
        logger.info("Using Google Cloud Translation API")
        translated_text = await google_translation_service.auto_translate(text)
        if translated_text:
            # Prefer cheap heuristic for source language to avoid double-calling Google
            source_lang = "th" if contains_thai(text) else "en"

    if not translated_text:
        logger.info("Using LibreTranslate (fallback)")
        translated_text, source_lang = await translation_service.auto_translate(text)

    if not translated_text or not source_lang:
        error_msg = TextMessage(text="Sorry, translation failed. Please try again.")  # type: ignore[call-arg]
        try:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(  # type: ignore[call-arg]
                    replyToken=reply_token, messages=[error_msg]
                ),
            )
        except Exception as e:
            logger.error(f"Error sending error message: {str(e)}")
        return

    target_lang = "en" if source_lang == "th" else "th"

    # Create Flex Message
    flex_dict = create_translation_flex_dict(
        original_text=text,
        translated_text=translated_text,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    # Use FlexContainer.from_dict (SDK v3)
    flex_container = FlexContainer.from_dict(flex_dict)
    flex_message = FlexMessage(  # type: ignore[call-arg]
        altText=f"Translation: {translated_text[:50]}...", contents=flex_container
    )

    try:
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(  # type: ignore[call-arg]
                replyToken=reply_token, messages=[flex_message]
            ),
        )
        logger.info(f"Translation sent: {source_lang} -> {target_lang}")
    except Exception as e:
        logger.error(f"Error sending translation: {str(e)}")
