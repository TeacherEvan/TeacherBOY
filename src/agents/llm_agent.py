"""LLM Agent - Handles general questions using OpenRouter."""

import asyncio
import logging
import re
from typing import Optional
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

from .base_agent import BaseAgent
from src.services.openrouter_service import openrouter_service
from src.utils.tracing import get_tracer
from src.config import settings
from src.services.privilege_service import privilege_service

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class LLMAgent(BaseAgent):
    """Agent for handling general questions using OpenRouter LLMs."""

    def __init__(self):
        super().__init__(
            name="LLMAgent",
            description="General Q&A using OpenRouter LLMs",
        )
        self.llm_service = openrouter_service
        # Cache env admins (tests patch module-local `settings`).
        self._admin_user_ids = settings.get_admin_user_ids()

    def get_priority(self) -> int:
        """
        Priority 9: Runs before TranslationAgent (10).
        Runs after SearchAgent (8).
        """
        return 9

    def _is_admin(self, user_id: Optional[str]) -> bool:
        """Check if user is an admin."""
        if privilege_service.is_claimed_admin(user_id):
            return True
        return user_id in self._admin_user_ids if user_id else False

    def _is_private_chat(self, event: MessageEvent) -> bool:
        """Check if chat is private (1-on-1)."""
        return event.source is not None and event.source.type == "user"

    def _parse_command(self, text: str) -> Optional[str]:
        """
        Parse command.
        Trigger: 'Zeus <query>'
        Returns query string or None.
        """
        # Regex for trigger: "Zeus" followed by query.
        # Accept optional leading slash and common typo "Zues".
        match = re.match(r"^/?(?:Zeus|Zues)\s+(.+)$", text.strip(), re.IGNORECASE)
        if match:
            query = match.group(1).strip()
            return query
        return None

    def _is_search_command(self, text: str) -> bool:
        """Return True if text is a Zeus search command (reserved for SearchAgent)."""
        return bool(
            re.match(
                r"^/?(?:Zeus|Zues)\s+search\b",
                text.strip(),
                re.IGNORECASE,
            )
        )

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """
        Handle if:
        1. Text starts with 'Zeus'
        2. This is NOT a Zeus search command (reserved for SearchAgent)
        """
        if not self._parse_command(text):
            return False

        # Reserve Zeus search for SearchAgent (priority 8)
        if self._is_search_command(text):
            return False
            
        # Always handle Zeus here so users get an explicit denial message
        # instead of silent ignore when they are not an admin.
        return True

    async def handle(
        self, event: MessageEvent, text: str, line_bot_api: MessagingApi
    ) -> bool:
        """Process LLM request."""
        query = self._parse_command(text)
        if not query:
            return False

        user_id = getattr(event.source, "user_id", None) if event.source else None
        is_private = self._is_private_chat(event)

        # Admin gate: Zeus LLM is admin-only everywhere.
        if not self._is_admin(user_id):
            context = "DM" if is_private else "group chat"
            logger.info(
                f"🔒 Zeus LLM denied for non-admin user_id={user_id} in {context}"
            )
            await self._send_reply(
                event,
                line_bot_api,
                (
                    "🔒 Zeus is admin-only.\n\n"
                    "If you think you are an admin, run: /admin whoami\n"
                    "Then add your LINE user ID to ADMIN_USER_IDS in HF/GitHub secrets and restart."
                ),
            )
            return True

        logger.info(
            f"🤖 Zeus query from {user_id} ({'DM' if is_private else 'group'}): {query[:50]}..."
        )

        with tracer.start_as_current_span("llm_agent.handle") as span:
            span.set_attribute("llm.query", query)
            
            try:
                if not self.llm_service.is_configured():
                    await self._send_reply(event, line_bot_api, "LLM service is not configured (missing API key).")
                    return True

                # Prepare prompt
                messages = [
                    {"role": "system", "content": settings.llm_system_prompt},
                    {"role": "user", "content": query}
                ]

                # Call LLM
                response_text = await self.llm_service.chat_completion(messages)
                
                if not response_text:
                    status_code, err_text, model_used = self.llm_service.get_last_error()
                    if status_code:
                        if status_code == 404 and model_used:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    f"OpenRouter error (404): model not available: {model_used}\n\n"
                                    "Fix: set OPENROUTER_DEFAULT_MODEL to a supported model in your host/Space Secrets, then restart.\n"
                                    "Models: https://openrouter.ai/models"
                                ),
                            )
                        else:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    f"OpenRouter error ({status_code}).\n\n"
                                    "Fix: check OPENROUTER_API_KEY and OPENROUTER_DEFAULT_MODEL in your host/Space Secrets, then restart.\n"
                                    "Models: https://openrouter.ai/models"
                                ),
                            )
                    else:
                        await self._send_reply(
                            event,
                            line_bot_api,
                            "Sorry, I couldn't generate an answer right now. Please try again in a moment.",
                        )
                    return True

                # Send response
                await self._send_reply(event, line_bot_api, response_text)
                
                logger.info(f"✅ Sent LLM response for '{query}'")
                return True

            except Exception as e:
                logger.error(f"❌ LLM agent error: {e}", exc_info=True)
                try:
                    await self._send_reply(event, line_bot_api, "Sorry, something went wrong.")
                except Exception:
                    # If replying fails (e.g., invalid reply token), still treat as handled
                    pass
                return True

    async def _send_reply(self, event: MessageEvent, line_bot_api: MessagingApi, message: str):
        """Send text reply."""
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[TextMessage(text=message, quickReply=None, quoteToken=None)],
                    notificationDisabled=False,
                ),
            )
