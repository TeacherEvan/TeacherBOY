"""LLM Agent - Handles general questions using GitHub Models or OpenRouter.

LIVE DATA INTEGRATION:
Zeus automatically detects queries that need real-time information (businesses,
locations, events, prices, etc.) and performs a web search BEFORE calling the LLM.
Search results are injected into the context so Zeus can reason about live data.
"""

import asyncio
import logging
import re
from typing import Optional, List, Dict, Any
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
from src.services.brave_search_service import brave_search_service
from src.services.conversation_memory_service import get_conversation_memory
from src.utils.tracing import get_tracer
from src.config import settings
from src.services.privilege_service import privilege_service

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

# ============================================================================
# LIVE DATA DETECTION PATTERNS
# ============================================================================
# These patterns trigger automatic web search before LLM response
# to provide Zeus with current, real-world information.

LIVE_DATA_PATTERNS = [
    # Location/proximity queries
    r"\bnear(?:by)?\s*(?:me|here|us)?\b",
    r"\bin\s+(?:bangkok|pattaya|thailand|chiang\s*mai|phuket|krabi|sukhumvit|silom|siam|asok)\b",
    r"\b(?:where|what)\s+(?:is|are)\s+(?:the\s+)?(?:best|nearest|closest|a\s+good)\b",
    r"\bwhere\s+can\s+i\s+(?:find|get|buy)\b",
    r"\bdirections?\s+to\b",
    r"\bhow\s+(?:to\s+)?get\s+to\b",
    r"\blocation\s+of\b",
    r"\baddress\s+(?:of|for)\b",
    
    # Business/place types
    r"\b(?:restaurant|cafe|coffee\s*shop|bar|pub|club|hotel|hostel|resort)\b",
    r"\b(?:store|shop|mall|market|supermarket|7[-\s]?eleven|convenience)\b",
    r"\b(?:hospital|clinic|pharmacy|doctor|dentist|medical)\b",
    r"\b(?:bank|atm|exchange|money\s*changer)\b",
    r"\b(?:gym|fitness|spa|massage|salon|barbershop)\b",
    r"\b(?:temple|wat|church|mosque|shrine)\b",
    r"\b(?:museum|gallery|park|beach|attraction|landmark)\b",
    r"\b(?:airport|bus\s*station|train\s*station|bts|mrt|taxi|grab)\b",
    
    # Time-sensitive queries
    r"\b(?:open|close[ds]?|hours|schedule|timing)\s*(?:now|today|tonight)?\b",
    r"\b(?:today|tonight|tomorrow|this\s+week|this\s+weekend)\b",
    r"\b(?:current|latest|recent|live|real[-\s]?time|up[-\s]?to[-\s]?date)\b",
    r"\b(?:happening|event|festival|concert|show|movie)\b",
    
    # Recommendations/reviews
    r"\b(?:best|top|recommend|suggestion|popular|famous|good)\s+(?:place|spot|restaurant|hotel|bar|cafe)?\b",
    r"\b(?:review|rating|rated)\b",
    r"\b(?:cheap|affordable|budget|expensive|luxury|fancy)\b",
    
    # Price/availability queries
    r"\b(?:price|cost|fee|rate|how\s+much)\b",
    r"\b(?:available|availability|book|reserve|reservation)\b",
    r"\b(?:menu|dish|food|cuisine)\b",
    
    # Contact/practical info
    r"\b(?:phone|number|contact|email|website|link)\b",
    r"\b(?:wifi|internet|parking|delivery)\b",
    
    # Comparison/alternatives
    r"\b(?:vs|versus|compare|alternative|similar\s+to|like)\b",
    r"\b(?:difference|between)\b",
    
    # News/current events
    r"\b(?:news|headline|breaking|update|announcement)\b",
    r"\b(?:weather|forecast|temperature|rain)\b",
    r"\b(?:traffic|congestion|accident|road)\b",
    
    # Sports/entertainment
    r"\b(?:score|match|game|play|playing|live\s+stream)\b",
    r"\b(?:ticket|seat|showtime)\b",
]

