"""LLM Agent - Handles general questions using GitHub Models or OpenRouter."""

import asyncio
import logging
import re
from typing import Optional
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import (
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,
    TextMessage,
)

from .base_agent import BaseAgent
from src.services.openrouter_service import openrouter_service
from src.services.github_models_service import github_models_service
from src.utils.tracing import get_tracer
from src.config import settings
from src.services.privilege_service import privilege_service

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class LLMAgent(BaseAgent):
    """Agent for handling general questions using GitHub Models or OpenRouter LLMs."""

    def __init__(self):
        super().__init__(
            name="LLMAgent",
            description="General Q&A using GitHub Models or OpenRouter LLMs",
        )
        # Services for LLM providers
        self.github_service = github_models_service
        self.openrouter_service = openrouter_service
        # Keep legacy reference for admin actions that use llm_service.client
        self.llm_service = openrouter_service
        # Cache env admins (tests patch module-local `settings`).
        self._admin_user_ids = settings.get_admin_user_ids()

    def _get_configured_provider(self) -> tuple[Optional[object], str]:
        """
        Get the first configured LLM provider based on priority settings.
        
        Returns:
            Tuple of (service_instance, provider_name) or (None, "") if none configured
        """
        priority = settings.get_llm_provider_priority()
        
        for provider in priority:
            if provider == "github" and self.github_service.is_configured():
                return self.github_service, "GitHub Models"
            elif provider == "openrouter" and self.openrouter_service.is_configured():
                return self.openrouter_service, "OpenRouter"
        
        # Fallback: try any configured provider
        if self.github_service.is_configured():
            return self.github_service, "GitHub Models"
        if self.openrouter_service.is_configured():
            return self.openrouter_service, "OpenRouter"
        
        return None, ""

    def _is_any_llm_configured(self) -> bool:
        """Check if any LLM provider is configured."""
        return self.github_service.is_configured() or self.openrouter_service.is_configured()

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

    def _get_named_users(self) -> dict[str, str]:
        """Return alias -> LINE user ID mapping from USER_<ALIAS> env vars."""
        try:
            return settings.get_named_user_ids()
        except Exception:
            return {}

    def _resolve_named_user_id(self, alias: str | None) -> str | None:
        alias_clean = (alias or "").strip().lower()
        if not alias_clean:
            return None
        return self._get_named_users().get(alias_clean)

    def _truncate_for_line(self, text: str, max_chars: int = 4500) -> str:
        cleaned = (text or "").strip()
        if len(cleaned) <= max_chars:
            return cleaned
        return cleaned[:max_chars].rstrip() + "..."

    def _push_text(self, line_bot_api: MessagingApi, to_user_id: str, text: str) -> bool:
        """Best-effort push text message to a LINE user ID."""
        try:
            if not hasattr(line_bot_api, "push_message"):
                return False
            line_bot_api.push_message(
                PushMessageRequest(
                    to=to_user_id,
                    messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
                    notificationDisabled=False,
                    customAggregationUnits=[],
                )
            )
            return True
        except Exception:
            return False

    def _parse_zeus_action(self, query: str) -> tuple[str | None, str | None, str | None]:
        """Parse Zeus admin actions.

        Returns (action, alias, payload).

        Supported:
        - send <alias> <text>
        - llm_send <alias> <prompt>
        - send_weather <alias>
        - send the weather to (my) <alias>
        """
        q = (query or "").strip()
        if not q:
            return None, None, None

        m = re.match(r"^send_weather\s+(\S+)\s*$", q, flags=re.IGNORECASE)
        if m:
            return "send_weather", m.group(1), None

        m = re.match(r"^send\s+(\S+)\s+(.+)$", q, flags=re.IGNORECASE)
        if m:
            return "send", m.group(1), m.group(2)

        m = re.match(r"^llm_send\s+(\S+)\s+(.+)$", q, flags=re.IGNORECASE)
        if m:
            return "llm_send", m.group(1), m.group(2)

        m = re.match(
            r"^send\s+(?:the\s+)?weather\s+to\s+(?:my\s+)?(\S+)\s*$",
            q,
            flags=re.IGNORECASE,
        )
        if m:
            return "send_weather", m.group(1), None

        return None, None, None

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

        # Admin-only Zeus outbound messaging helpers (named recipients).
        action, alias, payload = self._parse_zeus_action(query)
        if action:
            target_user_id = self._resolve_named_user_id(alias)
            if not target_user_id:
                await self._send_reply(
                    event,
                    line_bot_api,
                    (
                        f"❌ Unknown alias: {alias}\n\n"
                        "Configure: USER_<ALIAS>=<LINE_USER_ID> in your environment."
                    ),
                )
                return True

            if action == "send":
                msg = self._truncate_for_line(payload or "")
                pushed = await asyncio.to_thread(
                    self._push_text, line_bot_api, target_user_id, msg
                )
                await self._send_reply(
                    event,
                    line_bot_api,
                    "✅ Sent." if pushed else "❌ Failed to push message.",
                )
                return True

            if action == "send_weather":
                # Use the shared httpx client set during lifespan.
                client = getattr(self.llm_service, "client", None)
                if client is None:
                    await self._send_reply(
                        event,
                        line_bot_api,
                        "❌ Weather send unavailable (HTTP client not initialized).",
                    )
                    return True

                try:
                    from src.services.news_data_service import NewsDataService

                    service = NewsDataService(http_client=client, news_api_key=None)
                    data = await service.get_weather_data()
                    temp = data.get("temperature", "N/A")
                    pm25 = data.get("pm25", "N/A")
                    will_rain = data.get("will_rain")
                    rain_text = "Yes" if will_rain else "No" if will_rain is not None else "N/A"
                    msg = (
                        "🌡️ Bangkok weather\n"
                        f"Temp: {temp}°C\n"
                        f"PM2.5: {pm25}\n"
                        f"Next 5h rain: {rain_text}"
                    )
                    pushed = await asyncio.to_thread(
                        self._push_text, line_bot_api, target_user_id, msg
                    )
                    await self._send_reply(
                        event,
                        line_bot_api,
                        "✅ Weather sent." if pushed else "❌ Failed to push weather.",
                    )
                    return True
                except Exception as e:
                    logger.error(f"❌ Zeus send_weather failed: {e}", exc_info=True)
                    await self._send_reply(event, line_bot_api, "❌ Failed to fetch/send weather.")
                    return True

            if action == "llm_send":
                llm_provider, provider_name = self._get_configured_provider()
                if not llm_provider:
                    await self._send_reply(
                        event,
                        line_bot_api,
                        "❌ No LLM provider configured.\n\nSet GITHUB_MODELS_PAT or OPENROUTER_API_KEY.",
                    )
                    return True

                messages = [
                    {
                        "role": "system",
                        "content": settings.llm_system_prompt
                        + "\n\nYou will draft a short message to be sent to another person. Output plain text only.",
                    },
                    {"role": "user", "content": payload or ""},
                ]
                drafted = await llm_provider.chat_completion(messages, temperature=0.4)
                if not drafted:
                    await self._send_reply(event, line_bot_api, "❌ LLM failed to generate a message.")
                    return True

                msg = self._truncate_for_line(drafted)
                pushed = await asyncio.to_thread(
                    self._push_text, line_bot_api, target_user_id, msg
                )
                await self._send_reply(
                    event,
                    line_bot_api,
                    "✅ LLM message sent." if pushed else "❌ Failed to push message.",
                )
                return True

        logger.info(
            f"🤖 Zeus query from {user_id} ({'DM' if is_private else 'group'}): {query[:50]}..."
        )

        with tracer.start_as_current_span("llm_agent.handle") as span:
            span.set_attribute("llm.query", query)
            
            try:
                # Get the configured LLM provider
                llm_provider, provider_name = self._get_configured_provider()
                
                if not llm_provider:
                    await self._send_reply(
                        event, 
                        line_bot_api, 
                        (
                            "⚠️ No LLM service configured.\n\n"
                            "Configure one of:\n"
                            "• GITHUB_MODELS_PAT (free tier)\n"
                            "• OPENROUTER_API_KEY"
                        )
                    )
                    return True

                span.set_attribute("llm.provider", provider_name)

                # Prepare prompt
                messages = [
                    {"role": "system", "content": settings.llm_system_prompt},
                    {"role": "user", "content": query}
                ]

                # Call LLM with primary provider
                response_text = await llm_provider.chat_completion(messages)
                
                # If primary fails and we have a fallback, try it
                if not response_text:
                    fallback_provider, fallback_name = self._get_fallback_provider(provider_name)
                    if fallback_provider:
                        logger.warning(f"⚠️ {provider_name} failed, trying fallback: {fallback_name}")
                        response_text = await fallback_provider.chat_completion(messages)
                        if response_text:
                            provider_name = fallback_name
                
                if not response_text:
                    status_code, err_text, model_used = llm_provider.get_last_error()
                    if status_code:
                        if status_code == 404 and model_used:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    f"{provider_name} error (404): model not available: {model_used}\n\n"
                                    "Fix: update the default model in your environment settings."
                                ),
                            )
                        elif status_code == 429:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    f"⏳ {provider_name} rate limit reached.\n\n"
                                    "Free tier limits: ~15 requests/minute.\n"
                                    "Please wait a moment and try again."
                                ),
                            )
                        else:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    f"{provider_name} error ({status_code}).\n\n"
                                    "Check your API key/PAT configuration."
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
                
                logger.info(f"✅ Sent LLM response via {provider_name} for '{query[:30]}...'")
                return True

            except Exception as e:
                logger.error(f"❌ LLM agent error: {e}", exc_info=True)
                try:
                    await self._send_reply(event, line_bot_api, "Sorry, something went wrong.")
                except Exception:
                    # If replying fails (e.g., invalid reply token), still treat as handled
                    pass
                return True

    def _get_fallback_provider(self, primary_name: str) -> tuple[Optional[object], str]:
        """Get fallback provider if primary fails."""
        if primary_name == "GitHub Models" and self.openrouter_service.is_configured():
            return self.openrouter_service, "OpenRouter"
        elif primary_name == "OpenRouter" and self.github_service.is_configured():
            return self.github_service, "GitHub Models"
        return None, ""

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
