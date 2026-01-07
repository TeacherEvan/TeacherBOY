"""
Image Analyzer Agent - General purpose image Q&A using vision AI.

This agent allows users to submit images and ask questions about them.
Unlike the Profiler (which focuses on psychological analysis), this agent
handles general image-based questions like:
- "What's on this menu?"
- "What does this sign say?"
- "What products are shown here?"

Flow:
1. User: "Zeus analyze this" / "analyze image"
2. Zeus: "Provide me with thy image to examine (60 seconds)"
3. User: [sends image]
4. Zeus: "What is thy question about this image?"
5. User: "What would be most enjoyable on this menu to a westerner?"
6. Zeus: [analyzes image and answers question]

Calendar Integration:
When dates are detected in an image (schedules, announcements, etc.),
the agent can offer to add them to the user's calendar with reminders.
"""

import asyncio
import logging
import base64
import re
import json
from typing import Optional, List, Dict, Any
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.messaging import (
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
    QuickReply,
    QuickReplyItem,
    MessageAction,
    ApiClient,
    Configuration,
)

from .base_agent import BaseAgent
from src.services.image_analyzer_session_manager import (
    image_analyzer_session_manager,
    AnalyzerState,
)
from src.services.github_models_service import github_models_service
from src.services.rate_limiter import RateLimiter
from src.services.metrics_service import metrics_service
from src.services.privilege_service import privilege_service
from src.config import settings
from src.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Rate limiter: 5 analyses per hour per chat (less expensive than profiler)
image_analyzer_rate_limiter = RateLimiter(
    max_requests=5,
    time_window_seconds=3600
)


