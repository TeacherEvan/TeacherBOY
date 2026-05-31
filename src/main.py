
"""Ms. Green - Production-Grade Multi-Agent LINE Assistant.

This module implements a FastAPI application with intelligent agent routing,
high-performance async I/O, and production-ready error handling.
"""

import asyncio
import logging
import httpx
from datetime import datetime
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, Response
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
from src.services.scheduler_service import scheduler_service
from src.services.profiler_session_manager import profiler_session_manager
from src.services.news_session_manager import news_session_manager
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.rate_limiter import rate_limiter
from src.agents.agent_router import AgentRouter, RouteResult
from src.services.openrouter_service import openrouter_service
from src.services.calendar_service import calendar_service
from src.services.calendar_session_manager import calendar_session_manager
from src.services.reminder_service import reminder_service
from src.services.message_buffer_service import message_buffer_service
from src.services.brave_search_service import brave_search_service
from src.services.github_models_service import github_models_service
from src.services.bot_identity_service import configure_bot_identity_service
from src.services.convex_calendar_repository import ConvexCalendarRepository
from src.services.convex_client import ConvexClient
from src.services.structured_records_service import StructuredRecordsService
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
from src.services.convex_staff_memory_repository import (
    ConvexStaffMemoryRepository,
)
from src.services.document_memory_service import (
    init_document_memory,
    get_document_memory,
)
from src.services.history_log_service import (
    init_history_log,
    get_history_log,
    EventType,
    LogLevel,
)
from src.services.startup_data_loader import startup_loader
from src.utils.tracing import setup_tracing

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)
STAFF_MEMORY_STORAGE_PATH = Path("./data/staff_memory/staff_memory.json")

# ============================================================================
# LINE Bot SDK Configuration
# ============================================================================
configuration = Configuration(access_token=settings.line_channel_access_token)
webhook_parser = linebot.v3.WebhookParser(settings.line_channel_secret)

# ============================================================================
# Global Agent Router (Singleton Pattern)
# ============================================================================
agent_router = AgentRouter()
structured_records_service: Optional[StructuredRecordsService] = None
STRUCTURED_RECORD_WRITE_TIMEOUT_SECONDS = 0.5

# Bot's own user ID for self-message detection (prevents infinite loops)
bot_user_id: Optional[str] = None


def _get_chat_id_for_event(event: MessageEvent) -> Optional[str]:
    """Normalize LINE source identifiers into the app's chat_id format."""
    source = getattr(event, "source", None)
    if not source:
        return None
    if getattr(source, "group_id", None):
        return f"group_{source.group_id}"
    if getattr(source, "room_id", None):
        return f"room_{source.room_id}"
    if getattr(source, "user_id", None):
        return f"user_{source.user_id}"
    return None


def _normalize_route_result(
    route_outcome: object,
    fallback_message_type: Optional[str],
) -> RouteResult:
    """Keep webhook integration compatible with legacy bool route results."""
    if isinstance(route_outcome, RouteResult):
        return route_outcome
    return RouteResult(
        handled=bool(route_outcome),
        agent_name=None,
        message_type=fallback_message_type,
    )


async def _write_structured_record(coro, action: str) -> None:
    """Write a structured record without breaking inbound webhook handling."""
    try:
        await asyncio.wait_for(
            coro,
            timeout=STRUCTURED_RECORD_WRITE_TIMEOUT_SECONDS,
        )
    except Exception as error:
        logger.warning("⚠️ Structured record write failed during %s: %s", action, error)


async def _run_best_effort_structured_task(coro, action: str) -> None:
    try:
        await coro
    except Exception as error:
        logger.warning("⚠️ Structured record task failed during %s: %s", action, error)


def _schedule_best_effort_structured_task(coro, action: str) -> None:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    loop.create_task(_run_best_effort_structured_task(coro, action))


async def _upsert_known_line_user(
    event: MessageEvent,
    line_bot_api: MessagingApi,
) -> None:
    """Best-effort user upsert for message events with a known LINE user ID."""
    if structured_records_service is None:
        return

    source = getattr(event, "source", None)
    line_user_id = getattr(source, "user_id", None) if source else None
    if not line_user_id:
        return

    display_name = None
    if getattr(source, "type", None) == "user":
        try:
            profile = await asyncio.to_thread(line_bot_api.get_profile, line_user_id)
            display_name = getattr(profile, "display_name", None)
        except Exception as error:
            logger.warning(
                "⚠️ Failed to load LINE profile for %s: %s",
                line_user_id,
                error,
            )

    await _write_structured_record(
        structured_records_service.upsert_user(
            line_user_id=line_user_id,
            display_name=display_name,
            role=None,
        ),
        action="upsert_user",
    )


