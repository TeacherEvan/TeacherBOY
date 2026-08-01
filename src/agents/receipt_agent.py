"""Receipt Agent — Budget Boss receipt scanning via LINE."""

import logging
from typing import Any

from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.profiler_session_manager import profiler_session_manager
from src.services.receipt_bridge import gemini_text_to_ocr_payload, ingest_receipt
from src.utils.llm_fallback import chat_completion_with_vision_fallback
from src.utils.tracing import get_tracer

from .base_agent import BaseAgent

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# Scrape prompt — reuse existing pattern
RECEIPT_SCRAPE_PROMPT = (
    "Extract ALL text from this receipt image. Return ONLY the text content found in the image. "
    "Include any text from the receipt: merchant name, items, prices, subtotal, tax, total, date, "
    "payment method, card numbers (last 4 digits only). "
    "Preserve line breaks and layout as much as possible. "
    "If multiple languages are present, include all. "
    "Do not add explanations or analysis - just the extracted text."
)


class ReceiptAgent(BaseAgent):
    """Agent for scanning receipts from LINE images and sending to Budget Boss."""

    def __init__(self):
        super().__init__(
            name="ReceiptAgent",
            description="Scan receipt images and extract financial data to Budget Boss",
        )
        self._receipt_cache: dict[str, Any] = {}

    def get_priority(self) -> int:
        """Priority 8 — after profiler (7) and image_analyzer (7), before document_memory (8)."""
        return 8

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event (group_id > user_id)."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return group_id
        if event.source and hasattr(event.source, "user_id"):
            return getattr(event.source, "user_id", "unknown")
        return "unknown"

    async def _is_user_linked(self, line_user_id: str) -> bool:
        """Check if LINE user is linked to a Budget Boss account.

        For now, we assume any user can send receipts. In production,
        this could check against a linked users table.
        """
        return True

    async def _is_receipt_enabled(self, chat_id: str) -> bool:
        """Check if receipt feature is enabled."""
        return getattr(settings, "receipt_agent_enabled", True)

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Handle bare image when no higher-priority agent is waiting."""
        if not self.enabled:
            return False

        # Must be an image message
        message = getattr(event, "message", None)
        if not message or getattr(message, "type", None) != "image":
            return False

        # Check if vision providers are available
        if not self._has_vision_provider():
            logger.debug("ReceiptAgent: no vision provider available")
            return False

        chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None

        # Check if image_analyzer is waiting for image (priority 7)
        if await image_analyzer_session_manager.is_waiting_for_image(chat_id, user_id):
            logger.debug(f"ReceiptAgent: image_analyzer waiting for image in chat {chat_id}")
            return False

        # Check if profiler is waiting for image (priority 7)
        if profiler_session_manager.is_waiting_for_image(chat_id, user_id):
            logger.debug(f"ReceiptAgent: profiler waiting for image in chat {chat_id}")
            return False

        # Check if user is linked to Budget Boss
        if not await self._is_user_linked(user_id or ""):
            logger.debug(f"ReceiptAgent: user {user_id} not linked to Budget Boss")
            return False

        # Check if receipt feature enabled
        if not await self._is_receipt_enabled(chat_id):
            logger.debug(f"ReceiptAgent: receipt feature disabled for chat {chat_id}")
            return False

        logger.info(f"ReceiptAgent: will handle receipt image from chat {chat_id}, user {user_id}")
        return True

    def _has_vision_provider(self) -> bool:
        """Check if any vision-capable provider is configured."""
        from src.services.gemini_service import gemini_service
        from src.services.hermes_service import hermes_service
        from src.services.hf_inference_service import hf_inference_service
        from src.services.openrouter_service import openrouter_service

        return (
            hermes_service.is_vision_configured()
            or openrouter_service.is_configured()
            or gemini_service.is_vision_configured()
            or hf_inference_service.is_vision_configured()
        )

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        """Process receipt image: fetch, OCR via Gemini, send to Budget Boss, reply."""
        _chat_id = self._get_chat_id(event)
        user_id = getattr(event.source, "user_id", None) if event.source else None
        message_id = getattr(event.message, "id", None)

        if not message_id:
            logger.error("ReceiptAgent: no message ID")
            return False

        try:
            # 1. Fetch image bytes from LINE
            image_data = await self._fetch_image_bytes(message_id)
            if not image_data:
                await self._reply_error(line_bot_api, event, "Could not fetch image from LINE")
                return False

            # 2. Send to Gemini vision for text extraction
            scraped_text = await chat_completion_with_vision_fallback(
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": RECEIPT_SCRAPE_PROMPT},
                            {"type": "image_url", "image_url": {"url": image_data}},
                        ],
                    }
                ],
                temperature=0.1,
                max_tokens=2000,
            )

            if not scraped_text or not scraped_text.strip():
                await self._reply_error(line_bot_api, event, "Could not extract text from receipt")
                return False

            logger.info(f"ReceiptAgent: extracted {len(scraped_text)} chars from receipt")

            # 3. Convert to OcrPayload
            country_hint = self._get_country_hint(user_id)
            ocr_payload = gemini_text_to_ocr_payload(scraped_text, country_hint)

            # 4. POST to Budget Boss /receipts/ingest
            idempotency_key = f"line_{message_id}"
            result = await ingest_receipt(user_id or "", ocr_payload, idempotency_key)

            if not result.get("success"):
                await self._reply_error(line_bot_api, event, f"Budget Boss error: {result.get('error', 'unknown')}")
                return False

            # 5. Reply with Flex card showing extracted data + deep link
            await self._reply_success(line_bot_api, event, result)

            return True

        except Exception as e:
            logger.error(f"ReceiptAgent: error processing receipt: {e}", exc_info=True)
            await self._reply_error(line_bot_api, event, "Failed to process receipt")
            return False

    async def _fetch_image_bytes(self, message_id: str) -> str | None:
        """Fetch image from LINE and return as data URL."""
        try:
            from linebot.v3.messaging import ApiClient, Configuration, MessagingApiBlob

            access_token = settings.line_channel_access_token
            if not access_token:
                logger.error("No LINE channel access token")
                return None

            configuration = Configuration(access_token=access_token)
            async with ApiClient(configuration) as api_client:
                blob_api = MessagingApiBlob(api_client)
                # Run in thread since the SDK is sync
                import asyncio

                content = await asyncio.to_thread(blob_api.get_message_content, message_id)

                if not content:
                    return None

                # Convert bytes to base64 data URL
                import base64

                b64 = base64.b64encode(content).decode("utf-8")
                # Detect mime type from first bytes or default
                mime = "image/jpeg"
                if content[:4] == b"\x89PNG":
                    mime = "image/png"
                elif content[:2] == b"\xff\xd8":
                    mime = "image/jpeg"
                elif content[:4] == b"RIFF" and content[8:12] == b"WEBP":
                    mime = "image/webp"

                return f"data:{mime};base64,{b64}"
        except Exception as e:
            logger.error(f"ReceiptAgent: failed to fetch image: {e}")
            return None

    def _get_country_hint(self, user_id: str | None) -> str:
        """Get country hint for currency/date parsing from user's locale."""
        # Could be enhanced to use user's profile or stored preference
        return "TH"  # Default to Thailand

    async def _reply_success(self, line_bot_api: MessagingApi, event: MessageEvent, result: dict) -> None:
        """Reply with Flex card showing receipt summary and deep link."""
        try:
            from linebot.v3.messaging import (
                FlexBox,
                FlexBubble,
                FlexButton,
                FlexMessage,
                FlexSeparator,
                FlexText,
                ReplyMessageRequest,
                URIAction,
            )

            fields = result.get("fields", {})
            merchant = fields.get("merchant", {}).get("value", "Unknown")
            total = fields.get("total", {}).get("value", 0)
            category = fields.get("category", {}).get("value", "other")
            currency = fields.get("currency", {}).get("value", "USD")
            confidence = result.get("confidence", {})
            total_conf = confidence.get("total", 0)

            # Format currency
            currency_symbols = {"USD": "$", "EUR": "€", "GBP": "£", "THB": "฿", "JPY": "¥", "ZAR": "R"}
            symbol = currency_symbols.get(currency, currency)

            # Build Flex bubble
            bubble = FlexBubble(
                header=FlexBox(
                    layout="vertical",
                    contents=[
                        FlexText(text="🧾 Receipt Scanned", weight="bold", size="lg", color="#1a1a2e"),
                        FlexText(text=f"via {result.get('source', 'LINE')}", size="xs", color="#888"),
                    ],
                ),
                body=FlexBox(
                    layout="vertical",
                    spacing="md",
                    contents=[
                        FlexBox(
                            layout="horizontal",
                            contents=[
                                FlexText(text="Merchant", size="sm", color="#666", flex=1),
                                FlexText(text=str(merchant), size="sm", weight="bold", flex=2, wrap=True),
                            ],
                        ),
                        FlexBox(
                            layout="horizontal",
                            contents=[
                                FlexText(text="Total", size="sm", color="#666", flex=1),
                                FlexText(text=f"{symbol}{total:.2f}", size="lg", weight="bold", color="#fbbf24", flex=2),
                            ],
                        ),
                        FlexBox(
                            layout="horizontal",
                            contents=[
                                FlexText(text="Category", size="sm", color="#666", flex=1),
                                FlexText(text=str(category).capitalize(), size="sm", flex=2),
                            ],
                        ),
                        FlexSeparator(),
                        FlexText(
                            text=f"Confidence: {int(total_conf * 100)}%",
                            size="xs",
                            color="#34d399" if total_conf > 0.7 else "#fbbf24" if total_conf > 0.5 else "#f87171",
                        ),
                    ],
                ),
                footer=FlexBox(
                    layout="vertical",
                    spacing="sm",
                    contents=[
                        FlexButton(
                            action=URIAction(
                                label="Open in Budget Boss",
                                uri=f"{settings.budgetboss_app_url or 'https://budgetboss.app'}/receipts/{result.get('draftId', '')}",
                            ),
                            style="primary",
                            color="#fbbf24",
                        ),
                    ],
                ),
            )

            flex_msg = FlexMessage(alt_text="Receipt scanned", contents=bubble)
            await line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[flex_msg]))
        except Exception as e:
            logger.error(f"ReceiptAgent: failed to send success reply: {e}")
            # Fallback to simple text
            await self._reply_text(line_bot_api, event, f"✅ Receipt scanned: {merchant} — {symbol}{total:.2f} ({category})")

    async def _reply_error(self, line_bot_api: MessagingApi, event: MessageEvent, message: str) -> None:
        """Reply with error message."""
        await self._reply_text(line_bot_api, event, f"❌ {message}")

    async def _reply_text(self, line_bot_api: MessagingApi, event: MessageEvent, text: str) -> None:
        """Reply with simple text message."""
        from linebot.v3.messaging import ReplyMessageRequest, TextMessage

        await line_bot_api.reply_message(ReplyMessageRequest(reply_token=event.reply_token, messages=[TextMessage(text=text)]))
