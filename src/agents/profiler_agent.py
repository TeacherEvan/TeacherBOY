"""
Profiler Agent - Psychological profiling from photos using vision AI.

This agent handles image messages and performs comprehensive psychological
analysis using established behavioral science frameworks:

- FBI Behavioral Analysis Unit (BAU) methodology
- Paul Ekman's FACS and micro-expression analysis
- Joe Navarro's body language principles
- Environmental and color psychology

DISCLAIMER: For educational/entertainment purposes only.
"""

import asyncio
import logging
from typing import Optional, Any
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    MessagingApiBlob,
    ReplyMessageRequest,
    TextMessage,
)

from .base_agent import BaseAgent
from src.services.profiler_service import profiler_service
from src.services.github_models_service import github_models_service
from src.services.rate_limiter import RateLimiter
from src.services.metrics_service import metrics_service
from src.services.privilege_service import privilege_service
from src.config import settings
from src.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Rate limiter: 3 analyses per hour per chat (vision API is expensive)
profiler_rate_limiter = RateLimiter(
    max_requests=3,
    time_window_seconds=3600
)


class ProfilerAgent(BaseAgent):
    """
    Agent for psychological profiling from images.
    
    Uses GPT-4o vision capabilities to analyze photos and provide
    comprehensive behavioral and psychological assessments.
    """

    def __init__(
        self, 
        http_client=None,
        messaging_api_blob: Optional[MessagingApiBlob] = None
    ):
        """
        Initialize ProfilerAgent.
        
        Args:
            http_client: Shared HTTP client (not used directly but kept for interface consistency)
            messaging_api_blob: LINE API blob client for downloading images
        """
        super().__init__(
            name="ProfilerAgent",
            description="Psychological profiling from photos using AI vision",
        )
        self.http_client = http_client
        self.blob_api = messaging_api_blob
        self._admin_user_ids = settings.get_admin_user_ids()
        
    def get_priority(self) -> int:
        """
        Profiler has high priority for image messages.
        
        Priority 7: After admin/help (5), before search (8) and LLM (9).
        """
        return 7

    def _is_admin(self, user_id: Optional[str]) -> bool:
        """Check if user is an admin (admins bypass rate limits)."""
        if privilege_service.is_claimed_admin(user_id):
            return True
        return user_id in self._admin_user_ids if user_id else False

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

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if this is an image message.
        
        Note: The `text` parameter will be empty for image messages.
        We check the message type instead.
        """
        # Check if profiler is enabled
        if not getattr(settings, 'profiler_enabled', True):
            return False
            
        # Check if GitHub Models is configured (required for vision)
        if not github_models_service.is_configured():
            logger.debug("ProfilerAgent: GitHub Models not configured")
            return False
        
        # Check message type - we handle ImageMessageContent
        message = getattr(event, 'message', None)
        if message is None:
            return False
            
        message_type = getattr(message, 'type', None)
        return message_type == 'image'

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """
        Process image message and return psychological profile.
        
        Args:
            event: LINE message event with image
            text: Empty for image messages
            line_bot_api: LINE Messaging API client
            
        Returns:
            True if handled successfully
        """
        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        message_id = getattr(event.message, "id", None)

        with tracer.start_as_current_span("profiler_agent.handle") as span:
            span.set_attribute("chat.id", chat_id)
            span.set_attribute("message.type", "image")

            try:
                # Check rate limiting (skip for admins)
                if not self._is_admin(user_id):
                    if not profiler_rate_limiter.is_allowed(chat_id, user_id):
                        span.set_attribute("profiler.rate_limited", True)
                        metrics_service.record_rate_limited()
                        
                        reset_seconds = profiler_rate_limiter.get_reset_time(chat_id, user_id)
                        await self._send_rate_limit_message(event, line_bot_api, reset_seconds)
                        logger.warning(f"⚠️  Rate limited profiler for chat {chat_id}")
                        return True
                else:
                    logger.info(f"🔓 Admin {user_id} bypassed profiler rate limit")

                # Send "analyzing" indicator
                await self._send_analyzing_message(event, line_bot_api)
                
                # Download image from LINE
                if not isinstance(message_id, str) or not message_id.strip():
                    await self._send_error_message(
                        event,
                        line_bot_api,
                        "Missing image message id from LINE event. Please try again.",
                    )
                    return False

                logger.info(f"📸 Downloading image {message_id} from LINE...")
                image_bytes = await self._download_image(message_id, line_bot_api)
                
                if not image_bytes:
                    await self._send_error_message(
                        event, line_bot_api, 
                        "Failed to download image. Please try again."
                    )
                    return False

                span.set_attribute("image.size_bytes", len(image_bytes))
                logger.info(f"📸 Downloaded {len(image_bytes)} bytes")

                # Prepare image for vision API
                image_data_url = profiler_service.get_image_data_url(image_bytes)
                
                # Build vision message with profiling prompt
                analysis_type = getattr(settings, 'profiler_analysis_type', 'full')
                messages = profiler_service.build_vision_message(
                    image_data_url, 
                    analysis_type=analysis_type
                )

                # Get analysis from GPT-4o vision
                logger.info(f"🔬 Sending to GPT-4o for psychological analysis...")
                
                model = getattr(settings, 'profiler_model', 'openai/gpt-4o')
                analysis = await github_models_service.chat_completion_with_vision(
                    messages=messages,
                    model=model,
                    temperature=0.3,  # Lower temperature for analytical tasks
                    max_tokens=4000,
                )

                if not analysis:
                    status_code, error, model_used = github_models_service.get_last_error()
                    logger.error(f"❌ Vision API failed: {status_code} - {error}")
                    
                    await self._send_error_message(
                        event, line_bot_api,
                        f"Analysis failed: {error or 'Unknown error'}. Please try again later."
                    )
                    return False

                # Format and send response
                formatted_response = profiler_service.format_response_for_line(analysis)
                
                # Track metrics
                profiler_service.increment_analysis_count()
                span.set_attribute("profiler.success", True)
                span.set_attribute("analysis.length", len(analysis))

                # Send analysis result
                text_msg = TextMessage(
                    text=formatted_response,
                    quickReply=None,
                    quoteToken=None,
                )

                if event.reply_token:
                    # Note: We already used reply token for "analyzing" message
                    # Need to use push message for the result
                    from linebot.v3.messaging import PushMessageRequest
                    
                    group_id = getattr(event.source, "group_id", None) if event.source else None
                    room_id = getattr(event.source, "room_id", None) if event.source else None
                    target = group_id or room_id or user_id
                    
                    if target:
                        await asyncio.to_thread(
                            line_bot_api.push_message,
                            PushMessageRequest(
                                to=target,
                                messages=[text_msg],
                                notificationDisabled=False,
                                customAggregationUnits=None,
                            ),
                        )

                logger.info(f"✅ Psychological profile sent for chat {chat_id}")
                return True

            except Exception as e:
                logger.error(f"❌ ProfilerAgent error: {e}", exc_info=True)
                span.set_attribute("profiler.error", str(e))
                await self._send_error_message(
                    event, line_bot_api,
                    "An error occurred during analysis. Please try again."
                )
                return False

    async def _download_image(
        self, 
        message_id: str,
        line_bot_api: MessagingApi
    ) -> Optional[bytes]:
        """
        Download image content from LINE servers.
        
        Args:
            message_id: LINE message ID
            line_bot_api: LINE Messaging API client
            
        Returns:
            Image bytes or None if failed
        """
        try:
            # Use MessagingApiBlob for binary content
            from linebot.v3.messaging import ApiClient, Configuration
            
            configuration = Configuration(
                access_token=settings.line_channel_access_token
            )
            
            with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                
                # Get message content (returns binary stream)
                response: Any = await asyncio.to_thread(
                    blob_api.get_message_content,
                    message_id
                )
                
                # Read all bytes from response
                if hasattr(response, 'read'):
                    return response.read()
                elif isinstance(response, bytes):
                    return response
                else:
                    # Handle generator/iterator response
                    chunks = []
                    for chunk in response:
                        chunks.append(chunk)
                    return b''.join(chunks)
                    
        except Exception as e:
            logger.error(f"❌ Failed to download image {message_id}: {e}", exc_info=True)
            return None

    async def _send_analyzing_message(
        self, 
        event: MessageEvent, 
        line_bot_api: MessagingApi
    ):
        """Send a message indicating analysis is in progress."""
        analyzing_msg = TextMessage(
            text="🔬 Analyzing image... Please wait.\n\n"
                 "⚡ Zeus Psychological Profiler is scanning:\n"
                 "• Facial expressions (Ekman FACS)\n"
                 "• Body language (Navarro FBI methods)\n"
                 "• Environmental context\n"
                 "• Color psychology",
            quickReply=None,
            quoteToken=None,
        )

        if event.reply_token:
            try:
                await asyncio.to_thread(
                    line_bot_api.reply_message,
                    ReplyMessageRequest(
                        replyToken=event.reply_token,
                        messages=[analyzing_msg],
                        notificationDisabled=False,
                    ),
                )
            except Exception as e:
                logger.warning(f"⚠️  Failed to send analyzing message: {e}")

    async def _send_rate_limit_message(
        self, 
        event: MessageEvent, 
        line_bot_api: MessagingApi,
        reset_seconds: int
    ):
        """Send rate limit notification."""
        reset_minutes = (reset_seconds + 59) // 60
        
        msg = TextMessage(
            text=f"⏳ Profiler Rate Limit\n\n"
                 f"Maximum 3 photo analyses per hour.\n"
                 f"Please wait ~{reset_minutes} minute{'s' if reset_minutes != 1 else ''}.\n\n"
                 f"📸 กรุณารออีก ~{reset_minutes} นาที 😊",
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
                 f"เกิดข้อผิดพลาด กรุณาลองใหม่อีกครั้ง",
            quickReply=None,
            quoteToken=None,
        )

        # Try push message if reply token already used
        user_id = getattr(event.source, "user_id", None) if event.source else None
        group_id = getattr(event.source, "group_id", None) if event.source else None
        room_id = getattr(event.source, "room_id", None) if event.source else None
        target = group_id or room_id or user_id

        if target:
            try:
                from linebot.v3.messaging import PushMessageRequest
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