async def _record_inbound_interaction(
    event: MessageEvent,
    route_result: RouteResult,
) -> None:
    """Persist an inbound interaction after routing completes."""
    if structured_records_service is None:
        return

    source = getattr(event, "source", None)
    line_user_id = getattr(source, "user_id", None) if source else None
    source_chat_id = _get_chat_id_for_event(event)
    if not line_user_id or not source_chat_id or not route_result.message_type:
        return

    text_preview = None
    if isinstance(event.message, TextMessageContent):
        text_preview = event.message.text

    await _write_structured_record(
        structured_records_service.record_interaction(
            line_user_id=line_user_id,
            source_chat_id=source_chat_id,
            message_type=route_result.message_type,
            direction="inbound",
            text_preview=text_preview,
            handled_agent=route_result.agent_name,
        ),
        action="record_interaction",
    )


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
    global bot_user_id, structured_records_service

    logger.info("=" * 80)
    logger.info("🚀 Ms. Green Assistant - Starting Up")
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

    structured_records_service = None
    convex_client: Optional[ConvexClient] = None
    convex_primary_backend = settings.is_convex_primary_backend()
    if convex_primary_backend and not settings.is_convex_configured():
        raise RuntimeError(
            "Convex primary backend selected, but Convex is not configured. "
            "Set CONVEX_DEPLOYMENT_URL and CONVEX_SYNC_TOKEN or switch "
            "PERSISTENCE_BACKEND back to local."
        )

    # ========================================================================
    # PHASE 2: HTTP Client Initialization
    # ========================================================================
    logger.info("📡 Initializing optimized HTTP client pool...")
    http_client_pool = create_optimized_http_client()
    openrouter_service.set_client(http_client_pool)
    brave_search_service.set_client(http_client_pool)
    github_models_service.set_client(http_client_pool)
    logger.info("✅ HTTP client pool ready with connection pooling enabled")

    if convex_primary_backend:
        convex_client = ConvexClient(
            base_url=str(settings.convex_deployment_url),
            sync_token=settings.convex_sync_token or "",
            http_client=http_client_pool,
            timeout_seconds=float(settings.convex_request_timeout_seconds),
        )
        structured_records_service = StructuredRecordsService(
            convex_client=convex_client
        )
        logger.info("🧱 Structured records service enabled for Convex primary backend")

    configure_bot_identity_service(
        storage_path=settings.bot_identity_storage_path,
        default_name=settings.bot_identity_default_name,
        default_aliases=settings.get_bot_identity_default_aliases(),
    )

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
    # PHASE 2a1: Document Memory Initialization
    # ========================================================================
    if settings.document_memory_enabled:
        if settings.is_document_memory_configured():
            document_service = init_document_memory(
                hf_token=settings.hf_memory_token,
                hf_repo_id=settings.document_hf_repo_id,
                storage_path=settings.document_storage_path,
                max_file_size_mb=settings.document_max_file_size_mb,
                max_text_chars=settings.document_max_text_chars,
            )
            logger.info(
                f"📄 Document memory enabled (HF Hub: {settings.document_hf_repo_id})"
            )
        else:
            document_service = init_document_memory(
                storage_path=settings.document_storage_path,
                max_file_size_mb=settings.document_max_file_size_mb,
                max_text_chars=settings.document_max_text_chars,
            )
            logger.info("📄 Document memory enabled (local-only)")
    else:
        logger.info("📄 Document memory disabled")

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
    calendar_backend = "local"
    calendar_repository = None
    if settings.is_calendar_configured():
        if convex_client is not None:
            calendar_repository = ConvexCalendarRepository(convex_client)
            calendar_backend = "convex"
        elif settings.is_calendar_hf_configured():
            calendar_backend = "hf"

        calendar_service.configure(
            storage_path=settings.calendar_data_path,
            hf_token=(
                settings.hf_memory_token
                if calendar_backend == "hf"
                else None
            ),
            hf_repo_id=(
                settings.calendar_hf_repo_id
                if calendar_backend == "hf"
                else None
            ),
            sync_interval_seconds=settings.calendar_sync_interval_seconds,
            repository=calendar_repository,
        )
        logger.info(f"📅 Calendar service enabled (path: {settings.calendar_data_path})")
        
        if calendar_backend == "hf":
            logger.info(f"☁️ Calendar HF sync enabled: {settings.calendar_hf_repo_id}")
        elif calendar_backend == "convex":
            logger.info("🧱 Calendar persistence routed through Convex")
        
        # Configure reminder service (will be started later after LINE API is ready)
        reminder_service.configure(
            reminder_hour=settings.calendar_reminder_hour,
        )
        logger.info(f"⏰ Reminder service configured (daily at {settings.calendar_reminder_hour}:00 Bangkok)")
    else:
        logger.info("📅 Calendar service disabled")

    from src.services.staff_memory_service import StaffMemoryService

    staff_memory_backend = "convex" if convex_client is not None else "local"
    staff_memory_repository = None
    if convex_client is not None:
        staff_memory_repository = ConvexStaffMemoryRepository(convex_client)

    staff_memory_service = StaffMemoryService(
        STAFF_MEMORY_STORAGE_PATH,
        repository=staff_memory_repository,
    )

    # ========================================================================
    # PHASE 2a4: Synchronous Data Load from configured persistence backends (CRITICAL)
    # ========================================================================
    # This ensures all data is checked/downloaded BEFORE the app starts serving requests.
    # Without this, the app could appear to have lost state because remote backends have
    # not been validated or HF downloads have not completed yet.
    logger.info("🔄 Loading persistent data from configured backends...")
    load_results = await startup_loader.ensure_data_loaded(
        calendar_service=calendar_service if settings.is_calendar_configured() else None,
        staff_memory_service=staff_memory_service,
        memory_service=get_conversation_memory() if settings.conversation_memory_enabled else None,
        document_service=get_document_memory() if settings.document_memory_enabled else None,
        history_log=get_history_log() if settings.is_history_log_configured() else None,
        convex_client=convex_client,
        calendar_backend=calendar_backend,
        staff_memory_backend=staff_memory_backend,
        convex_health_required=settings.convex_require_healthcheck_on_startup,
    )
    if load_results["calendar"]:
        logger.info(f"✅ Calendar data loaded: {len(calendar_service._events)} events")
    if load_results["backup_created"]:
        logger.info("✅ LLM-readable backup created for disaster recovery")
    if load_results.get("documents"):
        logger.info("✅ Document data loaded")

    # ========================================================================
    # PHASE 2b: AI Translation Configuration
    # ========================================================================
    logger.info("✅ AI translation configured (GitHub Models -> OpenRouter fallback)")

    # ========================================================================
    # PHASE 3: Agent Registration
    # ========================================================================
    logger.info("📋 Registering intelligent agents...")

    # Import agents here (after HTTP client is ready)
    from src.agents.help_agent import HelpAgent
    from src.agents.admin_agent import AdminAgent
    from src.agents.calendar_agent import CalendarAgent
    from src.agents.review_agent import ReviewAgent
    from src.agents.document_memory_agent import DocumentMemoryAgent
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

    review_agent = ReviewAgent(
        staff_memory_service=staff_memory_service,
        bot_user_id=bot_user_id,
    )
    agent_router.register_agent(review_agent)
    logger.info("📝 Review Agent registered (explicit review and DM follow-up)")

    # Register Document Memory Agent (Priority: 8 - Handles PDF/DOCX uploads)
    if settings.document_memory_enabled:
        document_service = get_document_memory()
        if document_service:
            document_agent = DocumentMemoryAgent(document_service=document_service)
            agent_router.register_agent(document_agent)
            logger.info("📄 Document Memory Agent registered (PDF/DOCX storage)")
        else:
            logger.info("📄 Document Memory Agent not registered (service unavailable)")
    else:
        logger.info("📄 Document Memory Agent not registered (disabled)")

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
    logger.info("✅ Ms. Green is READY to serve! 🎉")
    logger.info("=" * 80)

    yield

    # ========================================================================
    # GRACEFUL SHUTDOWN
    # ========================================================================
    logger.info("=" * 80)
    logger.info("🛑 Ms. Green - Shutting down gracefully...")
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
    reminder_service.stop_scheduler(scheduler_service)
    logger.info("✅ Reminder service stopped")

    # Stop calendar service HF Hub sync
    calendar_service.stop()
    logger.info("✅ Calendar service stopped")

    # Log shutdown event
    history_svc = get_history_log()
    if history_svc:
        await history_svc.log(
            event_type=EventType.SHUTDOWN,
            message="🛑 Ms. Green Assistant shutting down gracefully",
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

    # Stop document memory scheduler (HF Hub sync)
    document_svc = get_document_memory()
    if document_svc:
        document_svc.stop()
        logger.info("✅ Document memory scheduler stopped")

    await http_client_pool.aclose()
    logger.info("✅ HTTP client pool closed")
    structured_records_service = None

    logger.info("👋 Ms. Green shutdown complete. Goodbye!")
    logger.info("=" * 80)


# ============================================================================
# FastAPI Application Initialization
# ============================================================================
app = FastAPI(
    title="Ms. Green - AI Assistant",
    description="Production-grade LINE assistant with AI translation and intelligent agent routing",
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
        "service": "Ms. Green Assistant",
        "version": "3.0.0",
        "api_docs": "/docs" if settings.debug else "disabled",
        "features": {
            "translation": "AI translation",
            "translation_backend": "ai",
        },
    }


@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Cheap liveness endpoint for process-level monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "process": "alive",
            "startup_data": "ready" if startup_loader.is_ready() else "loading",
            "agents_registered": len(agent_router.list_agents()),
        },
    }