# Compile patterns for efficiency
_LIVE_DATA_REGEX = re.compile(
    "|".join(f"({p})" for p in LIVE_DATA_PATTERNS),
    re.IGNORECASE
)


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

    def _get_configured_provider(self) -> tuple[Optional[Any], str]:
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

    # ========================================================================
    # LIVE DATA DETECTION & AUTO-SEARCH
    # ========================================================================

    def _needs_live_data(self, query: str) -> bool:
        """
        Detect if query needs real-time/live data from the web.
        
        Uses compiled regex patterns to identify queries about:
        - Locations, businesses, places
        - Current events, prices, availability
        - Time-sensitive information
        - Reviews, recommendations
        
        Args:
            query: User's question/query text
            
        Returns:
            True if the query would benefit from web search data
        """
        if not query:
            return False
        return bool(_LIVE_DATA_REGEX.search(query))

    async def _auto_search(self, query: str, max_results: int = 5) -> List[Dict[str, str]]:
        """
        Perform automatic web search for live data.
        
        Args:
            query: Search query (user's question)
            max_results: Maximum search results to return
            
        Returns:
            List of search result dicts with 'title', 'url', 'description'
        """
        if not brave_search_service.is_configured():
            logger.warning("🔍 Auto-search skipped: Brave Search not configured")
            return []
        
        try:
            results = await brave_search_service.search(query, count=max_results)
            if results:
                logger.info(f"🔍 Auto-search found {len(results)} results for: {query[:50]}...")
            return results
        except Exception as e:
            logger.error(f"🔍 Auto-search error: {e}")
            return []

    def _format_search_context(self, results: List[Dict[str, str]], query: str) -> str:
        """
        Format search results as context for LLM injection.
        
        This creates a clear, structured context that helps the LLM
        understand and reason about the live data.
        
        Args:
            results: Search results from Brave Search
            query: Original user query
            
        Returns:
            Formatted context string to inject into LLM prompt
        """
        if not results:
            return ""
        
        context_lines = [
            "═══ LIVE WEB SEARCH RESULTS ═══",
            f"Query: {query}",
            f"Retrieved: {len(results)} results from the web",
            "",
        ]
        
        for i, result in enumerate(results, 1):
            title = (result.get("title") or "").strip()
            url = (result.get("url") or "").strip()
            desc = (result.get("description") or "").strip()
            
            context_lines.append(f"[{i}] {title}")
            if desc:
                # Truncate long descriptions
                if len(desc) > 300:
                    desc = desc[:297] + "..."
                context_lines.append(f"    {desc}")
            if url:
                context_lines.append(f"    🔗 {url}")
            context_lines.append("")
        
        context_lines.append("═══ END SEARCH RESULTS ═══")
        context_lines.append("")
        context_lines.append("Use this live information to answer the user's question accurately.")
        context_lines.append("Include relevant URLs when helpful. Cite sources when appropriate.")
        
        return "\n".join(context_lines)

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event for conversation memory."""
        source = event.source
        if source:
            if hasattr(source, "group_id") and source.group_id:  # type: ignore[attr-defined]
                return f"group_{source.group_id}"  # type: ignore[attr-defined]
            if hasattr(source, "room_id") and source.room_id:  # type: ignore[attr-defined]
                return f"room_{source.room_id}"  # type: ignore[attr-defined]
            if hasattr(source, "user_id") and source.user_id:  # type: ignore[attr-defined]
                return f"user_{source.user_id}"  # type: ignore[attr-defined]
        return "unknown"

    def get_priority(self) -> int:
        """
        Priority 9: Runs before TranslationAgent (10).
        Runs after SearchAgent (8).
        """
        return 9

    def _is_private_chat(self, event: MessageEvent) -> bool:
        """Check if chat is private (1-on-1)."""
        return event.source is not None and event.source.type == "user"

    def _get_group_room_ids(self, event: MessageEvent) -> tuple[Optional[str], Optional[str]]:
        """Return (group_id, room_id) from event source."""
        source = getattr(event, "source", None)
        group_id = getattr(source, "group_id", None) if source else None
        room_id = getattr(source, "room_id", None) if source else None
        return group_id, room_id

    def _is_boss_question(self, query: str) -> bool:
        """Return True if the query is asking who is boss."""
        q = (query or "").strip().lower()
        return bool(
            re.match(
                r"^who\s*(?:is|'?s)\s*(?:the\s*)?boss\s*[?!.]*$",
                q,
            )
        )

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
        is_admin = privilege_service.is_admin(user_id)

        # Hard-coded shortcut: boss question must reply with ONLY 'Evan...'
        if self._is_boss_question(query):
            await self._send_reply(event, line_bot_api, "Evan...")
            return True

        # Admin-only Zeus outbound messaging helpers (named recipients).
        action, alias, payload = self._parse_zeus_action(query)
        if action:
            if not is_admin:
                await self._send_reply(event, line_bot_api, "🔒 Admin-only.")
                return True
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
                drafted = await llm_provider.chat_completion(
                    messages, temperature=settings.llm_temperature
                )
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

        # Handle memory clear command: "Zeus clear" or "Zeus forget"
        if query.lower().strip() in ("clear", "forget", "reset"):
            chat_id = self._get_chat_id(event)
            memory = get_conversation_memory()
            if memory:
                await memory.clear_conversation(chat_id)
                await self._send_reply(
                    event,
                    line_bot_api,
                    "🧹 Conversation memory cleared.\n\nI've forgotten our previous chat. Start fresh!",
                )
            else:
                await self._send_reply(
                    event,
                    line_bot_api,
                    "💭 Memory is not enabled.\n\nNo conversation history to clear.",
                )
            return True

        logger.info(
            f"🤖 Zeus query from {user_id} ({'DM' if is_private else 'group'}): {query[:50]}..."
        )

        # Group/room access control for non-admins (private chats always allowed).
        if not is_private and not settings.is_zeus_allowed_in_group(
            *self._get_group_room_ids(event),
            user_is_admin=is_admin,
        ):
            await self._send_reply(
                event,
                line_bot_api,
                "🔒 Zeus is not enabled in this group.",
            )
            return True

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
                            "⚠️ Zeus cannot speak without an Oracle!\n\n"
                            "No LLM service is configured for divine wisdom.\n\n"
                            "🔧 Configure one of:\n"
                            "• GITHUB_MODELS_PAT (Classic PAT with models:read)\n"
                            "• OPENROUTER_API_KEY"
                        )
                    )
                    return True

                span.set_attribute("llm.provider", provider_name)

                # ============================================================
                # LIVE DATA AUTO-SEARCH
                # ============================================================
                # Detect if query needs real-time information and auto-search
                search_context = ""
                used_live_search = False
                
                if self._needs_live_data(query):
                    logger.info(f"🔍 Query needs live data, auto-searching: {query[:50]}...")
                    span.set_attribute("llm.needs_live_data", True)
                    
                    search_results = await self._auto_search(query)
                    if search_results:
                        search_context = self._format_search_context(search_results, query)
                        used_live_search = True
                        span.set_attribute("llm.search_results_count", len(search_results))
                        logger.info(f"🔍 Injecting {len(search_results)} search results into LLM context")
                    else:
                        logger.warning("🔍 No search results found, proceeding with LLM only")
                else:
                    span.set_attribute("llm.needs_live_data", False)

                # Get conversation context from memory service
                chat_id = self._get_chat_id(event)
                memory = get_conversation_memory()
                context_messages = []
                
                if memory and settings.conversation_memory_enabled:
                    # Add user message to memory first
                    await memory.add_message(chat_id, "user", query, user_id)
                    # Get conversation context (includes system prompt hint)
                    context_messages = await memory.get_context_messages(chat_id)
                    logger.debug(f"💭 Retrieved {len(context_messages)} context messages for {chat_id}")

                # Build system prompt - enhanced with live search capability note
                system_prompt = settings.llm_system_prompt
                if used_live_search:
                    system_prompt += (
                        "\n\n⚡ LIVE DATA MODE ACTIVE: You have access to real-time web search results. "
                        "Use this current information to provide accurate, up-to-date answers. "
                        "Include specific details, prices, hours, and URLs from the search results when relevant."
                    )

                # Build messages with conversation context
                messages = [{"role": "system", "content": system_prompt}]
                
                if context_messages:
                    # Add context messages (excluding current query, already added to memory)
                    # Context includes previous exchanges for multi-turn conversation
                    for ctx_msg in context_messages[:-1]:  # Exclude last (current query)
                        messages.append(ctx_msg)
                
                # Inject search context before user query if available
                if search_context:
                    messages.append({
                        "role": "user",
                        "content": f"Here is current information from the web:\n\n{search_context}"
                    })
                    messages.append({
                        "role": "assistant", 
                        "content": "Thank you for the live search data. I'll use this current information to answer your question accurately."
                    })
                
                # Add current query
                messages.append({"role": "user", "content": query})

                # Call LLM with primary provider
                response_text = await llm_provider.chat_completion(
                    messages, temperature=settings.llm_temperature
                )
                
                # If primary fails and we have a fallback, try it
                if not response_text:
                    fallback_provider, fallback_name = self._get_fallback_provider(provider_name)
                    if fallback_provider:
                        logger.warning(f"⚠️ {provider_name} failed, trying fallback: {fallback_name}")
                        response_text = await fallback_provider.chat_completion(
                            messages, temperature=settings.llm_temperature
                        )
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
                                    f"🏛️ The Oracle you seek has wandered from Mount Olympus!\n\n"
                                    f"Model '{model_used}' is not available in the {provider_name} pantheon.\n\n"
                                    "⚡ Decree: Update the default model in your environment settings."
                                ),
                            )
                        elif status_code == 429:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    "⏳ Even the God of Thunder must rest between lightning strikes!\n\n"
                                    f"The {provider_name} Olympian scrolls are briefly sealed.\n"
                                    "Free tier: ~15 requests per minute.\n\n"
                                    "🌩️ Patience, mortal. Try again in a moment."
                                ),
                            )
                        elif status_code == 403:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    "⚡ By the thunderbolts of Olympus! The gates of wisdom are CLOSED!\n\n"
                                    f"Error 403: {provider_name} denies entry to Zeus.\n\n"
                                    "🔑 Mortal decrees to restore access:\n"
                                    "• Use a CLASSIC PAT (not fine-grained)\n"
                                    "• Enable 'models:read' scope\n"
                                    "• Visit github.com/marketplace/models first\n\n"
                                    "⚠️ Fine-grained PATs lack the divine 'models' permission!"
                                ),
                            )
                        else:
                            await self._send_reply(
                                event,
                                line_bot_api,
                                (
                                    f"🌩️ Storm clouds obscure my vision! ({provider_name} error {status_code})\n\n"
                                    "The Oracle's connection to Olympus falters.\n"
                                    "Check your API key/PAT configuration and try again."
                                ),
                            )
                    else:
                        await self._send_reply(
                            event,
                            line_bot_api,
                            (
                                "🌩️ The mists of Olympus cloud my thoughts...\n\n"
                                "Zeus cannot summon an answer at this moment.\n"
                                "Try again shortly, brave mortal!"
                            ),
                        )
                    return True

                # Save assistant response to conversation memory
                if memory and settings.conversation_memory_enabled:
                    await memory.add_message(chat_id, "assistant", response_text)
                    logger.debug(f"💭 Saved assistant response to memory for {chat_id}")

                # Send response
                await self._send_reply(event, line_bot_api, response_text)
                
                logger.info(f"✅ Sent LLM response via {provider_name} for '{query[:30]}...'")
                return True

            except Exception as e:
                logger.error(f"❌ LLM agent error: {e}", exc_info=True)
                try:
                    await self._send_reply(
                        event, 
                        line_bot_api, 
                        (
                            "⚡ A divine mishap on Mount Olympus!\n\n"
                            "Zeus encountered an unexpected storm.\n"
                            "The gods are working to restore order."
                        )
                    )
                except Exception as reply_error:
                    # If replying fails (e.g., invalid reply token), still treat as handled
                    # The _send_reply method already tries push message as fallback
                    logger.warning(f"⚠️ Could not send error message: {reply_error}")
                return True

    def _get_fallback_provider(self, primary_name: str) -> tuple[Optional[Any], str]:
        """Get fallback provider if primary fails."""
        if primary_name == "GitHub Models" and self.openrouter_service.is_configured():
            return self.openrouter_service, "OpenRouter"
        elif primary_name == "OpenRouter" and self.github_service.is_configured():
            return self.github_service, "GitHub Models"
        return None, ""

    async def _send_reply(self, event: MessageEvent, line_bot_api: MessagingApi, message: str):
        """Send text message using push_message (robust for async processing)."""
        import datetime

        current_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        logger.info(f"📤 Attempting to send message at {current_time}, message length: {len(message)}")

        # Extract target ID from event source
        target_id = None
        if event.source:
            target_id = (
                getattr(event.source, "group_id", None) or
                getattr(event.source, "room_id", None) or
                getattr(event.source, "user_id", None)
            )

        if target_id:
            try:
                await asyncio.to_thread(
                    line_bot_api.push_message,
                    PushMessageRequest(
                        to=target_id,
                        messages=[TextMessage(text=message, quickReply=None, quoteToken=None)],
                        notificationDisabled=False,
                    ),
                )
                logger.info(f"✅ Push message sent successfully to {target_id}")
            except Exception as e:
                logger.error(f"❌ Push message failed: {e}", exc_info=True)
                raise
        else:
            logger.error("❌ Cannot send message: no target ID available")
