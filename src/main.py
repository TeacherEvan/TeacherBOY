
"""Zeus - Production-Grade Multi-Agent LINE Translation Bot.

This module implements a FastAPI application with intelligent agent routing,
high-performance async I/O, and production-ready error handling.
"""

import asyncio
import logging
import httpx
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any, Optional

# LINE Bot SDK v3 imports
import linebot.v3
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    FollowEvent,
    UnfollowEvent,
    JoinEvent,
    LeaveEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
)
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    PushMessageRequest,  # For FollowEvent welcome message (push to user)
    TextMessage,
    FlexMessage,
    FlexBubble,
)
from linebot.v3.exceptions import InvalidSignatureError

from src.config import settings
from src.services.translation_service import translation_service
from src.services.google_translation import google_translation_service
from src.services.scheduler_service import scheduler_service
from src.services.news_data_service import NewsDataService
from src.agents.agent_router import AgentRouter
from src.agents.translation_agent import TranslationAgent
from src.agents.admin_agent import AdminAgent
from src.agents.special_news_agent import SpecialNewsAgent
from src.agents.news_agent import NewsAgent
from src.agents.llm_agent import LLMAgent
from src.agents.search_agent import SearchAgent
from src.agents.help_agent import HelpAgent
from src.services.openrouter_service import openrouter_service
from src.services.brave_search_service import brave_search_service
from src.handlers.message_handler import (
    handle_join_event,
    handle_leave_event,
    handle_member_joined_event,
    handle_member_left_event,
)
from src.services.metrics_service import metrics_service
from src.utils.tracing import setup_tracing

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)

# ============================================================================
# LINE Bot SDK Configuration
# ============================================================================
configuration = Configuration(access_token=settings.line_channel_access_token)
webhook_parser = linebot.v3.WebhookParser(settings.line_channel_secret)

# ============================================================================
# Global Agent Router (Singleton Pattern)
# ============================================================================
agent_router = AgentRouter()

# Bot's own user ID for self-message detection (prevents infinite loops)
bot_user_id: Optional[str] = None