@app.get("/readiness", tags=["Health"])
async def readiness_check(response: Response) -> Dict[str, Any]:
    """
    Readiness probe for orchestration systems.

    Returns detailed status of critical dependencies.
    """
    agents_status = agent_router.list_agents()
    startup_ready = startup_loader.is_ready()
    ready = startup_ready and len(agents_status) > 0

    response.status_code = 200 if ready else 503

    return {
        "ready": ready,
        "checks": {
            "startup_data": "ready" if startup_ready else "loading",
            "agents_registered": len(agents_status),
        },
        "translation_backend": "ai",
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
    try:
        # Extract signature and body inside the guarded block so unexpected
        # setup failures still use the generic webhook error response.
        signature = request.headers.get("X-Line-Signature", "")
        body = await request.body()
        body_text = body.decode("utf-8")

        logger.info(f"📨 Received webhook request ({len(body_text)} bytes)")

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
                        user_id = getattr(event.source, "user_id", None) if event.source else None
                        route_result = RouteResult(
                            handled=False,
                            agent_name=None,
                            message_type=None,
                        )
                        
                        if isinstance(event.message, TextMessageContent):
                            # Store message in buffer for "zeus scrape" feature
                            # NOTE: We now store ALL messages including bot's own messages
                            # This allows Zeus to scrape dates from his own responses
                            chat_id = _get_chat_id_for_event(event)
                            
                            if chat_id and user_id:
                                message_buffer_service.store_message(
                                    chat_id=chat_id,
                                    text=event.message.text,
                                    user_id=user_id,
                                    message_id=event.message.id if hasattr(event.message, 'id') else None
                                )
                            
                            # CRITICAL: Check if message is from bot itself (prevent infinite loop)
                            # Skip agent routing for bot's own messages to prevent responding to itself
                            if bot_user_id and user_id == bot_user_id:
                                logger.debug(
                                    f"🔒 Skipping agent routing for bot's own message (stored in buffer only)"
                                )
                                continue

                            # Route text message to appropriate agent
                            route_result = _normalize_route_result(
                                await agent_router.route_message(event, line_bot_api),
                                fallback_message_type="text",
                            )
                            _schedule_best_effort_structured_task(
                                _record_inbound_interaction(event, route_result),
                                "record_inbound_interaction",
                            )
                            _schedule_best_effort_structured_task(
                                _upsert_known_line_user(event, line_bot_api),
                                "upsert_known_line_user",
                            )
                            await asyncio.sleep(0)

                        elif isinstance(event.message, ImageMessageContent):
                            # Route image message to ProfilerAgent via agent router
                            logger.info(f"📷 Received image message from {user_id}")
                            route_result = _normalize_route_result(
                                await agent_router.route_message(event, line_bot_api),
                                fallback_message_type="image",
                            )
                            _schedule_best_effort_structured_task(
                                _record_inbound_interaction(event, route_result),
                                "record_inbound_interaction",
                            )
                            _schedule_best_effort_structured_task(
                                _upsert_known_line_user(event, line_bot_api),
                                "upsert_known_line_user",
                            )
                            await asyncio.sleep(0)

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

    except Exception:
        logger.error("❌ Webhook processing error", exc_info=True)
        return JSONResponse(
            content={"status": "error", "detail": "Internal server error"},
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app", host=settings.host, port=settings.port, reload=settings.debug
    )