class ImageAnalyzerAgent(BaseAgent):
    """
    Agent for general-purpose image Q&A.
    
    Uses GPT-4o vision to analyze images and answer user questions.
    """

    # Trigger phrases that start an image analysis session
    TRIGGERS = [
        "zeus analyze",
        "analyze this",
        "analyze image",
        "zeus examine",
        "examine this",
        "examine image",
        "zeus look at",
        "look at this",
    ]

    def __init__(self, http_client=None):
        """
        Initialize ImageAnalyzerAgent.
        
        Args:
            http_client: Shared HTTP client
        """
        super().__init__(
            name="ImageAnalyzerAgent",
            description="General purpose image Q&A using vision AI",
        )
        self.http_client = http_client
        
    def get_priority(self) -> int:
        """
        Image Analyzer priority - just after Profiler (7), before Search (8).
        
        This ensures profiler-specific triggers go to profiler first.
        """
        return 7  # Same as profiler (but profiler checks for "profile" keyword)

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
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

    def _is_trigger(self, text: str) -> bool:
        """Check if text contains a trigger phrase."""
        text_lower = text.lower().strip()
        
        # Don't trigger on profiler-specific phrases
        # These go to ProfilerAgent for facial/psychological analysis
        profiler_keywords = [
            "profile",
            "read face",
            "face analysis",
            "facial analysis",
            "read expression",
            "read emotions",
        ]
        if any(keyword in text_lower for keyword in profiler_keywords):
            return False
        
        return any(trigger in text_lower for trigger in self.TRIGGERS)

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Text message with analyze trigger (start session)
        2. Image message when waiting for image
        3. Text message when waiting for question
        4. Calendar confirmation response (yes/no add to calendar)
        """
        # Check if GitHub Models is configured (required for vision)
        if not github_models_service.is_configured():
            return False
        
        message = getattr(event, 'message', None)
        if message is None:
            return False
        
        message_type = getattr(message, 'type', None)
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        
        # Case 1: Text message with trigger phrase
        if message_type == 'text' and text and self._is_trigger(text):
            return True
        
        # Case 2: Image message when waiting for image
        if message_type == 'image':
            return image_analyzer_session_manager.is_waiting_for_image(chat_id, user_id)
        
        # Case 3: Text message when waiting for question
        if message_type == 'text' and text:
            if image_analyzer_session_manager.is_waiting_for_question(chat_id, user_id):
                return True
            
            # Case 4: Calendar confirmation response
            text_lower = text.lower().strip()
            if image_analyzer_session_manager.is_waiting_for_calendar_confirmation(chat_id, user_id):
                if any(kw in text_lower for kw in ["yes add", "no skip", "yes", "no", "ใช่", "ไม่"]):
                    return True
        
        return False

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """
        Process image analysis request through multi-step flow.
        
        Args:
            event: LINE message event
            text: Message text (empty for images)
            line_bot_api: LINE Messaging API client
            
        Returns:
            True if handled successfully
        """
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        message = getattr(event, 'message', None)
        message_type = getattr(message, 'type', None) if message else None

        with tracer.start_as_current_span("image_analyzer_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)

            try:
                # Step 1: Trigger phrase - start session
                if message_type == 'text' and self._is_trigger(text):
                    return await self._handle_trigger(event, chat_id, user_id, line_bot_api)
                
                # Step 2: Image received - store and ask for question
                if message_type == 'image':
                    return await self._handle_image(event, chat_id, user_id, line_bot_api, span)
                
                # Step 3: Question received - analyze and respond
                if message_type == 'text' and image_analyzer_session_manager.is_waiting_for_question(chat_id, user_id):
                    return await self._handle_question(event, text, chat_id, user_id, line_bot_api, span)
                
                # Step 4: Calendar confirmation response
                if message_type == 'text' and image_analyzer_session_manager.is_waiting_for_calendar_confirmation(chat_id, user_id):
                    return await self._handle_calendar_confirmation(event, text, chat_id, user_id, line_bot_api)
                
                return False

            except Exception as e:
                logger.error(f"❌ ImageAnalyzerAgent error: {e}", exc_info=True)
                span.set_attribute("analyzer.error", str(e))
                await self._send_error_message(event, line_bot_api, str(e))
                image_analyzer_session_manager.clear_session(chat_id)
                return False

    async def _handle_trigger(
        self, 
        event: MessageEvent, 
        chat_id: str, 
        user_id: Optional[str],
        line_bot_api: MessagingApi
    ) -> bool:
        """Handle trigger phrase - start new session."""
        
        # Check rate limiting (skip for admins)
        if not privilege_service.is_admin(user_id):
            if not image_analyzer_rate_limiter.is_allowed(chat_id, user_id):
                metrics_service.record_rate_limited()
                reset_seconds = image_analyzer_rate_limiter.get_reset_time(chat_id, user_id)
                await self._send_rate_limit_message(event, line_bot_api, reset_seconds)
                return True
        else:
            logger.info(f"🔓 Admin {user_id} bypassed image analyzer rate limit")
        
        # Start session
        image_analyzer_session_manager.start_session(chat_id, user_id)
        
        prompt_msg = TextMessage(
            text="🖼️ Provide me with thy image to examine.\n\n"
                 "(You have 60 seconds to send an image)\n\n"
                 "ส่งภาพที่ต้องการให้วิเคราะห์ (60 วินาที)",
            quickReply=None,
            quoteToken=None,
        )
        
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[prompt_msg],
                    notificationDisabled=False,
                ),
            )
        
        logger.info(f"🖼️ Image analysis session started for chat {chat_id}")
        return True

    async def _handle_image(
        self,
        event: MessageEvent,
        chat_id: str,
        user_id: Optional[str],
        line_bot_api: MessagingApi,
        span
    ) -> bool:
        """Handle image receipt - store and prompt for question."""
        
        message_id = getattr(event.message, "id", None)
        if not isinstance(message_id, str) or not message_id.strip():
            await self._send_error_message(event, line_bot_api, "Could not retrieve image. Please try again.")
            return False
        
        # Download image
        logger.info(f"📸 Downloading image {message_id} from LINE...")
        image_bytes = await self._download_image(message_id)
        
        if not image_bytes:
            await self._send_error_message(event, line_bot_api, "Failed to download image. Please try again.")
            image_analyzer_session_manager.clear_session(chat_id)
            return False
        
        span.set_attribute("image.size_bytes", len(image_bytes))
        
        # Convert to base64 and store in session manager
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        image_data_url = f"data:image/jpeg;base64,{image_base64}"
        
        # CRITICAL: Clear original binary data after encoding
        del image_bytes  # Remove binary data from memory
        del image_base64  # Remove base64 string (data URL is kept in session)
        
        if not image_analyzer_session_manager.store_image(chat_id, image_data_url):
            await self._send_error_message(event, line_bot_api, "Session expired. Please start again with 'Zeus analyze this'.")
            del image_data_url  # Clean up on error
            return False
        
        # Clear data URL reference now that it's stored in session manager
        del image_data_url
        
        # Ask for question
        question_msg = TextMessage(
            text="⚡ Image received! What is thy question about this image?\n\n"
                 "(You have 60 seconds to ask)\n\n"
                 "ได้รับภาพแล้ว! มีคำถามอะไรเกี่ยวกับภาพนี้?",
            quickReply=None,
            quoteToken=None,
        )
        
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[question_msg],
                    notificationDisabled=False,
                ),
            )
        
        logger.info(f"🖼️ Image stored for chat {chat_id}, waiting for question")
        return True

    async def _handle_question(
        self,
        event: MessageEvent,
        question: str,
        chat_id: str,
        user_id: Optional[str],
        line_bot_api: MessagingApi,
        span
    ) -> bool:
        """Handle question - analyze image and respond."""
        
        # Get stored image and question
        image_data, _ = image_analyzer_session_manager.get_image_and_question(chat_id, question)
        
        if not image_data:
            await self._send_error_message(event, line_bot_api, "Session expired or image not found. Please start again.")
            return False
        
        span.set_attribute("question.length", len(question))
        
        # Send "analyzing" message
        await self._send_analyzing_message(event, line_bot_api)
        
        # Build vision message
        messages = self._build_vision_message(image_data, question)
        
        # Call GPT-4o vision
        logger.info(f"🖼️ Analyzing image with question: {question[:50]}...")
        
        model = getattr(settings, 'profiler_model', 'openai/gpt-4o')
        analysis = await github_models_service.chat_completion_with_vision(
            messages=messages,
            model=model,
            temperature=settings.llm_temperature,  # Use configured temperature
            max_tokens=2000,
        )
        
        # CRITICAL: Clear image data from memory after vision API call
        # This prevents sensitive image data from lingering in memory/logs
        del image_data  # Clear base64 data URL
        del messages  # Clear vision API messages containing image
        
        if not analysis:
            status_code, error, model_used = github_models_service.get_last_error()
            logger.error(f"❌ Vision API failed: {status_code} - {error}")
            await self._send_error_message(event, line_bot_api, f"Analysis failed: {error or 'Unknown error'}")
            return False
        
        span.set_attribute("analyzer.success", True)
        span.set_attribute("analysis.length", len(analysis))
        
        # Extract detected dates before formatting (which strips them)
        detected_dates = self._extract_dates_from_analysis(analysis)
        if detected_dates:
            logger.info(f"📅 Detected {len(detected_dates)} dates in image analysis")
            span.set_attribute("dates.detected", len(detected_dates))
        
        # Format and send response (strips date section)
        response = self._format_response(analysis)
        
        # Send via push (reply token already used for "analyzing" message)
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id
        
        if target:
            text_msg = TextMessage(text=response, quickReply=None, quoteToken=None)
            await asyncio.to_thread(
                line_bot_api.push_message,
                PushMessageRequest(
                    to=target,
                    messages=[text_msg],
                    notificationDisabled=False,
                    customAggregationUnits=None,
                ),
            )
        
        logger.info(f"✅ Image analysis sent for chat {chat_id}")
        
        # Offer calendar integration if dates were detected
        if detected_dates:
            await self._offer_calendar_integration(
                event, line_bot_api, detected_dates, user_id, chat_id
            )
        
        return True

    def _build_vision_message(self, image_data_url: str, question: str) -> list:
        """Build the vision API message structure."""
        
        system_prompt = (
            "You are Zeus, the king of the Olympian gods. "
            "You speak with measured wisdom and authority, but with warmth befitting a benevolent ruler. "
            "When analyzing images, provide helpful, practical answers to mortal questions. "
            "Be direct and insightful. Keep responses concise but complete. "
            "For menus, signs, or text: translate and explain if in another language. "
            "For products or items: describe what you see and provide recommendations if asked.\n\n"
            "IMPORTANT: If you detect any dates, deadlines, events, or schedules in the image, "
            "always include a section at the end of your response with the following format:\n"
            "---DATES_DETECTED---\n"
            "[{\"date\": \"YYYY-MM-DD\", \"title\": \"Event title\", \"description\": \"Brief description\"}]\n"
            "---END_DATES---\n"
            "Use ISO format (YYYY-MM-DD) for dates. If the year is not specified, assume the current or next occurrence. "
            "Only include this section if you actually find date-related information in the image."
        )
        
        return [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Examine this image and answer my question:\n\n{question}"
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url
                        }
                    }
                ]
            }
        ]

    def _format_response(self, analysis: str) -> str:
        """Format the analysis response for LINE (strip date detection section)."""
        header = "⚡ ZEUS OBSERVES ⚡\n"
        header += "━" * 20 + "\n\n"
        
        # Strip date detection section from user-visible response
        clean_analysis = self._strip_dates_section(analysis)
        
        # Truncate if too long (LINE limit is 5000 chars)
        max_content = 4800 - len(header)
        if len(clean_analysis) > max_content:
            clean_analysis = clean_analysis[:max_content] + "\n\n[Response truncated]"
        
        return header + clean_analysis

    def _strip_dates_section(self, analysis: str) -> str:
        """Remove the dates detection section from analysis text."""
        # Remove the dates section that's meant for internal processing
        pattern = r'---DATES_DETECTED---.*?---END_DATES---'
        return re.sub(pattern, '', analysis, flags=re.DOTALL).strip()

    def _extract_dates_from_analysis(self, analysis: str) -> List[Dict[str, str]]:
        """
        Extract detected dates from the analysis response.
        
        Returns:
            List of dicts with 'date', 'title', 'description' keys
        """
        try:
            # Look for the dates section
            match = re.search(r'---DATES_DETECTED---\s*(.+?)\s*---END_DATES---', analysis, re.DOTALL)
            if not match:
                return []
            
            dates_json = match.group(1).strip()
            
            # Parse JSON
            dates = json.loads(dates_json)
            
            if isinstance(dates, list):
                # Validate each date entry
                valid_dates = []
                for entry in dates:
                    if isinstance(entry, dict) and 'date' in entry and 'title' in entry:
                        valid_dates.append({
                            'date': str(entry.get('date', '')),
                            'title': str(entry.get('title', 'Untitled Event')),
                            'description': str(entry.get('description', '')),
                        })
                return valid_dates
            
            return []
            
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"⚠️ Failed to parse dates from analysis: {e}")
            return []

    async def _offer_calendar_integration(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        detected_dates: List[Dict[str, str]],
        user_id: Optional[str],
        chat_id: str,
    ) -> bool:
        """
        Offer to add detected dates to the calendar.
        
        Returns:
            True if offer was sent successfully
        """
        if not detected_dates:
            return False
        
        # Check if calendar is enabled
        if not settings.is_calendar_configured():
            logger.debug("Calendar not configured, skipping date integration offer")
            return False
        
        # Format the dates for display
        dates_summary = []
        for i, d in enumerate(detected_dates[:5], 1):  # Limit to 5 dates
            dates_summary.append(f"{i}. {d['date']}: {d['title']}")
        
        dates_text = "\n".join(dates_summary)
        
        # Store dates in session for later retrieval
        image_analyzer_session_manager.store_detected_dates(chat_id, detected_dates)
        
        # Create message with quick reply
        msg_text = (
            f"📅 I detected {len(detected_dates)} date(s) in this image:\n\n"
            f"{dates_text}\n\n"
            f"Would you like to add these to your calendar with reminders?\n\n"
            f"ฉันพบวันที่ {len(detected_dates)} รายการในภาพนี้\n"
            f"ต้องการเพิ่มลงในปฏิทินพร้อมการแจ้งเตือนไหม?"
        )
        
        quick_reply = QuickReply(
            items=[
                QuickReplyItem(
                    type="action",
                    action=MessageAction(label="📅 Yes / ใช่", text="yes add to calendar"),
                ),
                QuickReplyItem(
                    type="action",
                    action=MessageAction(label="❌ No / ไม่", text="no skip calendar"),
                ),
            ]
        )
        
        msg = TextMessage(text=msg_text, quickReply=quick_reply, quoteToken=None)
        
        # Get target for push message
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id
        
        if target:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                )
                logger.info(f"📅 Offered calendar integration for {len(detected_dates)} dates in chat {chat_id}")
                return True
            except Exception as e:
                logger.error(f"❌ Failed to offer calendar integration: {e}")
                return False
        
        return False

    async def _handle_calendar_confirmation(
        self,
        event: MessageEvent,
        text: str,
        chat_id: str,
        user_id: Optional[str],
        line_bot_api: MessagingApi,
    ) -> bool:
        """
        Handle user's response to calendar integration offer.
        
        Args:
            event: LINE message event
            text: User's response text
            chat_id: Chat ID
            user_id: User ID
            line_bot_api: LINE API client
            
        Returns:
            True if handled successfully
        """
        text_lower = text.lower().strip()
        
        # Check for "yes" response
        if "yes" in text_lower or "add to calendar" in text_lower:
            # Get detected dates from session
            detected_dates = image_analyzer_session_manager.get_detected_dates(chat_id)
            
            if not detected_dates:
                # Session expired or no dates found
                msg = TextMessage(
                    text="⏳ Session expired. Please analyze the image again.\n\n"
                         "เซสชันหมดอายุ กรุณาวิเคราะห์ภาพใหม่อีกครั้ง",
                    quickReply=None,
                    quoteToken=None,
                )
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[msg],
                            notificationDisabled=False,
                        ),
                    )
                image_analyzer_session_manager.clear_session(chat_id)
                return True
            
            # Clear the image analyzer session first
            image_analyzer_session_manager.clear_session(chat_id)
            
            # Import and call calendar agent to start extraction flow
            try:
                from src.agents.calendar_agent import CalendarAgent
                
                # Find calendar agent from the router or create one
                # For now, we'll create a new instance since it's stateless
                calendar_agent = CalendarAgent()
                
                # Start the extraction flow with detected dates
                await calendar_agent.start_extraction_flow_from_image(
                    event=event,
                    detected_dates=detected_dates,
                    user_id=user_id,
                    chat_id=chat_id,
                    line_bot_api=line_bot_api,
                )
                
                logger.info(f"📅 Started calendar extraction flow for {len(detected_dates)} dates in chat {chat_id}")
                return True
                
            except Exception as e:
                logger.error(f"❌ Failed to start calendar extraction flow: {e}", exc_info=True)
                msg = TextMessage(
                    text="❌ Failed to start calendar flow. Please try 'Zeus add event' manually.\n\n"
                         "เกิดข้อผิดพลาด กรุณาลอง 'Zeus add event' ด้วยตนเอง",
                    quickReply=None,
                    quoteToken=None,
                )
                if event.reply_token:
                    await asyncio.to_thread(
                        line_bot_api.reply_message,
                        ReplyMessageRequest(
                            replyToken=event.reply_token,
                            messages=[msg],
                            notificationDisabled=False,
                        ),
                    )
                return True
        
        # Check for "no" response
        elif "no" in text_lower or "skip" in text_lower:
            # Clear session and acknowledge
            image_analyzer_session_manager.clear_session(chat_id)
            
            msg = TextMessage(
                text="👍 Understood. Calendar skipped.\n\n"
                     "เข้าใจแล้ว ไม่เพิ่มลงปฏิทิน",
                quickReply=None,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[msg],
                        notificationDisabled=False,
                    ),
                )
            
            logger.info(f"📅 User skipped calendar integration in chat {chat_id}")
            return True
        
        else:
            # Unclear response, ask again
            quick_reply = QuickReply(
                items=[
                    QuickReplyItem(
                        type="action",
                        action=MessageAction(label="📅 Yes / ใช่", text="yes add to calendar"),
                    ),
                    QuickReplyItem(
                        type="action",
                        action=MessageAction(label="❌ No / ไม่", text="no skip calendar"),
                    ),
                ]
            )
            
            msg = TextMessage(
                text="❓ Would you like to add the detected dates to your calendar?\n\n"
                     "ต้องการเพิ่มวันที่ที่ตรวจพบลงในปฏิทินไหม?",
                quickReply=quick_reply,
                quoteToken=None,
            )
            if event.reply_token:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[msg],
                        notificationDisabled=False,
                    ),
                )
            return True

    async def _download_image(self, message_id: str) -> Optional[bytes]:
        """Download image content from LINE servers."""
        try:
            configuration = Configuration(
                access_token=settings.line_channel_access_token
            )
            
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                
                response = await asyncio.to_thread(
                    blob_api.get_message_content,
                    message_id
                )
                
                # Handle None response explicitly
                if response is None:
                    logger.warning("❌ Response is None from LINE API")
                    return None
                
                if isinstance(response, bytes):
                    return response
                elif isinstance(response, bytearray):
                    return bytes(response)
                elif hasattr(response, 'read') and callable(getattr(response, 'read', None)):
                    return response.read()
                else:
                    # Try to iterate as generator/stream
                    # Type checker: response could be an iterator/generator we haven't explicitly typed
                    chunks = []
                    try:
                        for chunk in response:  # type: ignore[union-attr]
                            chunks.append(chunk)
                        return b''.join(chunks)
                    except TypeError:
                        logger.error(f"❌ Unexpected response type: {type(response)}")
                        return None
                    
        except Exception as e:
            logger.error(f"❌ Failed to download image {message_id}: {e}", exc_info=True)
            return None

    async def _send_analyzing_message(self, event: MessageEvent, line_bot_api: MessagingApi):
        """Send a message indicating analysis is in progress."""
        msg = TextMessage(
            text="🔍 Examining thy image... One moment.\n\n"
                 "กำลังวิเคราะห์ภาพ... กรุณารอสักครู่",
            quickReply=None,
            quoteToken=None,
        )

        if event.reply_token:
            try:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[msg],
                        notificationDisabled=False,
                    ),
                )
            except Exception as e:
                logger.warning(f"⚠️ Failed to send analyzing message: {e}")

    async def _send_rate_limit_message(
        self, 
        event: MessageEvent, 
        line_bot_api: MessagingApi,
        reset_seconds: int
    ):
        """Send rate limit notification."""
        reset_minutes = (reset_seconds + 59) // 60
        
        msg = TextMessage(
            text=f"⏳ Image Analysis Rate Limit\n\n"
                 f"Maximum 5 analyses per hour.\n"
                 f"Please wait ~{reset_minutes} minute{'s' if reset_minutes != 1 else ''}.\n\n"
                 f"กรุณารออีก ~{reset_minutes} นาที 😊",
            quickReply=None,
            quoteToken=None,
        )

        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[msg],
                    notificationDisabled=False,
                ),
            )

    async def _send_error_message(
        self, 
        event: MessageEvent, 
        line_bot_api: MessagingApi,
        error_detail: str
    ):
        """Send error message to user."""
        msg = TextMessage(
            text=f"❌ Analysis Error\n\n{error_detail}\n\n"
                 f"เกิดข้อผิดพลาด กรุณาลองใหม่",
            quickReply=None,
            quoteToken=None,
        )

        user_id = getattr(event.source, "user_id", None) if event.source else None
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target,
                        messages=[msg],
                        notificationDisabled=False,
                        customAggregationUnits=None,
                    ),
                )
            except Exception as e:
                logger.error(f"❌ Failed to send error message: {e}")
