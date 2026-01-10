
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
    ImageMessageContent,
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
from src.services.profiler_session_manager import profiler_session_manager
from src.services.news_session_manager import news_session_manager
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.rate_limiter import rate_limiter
from src.agents.agent_router import AgentRouter
from src.services.openrouter_service import openrouter_service
from src.services.calendar_service import calendar_service
from src.services.calendar_session_manager import calendar_session_manager
from src.services.reminder_service import reminder_service
from src.services.message_buffer_service import message_buffer_service
from src.services.brave_search_service import brave_search_service
from src.services.github_models_service import github_models_service
from src.handlers.message_handler import (
    handle_join_event,
    handle_leave_event,
    handle_member_joined_event,
    handle_member_left_event,
)
from src.services.metrics_service import metrics_service
from src.services.conversation_memory_service import (
    init_conversation_memory,
    get_conversation_memory,
)
from src.services.history_log_service import (
    init_history_log,
    get_history_log,
    EventType,
    LogLevel,
)
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
    github_models_service.set_client(http_client_pool)
    logger.info("✅ HTTP client pool ready with connection pooling enabled")

    # ========================================================================
    # PHASE 2a: Conversation Memory Initialization
    # ========================================================================
    if settings.conversation_memory_enabled:
        if settings.is_conversation_memory_configured():
            memory_service = init_conversation_memory(
                hf_token=settings.hf_memory_token,
                hf_repo_id=settings.hf_memory_repo_id,
            )
            logger.info(
                f"💭 Conversation memory enabled (HF Hub: {settings.hf_memory_repo_id})"
            )
        else:
            memory_service = init_conversation_memory()  # In-memory only
            logger.info("💭 Conversation memory enabled (in-memory only)")
    else:
        logger.info("💭 Conversation memory disabled")

    # ========================================================================
    # PHASE 2a2: History Logging Initialization
    # ========================================================================
    if settings.is_history_log_configured():
        history_log = init_history_log(
            storage_path=settings.history_log_path,
            hf_token=settings.hf_memory_token if settings.is_history_log_hf_configured() else None,
            hf_repo_id=settings.history_log_hf_repo_id,
            encryption_key=settings.history_log_encryption_key,
        )
        logger.info(f"📜 History logging enabled (path: {settings.history_log_path})")
        
        # Log startup event
        await history_log.log(
            event_type=EventType.STARTUP,
            message="⚡ Zeus Multi-Agent System starting up!",
            level=LogLevel.INFO,
            zeus_style=settings.zeus_error_style,
        )
        
        if settings.is_history_log_hf_configured():
            logger.info(f"☁️ History log HF sync enabled: {settings.history_log_hf_repo_id}")
        if settings.history_log_encryption_key:
            logger.info("🔐 History log encryption enabled")
    else:
        logger.info("📜 History logging disabled")

    # ========================================================================
    # PHASE 2a3: Calendar Service Initialization
    # ========================================================================
    if settings.is_calendar_configured():
        calendar_service.configure(
            storage_path=settings.calendar_data_path,
            hf_token=settings.hf_memory_token if settings.is_calendar_hf_configured() else None,
            hf_repo_id=settings.calendar_hf_repo_id,
            sync_interval_seconds=settings.calendar_sync_interval_seconds,
        )
        logger.info(f"📅 Calendar service enabled (path: {settings.calendar_data_path})")
        
        if settings.is_calendar_hf_configured():
            logger.info(f"☁️ Calendar HF sync enabled: {settings.calendar_hf_repo_id}")
        
        # Configure reminder service (will be started later after LINE API is ready)
        reminder_service.configure(
            reminder_hour=settings.calendar_reminder_hour,
        )
        logger.info(f"⏰ Reminder service configured (daily at {settings.calendar_reminder_hour}:00 Bangkok)")
    else:
        logger.info("📅 Calendar service disabled")

    # ========================================================================
    # PHASE 2b: Translation Services Configuration
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

    # Import agents here (after HTTP client is ready)
    from src.agents.help_agent import HelpAgent
    from src.agents.admin_agent import AdminAgent
    from src.agents.translation_agent import TranslationAgent
    from src.agents.calendar_agent import CalendarAgent
    from src.agents.profiler_agent import ProfilerAgent
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent
    from src.agents.search_agent import SearchAgent
    from src.agents.llm_agent import LLMAgent
    from src.agents.news_agent import NewsAgent
    from src.agents.special_news_agent import SpecialNewsAgent
    from src.services.news_data_service import NewsDataService
    from src.services.special_news_service import SpecialNewsService

    # Register Help Agent (Priority: 5 - Highest)
    help_agent = HelpAgent()
    agent_router.register_agent(help_agent)
    logger.info("🗡️ Help Agent registered (comprehensive contextual help)")

    # Register Admin Agent if configured (Priority: 5 - Highest)
    admin_user_ids: list[str] = []
    try:
        candidate_admins = settings.get_admin_user_ids()
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

    # Register Calendar Agent (Priority: 6 - Handles calendar/reminder commands)
    if settings.is_calendar_configured():
        calendar_agent = CalendarAgent(calendar_service=calendar_service)
        agent_router.register_agent(calendar_agent)
        logger.info("📅 Calendar Agent registered (events and reminders)")
    else:
        logger.info("📅 Calendar Agent not registered (calendar disabled)")

    # Register Hannibal Profile Agent (Priority: 6 - Psychological profiling from message history)
    if settings.is_github_models_configured():
        from src.agents.hannibal_agent import HannibalProfileAgent
        hannibal_agent = HannibalProfileAgent(http_client=http_client_pool)
        agent_router.register_agent(hannibal_agent)
        logger.info("🎭 Hannibal Profile Agent registered (message history analysis)")
    else:
        logger.info("🎭 Hannibal Profile Agent not registered (GitHub Models not configured)")

    # Register Profiler Agent (Priority: 7 - Handles image messages for psychological profiling)
    if settings.is_profiler_configured():
        profiler_agent = ProfilerAgent(http_client=http_client_pool)
        agent_router.register_agent(profiler_agent)
        logger.info(f"🔬 Profiler Agent registered (Model: {settings.profiler_model})")
    else:
        logger.info("🔬 Profiler Agent not registered (GitHub Models not configured)")

    # Register Image Analyzer Agent (Priority: 7 - Handles image Q&A)
    if settings.is_github_models_configured():
        image_analyzer_agent = ImageAnalyzerAgent(http_client=http_client_pool)
        agent_router.register_agent(image_analyzer_agent)
        logger.info("🖼️ Image Analyzer Agent registered (general image Q&A)")
    else:
        logger.info("🖼️ Image Analyzer Agent not registered (GitHub Models not configured)")

    # Register Search Agent (Priority: 8)
    search_agent = SearchAgent()
    agent_router.register_agent(search_agent)
    if settings.is_brave_search_configured():
        logger.info("🔍 Search Agent registered (Brave Search enabled)")
    else:
        logger.info("🔍 Search Agent registered but DISABLED until BRAVE_SEARCH_API_KEY is set")

    # Register LLM Agent (Priority: 9)
    llm_agent = LLMAgent()
    agent_router.register_agent(llm_agent)
    if settings.is_openrouter_configured():
        logger.info(f"🤖 LLM Agent registered (Model: {settings.openrouter_default_model})")
    else:
        logger.info("🤖 LLM Agent registered (API key missing - will return errors)")

    # Register Translation Agent (Priority: 10)
    translation_agent = TranslationAgent()
    agent_router.register_agent(translation_agent)
    logger.info("🌐 Translation Agent registered")

    # Register Special News Agent (Priority: 12)
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

    # ========================================================================
    # PHASE 6: Start Background Cleanup Tasks
    # ========================================================================
    logger.info("🧹 Starting background cleanup tasks...")
    profiler_session_manager.start_cleanup()
    news_session_manager.start_cleanup()
    image_analyzer_session_manager.start_cleanup()
    calendar_session_manager.start_cleanup()
    message_buffer_service.start_cleanup_task()
    rate_limiter.start_cleanup()
    logger.info("✅ All cleanup tasks started")

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

    # Stop background cleanup tasks
    logger.info("🧹 Stopping background cleanup tasks...")
    profiler_session_manager.stop_cleanup()
    news_session_manager.stop_cleanup()
    image_analyzer_session_manager.stop_cleanup()
    calendar_session_manager.stop_cleanup()
    message_buffer_service.stop_cleanup_task()
    rate_limiter.stop_cleanup()
    logger.info("✅ All cleanup tasks stopped")

    # Stop reminder service scheduler
    reminder_service.stop()
    logger.info("✅ Reminder service stopped")

    # Stop calendar service HF Hub sync
    calendar_service.stop()
    logger.info("✅ Calendar service stopped")

    # Log shutdown event
    history_svc = get_history_log()
    if history_svc:
        await history_svc.log(
            event_type=EventType.SHUTDOWN,
            message="🛑 Zeus Multi-Agent System shutting down gracefully",
            level=LogLevel.INFO,
        )
        history_svc.stop()
        logger.info("✅ History log scheduler stopped")

    scheduler_service.stop()
    logger.info("✅ Scheduler stopped")

    # Stop conversation memory scheduler (HF Hub sync)
    memory_svc = get_conversation_memory()
    if memory_svc:
        memory_svc.stop()
        logger.info("✅ Conversation memory scheduler stopped")

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
async def health_check() -> Dict[str, Any]:
    """
    Kubernetes-style health check endpoint.

    Returns HTTP 200 if the service is healthy and ready to serve traffic.
    Includes checks for critical external dependencies.
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {},
    }

    # Check LINE Bot API connectivity
    try:
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            # Simple check - get bot info (already cached in bot_user_id)
            if bot_user_id:
                health_status["checks"]["line_api"] = "healthy"
            else:
                health_status["checks"]["line_api"] = "degraded"
    except Exception as e:
        logger.warning(f"LINE API health check failed: {e}")
        health_status["checks"]["line_api"] = "unhealthy"

    # Check Google Translate API if configured (best-effort)
    if settings.is_google_translate_configured():
        try:
            # Simple test translation
            test_result = await google_translation_service.translate("Hello", "en", "th")
            if test_result:
                health_status["checks"]["google_translate"] = "healthy"
            else:
                health_status["checks"]["google_translate"] = "degraded"
        except Exception as e:
            logger.warning(f"Google Translate health check failed: {e}")
            health_status["checks"]["google_translate"] = "unhealthy"

    # Check LibreTranslate API (best-effort)
    try:
        test_result = await translation_service.translate("Hello", "en", "th")
        if test_result:
            health_status["checks"]["libretranslate"] = "healthy"
        else:
            health_status["checks"]["libretranslate"] = "unhealthy"
    except Exception as e:
        logger.warning(f"LibreTranslate health check failed: {e}")
        health_status["checks"]["libretranslate"] = "unhealthy"

    # Check OpenRouter if configured
    if settings.is_openrouter_configured():
        try:
            # Simple connectivity check (don't make expensive LLM call)
            health_status["checks"]["openrouter"] = "configured"
        except Exception as e:
            logger.warning(f"OpenRouter health check failed: {e}")
            health_status["checks"]["openrouter"] = "unhealthy"

    # Check agent registration
    agents_count = len(agent_router.list_agents())
    health_status["checks"]["agents_registered"] = agents_count
    if agents_count == 0:
        # In unit tests the lifespan may not register agents.
        pass

    return health_status


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
                            # Store message in buffer for "zeus scrape" feature
                            chat_id = None
                            if event.source:
                                if getattr(event.source, "group_id", None):
                                    chat_id = f"group_{event.source.group_id}"
                                elif getattr(event.source, "room_id", None):
                                    chat_id = f"room_{event.source.room_id}"
                                elif getattr(event.source, "user_id", None):
                                    chat_id = f"user_{event.source.user_id}"
                            
                            if chat_id and user_id:
                                message_buffer_service.store_message(
                                    chat_id=chat_id,
                                    text=event.message.text,
                                    user_id=user_id,
                                    message_id=event.message.id if hasattr(event.message, 'id') else None
                                )
                            
                            # Route text message to appropriate agent
                            await agent_router.route_message(event, line_bot_api)

                        elif isinstance(event.message, ImageMessageContent):
                            # Route image message to ProfilerAgent via agent router
                            logger.info(f"📷 Received image message from {user_id}")
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
                                        to=user_id, 
                                        messages=[welcome_msg],
                                        customAggregationUnits=None,  # Explicitly None to avoid SDK serialization issues
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
