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
"""

import asyncio
import logging
import base64
from typing import Optional
from linebot.v3.webhooks import MessageEvent, TextMessageContent, ImageMessageContent
from linebot.v3.messaging import (
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
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
            return image_analyzer_session_manager.is_waiting_for_question(chat_id, user_id)
        
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
        
        # Convert to base64 and store
        image_base64 = base64.b64encode(image_bytes).decode('utf-8')
        image_data_url = f"data:image/jpeg;base64,{image_base64}"
        
        if not image_analyzer_session_manager.store_image(chat_id, image_data_url):
            await self._send_error_message(event, line_bot_api, "Session expired. Please start again with 'Zeus analyze this'.")
            return False
        
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
        
        if not analysis:
            status_code, error, model_used = github_models_service.get_last_error()
            logger.error(f"❌ Vision API failed: {status_code} - {error}")
            await self._send_error_message(event, line_bot_api, f"Analysis failed: {error or 'Unknown error'}")
            return False
        
        span.set_attribute("analyzer.success", True)
        span.set_attribute("analysis.length", len(analysis))
        
        # Format and send response
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
        return True

    def _build_vision_message(self, image_data_url: str, question: str) -> list:
        """Build the vision API message structure."""
        
        system_prompt = (
            "You are Zeus, the king of the Olympian gods. "
            "You speak with measured wisdom and authority, but with warmth befitting a benevolent ruler. "
            "When analyzing images, provide helpful, practical answers to mortal questions. "
            "Be direct and insightful. Keep responses concise but complete. "
            "For menus, signs, or text: translate and explain if in another language. "
            "For products or items: describe what you see and provide recommendations if asked."
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
        """Format the analysis response for LINE."""
        header = "⚡ ZEUS OBSERVES ⚡\n"
        header += "━" * 20 + "\n\n"
        
        # Truncate if too long (LINE limit is 5000 chars)
        max_content = 4800 - len(header)
        if len(analysis) > max_content:
            analysis = analysis[:max_content] + "\n\n[Response truncated]"
        
        return header + analysis

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