def create_optimized_http_client() -> httpx.AsyncClient:
    """
    Create a production-optimized HTTP client with connection pooling.

    Features:
    - HTTP/2 support for better performance
    - Connection pooling to reduce latency
    - Configurable timeouts
    - Keep-alive connections

    Returns:
        Configured httpx.AsyncClient instance
    """
    client_config = settings.get_http_client_config()
    limits = httpx.Limits(
        max_connections=client_config["limits"]["max_connections"],
        max_keepalive_connections=client_config["limits"]["max_keepalive_connections"],
    )

    return httpx.AsyncClient(
        timeout=client_config["timeout"],
        limits=limits,
        http2=client_config["http2"],
        follow_redirects=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manage application lifecycle with proper resource initialization and cleanup.

    This context manager handles:
    - HTTP client pool initialization
    - Translation services setup
    - Agent registration
    - Scheduler configuration
    - Graceful shutdown
    """
    global bot_user_id

    logger.info("=" * 80)
    logger.info("🚀 Zeus Multi-Agent System - Starting Up")
    logger.info("=" * 80)

    # Tracing (OpenTelemetry) - optional, controlled by settings.enable_tracing
    setup_tracing(app, settings)

    # ========================================================================
    # PHASE 1: Bot Identity Detection (Prevent Infinite Loop)
    # ========================================================================
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            # Get bot's own profile to extract user ID
            bot_info = await asyncio.to_thread(line_bot_api.get_bot_info)
            bot_user_id = bot_info.user_id
            logger.info(
                f"🤖 Bot User ID: {bot_user_id} (self-message detection enabled)"
            )
    except Exception as e:
        logger.error(f"❌ Failed to get bot user ID: {e}", exc_info=True)
        logger.warning("⚠️  Bot will operate without self-message detection (RISKY!)")

    # ========================================================================
    # PHASE 2: HTTP Client Initialization
    # ========================================================================
    logger.info("📡 Initializing optimized HTTP client pool...")
    http_client_pool = create_optimized_http_client()
    translation_service.set_client(http_client_pool)
    openrouter_service.set_client(http_client_pool)
    brave_search_service.set_client(http_client_pool)
    logger.info("✅ HTTP client pool ready with connection pooling enabled")

    # ========================================================================
    # PHASE 2: Translation Services Configuration
    # ========================================================================
    if settings.is_google_translate_configured():
        google_translation_service.api_key = settings.google_translate_api_key
        google_translation_service.set_client(http_client_pool)
        logger.info("✅ Google Cloud Translation API configured (PRIMARY)")
    else:
        logger.warning(
            "⚠️  Google Translate API not configured - using LibreTranslate only"
        )

    logger.info("✅ LibreTranslate configured (FALLBACK)")

    # ========================================================================
    # PHASE 3: Agent Registration
    # ========================================================================
    logger.info("📋 Registering intelligent agents...")

    # Register Help Agent (Priority: 5 - Highest)
    help_agent = HelpAgent()
    agent_router.register_agent(help_agent)
    logger.info("🗡️ Help Agent registered (comprehensive contextual help)")

    # Register Admin Agent if configured (Priority: 5 - Highest)
    admin_user_ids: list[str] = []
    try:
        candidate_admins = settings.get_admin_user_ids()  # type: ignore[call-arg]
        if isinstance(candidate_admins, list):
            admin_user_ids = candidate_admins
    except Exception:
        admin_user_ids = []

    admin_setup_key = getattr(settings, "admin_setup_key", None)
    if not isinstance(admin_setup_key, str) or not admin_setup_key.strip():
        admin_setup_key = None

    if admin_user_ids or admin_setup_key:
        admin_agent = AdminAgent(
            http_client=http_client_pool, news_api_key=settings.news_api_key
        )
        agent_router.register_agent(admin_agent)
        if admin_user_ids:
            logger.info(
                f"🔧 Admin Agent registered with {len(admin_user_ids)} authorized admin(s)"
            )
        else:
            logger.info(
                "🔧 Admin Agent registered (bootstrap enabled via ADMIN_SETUP_KEY)"
            )
    else:
        logger.info("🔧 Admin Agent not registered (no ADMIN_USER_IDS configured)")

    # Register Translation Agent (Priority: 10)
    translation_agent = TranslationAgent()
    agent_router.register_agent(translation_agent)

    # Register LLM Agent (Priority: 9)
    llm_agent = LLMAgent()
    agent_router.register_agent(llm_agent)
    if settings.is_openrouter_configured():
        logger.info(f"🤖 LLM Agent registered (Model: {settings.openrouter_default_model})")
    else:
        logger.info("🤖 LLM Agent registered (API key missing - will return errors)")

    # Register Search Agent (Priority: 8 - Mutually exclusive with LLM via triggers)
    if settings.is_brave_search_configured():
        search_agent = SearchAgent()
        agent_router.register_agent(search_agent)
        logger.info("🔍 [Startup] Search Agent registered (Brave Search enabled)")
    else:
        logger.info("🔍 [Startup] Search Agent not registered (BRAVE_SEARCH_API_KEY missing)")

    # Register Special News Agent (Priority: 12)
    from src.services.special_news_service import SpecialNewsService

    special_news_service = SpecialNewsService(
        http_client=http_client_pool,
        cache_ttl_seconds=300  # 5-minute cache for volatile news data
    )
    special_news_agent = SpecialNewsAgent(news_service=special_news_service)
    agent_router.register_agent(special_news_agent)
    logger.info("📰 Special News Agent registered (Thailand tourism, sports, international)")

    # Register News Agent (Priority: 15)
    news_data_service = NewsDataService(
        http_client=http_client_pool, news_api_key=settings.news_api_key
    )
    news_agent = NewsAgent(news_data_service=news_data_service)
    agent_router.register_agent(news_agent)
    if settings.is_news_api_configured():
        logger.info("📰 News Agent registered with NewsAPI.org key")
    else:
        logger.info("📰 News Agent registered (using Open-Meteo only, no NewsAPI key)")

    # Update AdminAgent with news_data_service if it was registered
    if admin_user_ids or admin_setup_key:
        # Re-inject news_data_service into admin_agent for stats dashboard
        admin_agent._news_data_service = news_data_service

    # ========================================================================
    # PHASE 5: Startup Summary
    # ========================================================================
    agents_info = agent_router.list_agents()
    logger.info(f"✅ Registered {len(agents_info)} agent(s):")
    for agent_info in agents_info:
        status = "🟢 ENABLED" if agent_info["enabled"] else "🔴 DISABLED"
        logger.info(
            f"   {status} | {agent_info['name']}: {agent_info['description']} "
            f"(priority: {agent_info['priority']})"
        )

    logger.info("=" * 80)
    logger.info("✅ Zeus is READY to serve! 🎉")
    logger.info("=" * 80)

    yield

    # ========================================================================
    # GRACEFUL SHUTDOWN
    # ========================================================================
    logger.info("=" * 80)
    logger.info("🛑 Zeus - Shutting down gracefully...")
    logger.info("=" * 80)

    scheduler_service.stop()
    logger.info("✅ Scheduler stopped")

    await http_client_pool.aclose()
    logger.info("✅ HTTP client pool closed")

    logger.info("👋 Zeus shutdown complete. Goodbye!")
    logger.info("=" * 80)


# ============================================================================
# FastAPI Application Initialization
# ============================================================================
app = FastAPI(
    title="Zeus - Multi-Agent Translation Bot",
    description="Production-grade Thai/English translation bot for LINE with intelligent agent routing",
    version="3.0.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.debug else None,  # Disable docs in production
    redoc_url="/redoc" if settings.debug else None,
)

# Add CORS middleware for API access (if needed)
if settings.debug:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ============================================================================
# Health Check & Monitoring Endpoints
# ============================================================================


@app.get("/", tags=["Health"])
async def root() -> Dict[str, Any]:
    """
    Root endpoint with service information.

    Returns basic information about the service status and version.
    """
    return {
        "status": "operational",
        "service": "Zeus Multi-Agent Translation Bot",
        "version": "3.0.0",
        "api_docs": "/docs" if settings.debug else "disabled",
        "features": {
            "translation": "Thai ↔ English",
            "google_translate": settings.is_google_translate_configured(),
        },
    }


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, str]:
    """
    Kubernetes-style health check endpoint.

    Returns HTTP 200 if the service is healthy and ready to serve traffic.
    """
    # TODO: [OPTIMIZATION] Add actual health checks (DB connection, external APIs, etc.)
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}


@app.get("/readiness", tags=["Health"])
async def readiness_check() -> Dict[str, Any]:
    """
    Readiness probe for orchestration systems.

    Returns detailed status of critical dependencies.
    """
    agents_status = agent_router.list_agents()

    return {
        "ready": True,
        "agents_registered": len(agents_status),
        "google_translate_enabled": settings.is_google_translate_configured(),
    }


# ============================================================================
# LINE Webhook Endpoint
# ============================================================================


@app.post("/webhook", tags=["LINE Bot"])
async def webhook(request: Request) -> JSONResponse:
    """
    LINE Bot webhook endpoint for receiving messages and events.

    This endpoint:
    1. Validates LINE signature for security
    2. Parses incoming events
    3. Routes messages to appropriate agents
    4. Handles group/member events

    Args:
        request: FastAPI request object containing LINE webhook data

    Returns:
        JSON response with processing status

    Raises:
        HTTPException: If signature validation fails
    """
    # Extract signature and body
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_text = body.decode("utf-8")

    logger.info(f"📨 Received webhook request ({len(body_text)} bytes)")

    try:
        # Parse and validate events using LINE SDK v3
        events = webhook_parser.parse(body_text, signature)  # type: ignore[union-attr]

        # Ensure events is a list
        if not isinstance(events, list):
            events = []

        # Create API client for sending replies
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)

            # Process each event
            for event in events:
                try:
                    if isinstance(event, MessageEvent):
                        # CRITICAL: Check if message is from bot itself (prevent infinite loop)
                        user_id = getattr(event.source, "user_id", None) if event.source else None
                        if bot_user_id and user_id == bot_user_id:
                            logger.info(
                                f"🔒 Skipping bot's own message (self-message detection)"
                            )
                            continue

                        if isinstance(event.message, TextMessageContent):
                            # Route text message to appropriate agent
                            await agent_router.route_message(event, line_bot_api)

                    elif isinstance(event, JoinEvent):
                        # Bot joined a group/room
                        await handle_join_event(event, line_bot_api)

                    elif isinstance(event, FollowEvent):
                        # User added bot as friend
                        user_id = (
                            getattr(event.source, "user_id", None)
                            if getattr(event, "source", None)
                            else None
                        )
                        metrics_service.record_friend_added(user_id)
                        logger.info("➕ Follow event received (friend added)")

                        # Send welcome message
                        if user_id:
                            welcome_msg = TextMessage(text="Welcome friend\n\nยินดีต้อนรับเพื่อน")  # type: ignore[call-arg]
                            try:
                                await asyncio.to_thread(
                                    line_bot_api.push_message,
                                    PushMessageRequest(  # type: ignore[call-arg]
                                        to=user_id, messages=[welcome_msg]
                                    ),
                                )
                                logger.info(f"✅ Sent welcome message to new friend {user_id}")
                            except Exception as e:
                                logger.error(f"❌ Failed to send welcome message: {e}")

                    elif isinstance(event, UnfollowEvent):
                        # User blocked/removed bot
                        user_id = (
                            getattr(event.source, "user_id", None)
                            if getattr(event, "source", None)
                            else None
                        )
                        metrics_service.record_friend_removed(user_id)
                        logger.info("➖ Unfollow event received")

                    elif isinstance(event, LeaveEvent):
                        # Bot left a group/room
                        await handle_leave_event(event, line_bot_api)

                    elif isinstance(event, MemberJoinedEvent):
                        # New member joined group/room
                        await handle_member_joined_event(event, line_bot_api)

                    elif isinstance(event, MemberLeftEvent):
                        # Member left group/room
                        await handle_member_left_event(event, line_bot_api)

                    else:
                        logger.debug(f"Unhandled event type: {type(event).__name__}")

                except Exception as event_error:
                    logger.error(
                        f"❌ Error processing event {type(event).__name__}: {event_error}",
                        exc_info=True,
                    )
                    # Continue processing other events even if one fails
                    continue

        return JSONResponse(content={"status": "success", "processed": len(events)})

    except InvalidSignatureError:
        logger.error("❌ Invalid LINE signature - possible security threat!")
        raise HTTPException(
            status_code=400, detail="Invalid signature. Request rejected for security."
        )

    except Exception as e:
        logger.error(f"❌ Webhook processing error: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"status": "error", "detail": str(e)}, status_code=500
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app", host=settings.host, port=settings.port, reload=settings.debug
    )
