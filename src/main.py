"""Ms. Green - Production-Grade Multi-Agent LINE Translation Bot.

This module implements a FastAPI application with intelligent agent routing,
high-performance async I/O, and production-ready error handling.
"""

import asyncio
import logging
import time
import uuid
from collections import defaultdict
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

# LINE Bot SDK v3 imports
import linebot.v3
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    ApiClient,
    Configuration,
    MessagingApi,
    MessagingApiBlob,
    PushMessageRequest,  # For FollowEvent welcome message (push to user)
    TextMessage,
)
from linebot.v3.webhooks import (
    FollowEvent,
    ImageMessageContent,
    JoinEvent,
    LeaveEvent,
    MemberJoinedEvent,
    MemberLeftEvent,
    MessageEvent,
    PostbackEvent,
    TextMessageContent,
    UnfollowEvent,
)

from src.agents.agent_router import AgentRouter
from src.agents.mod_mode.dashboard import ModDashboardBuilder
from src.config import settings
from src.handlers.message_handler import (
    handle_join_event,
    handle_leave_event,
    handle_member_joined_event,
    handle_member_left_event,
)
from src.services.ban_list_service import init_ban_list_service

if TYPE_CHECKING:
    from src.agents.mod_mode_agent import ModModeAgent
from src.services.bot_identity_service import get_bot_identity_service
from src.services.brave_search_service import brave_search_service
from src.services.calendar_service import calendar_service
from src.services.calendar_session_manager import calendar_session_manager
from src.services.conversation_memory_service import (
    get_conversation_memory,
    init_conversation_memory,
)
from src.services.document_memory_service import (
    DocumentMemoryService,
    get_document_memory,
    init_document_memory,
)
from src.services.gemini_service import gemini_service
from src.services.harmful_content_detector import harmful_content_detector
from src.services.hermes_service import hermes_service
from src.services.hf_inference_service import hf_inference_service
from src.services.history_log_service import (
    EventType,
    LogLevel,
    get_history_log,
    init_history_log,
)
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.logging_service import logging_service
from src.services.memory_monitor_service import (
    check_and_auto_flush,
    get_memory_monitor,
    init_memory_monitor,
)
from src.services.message_buffer_service import message_buffer_service
from src.services.metrics_service import metrics_service
from src.services.mod_audit_log import get_mod_audit_log, init_mod_audit_log
from src.services.mod_mode_service import init_mod_mode_service
from src.services.n1_detector import n1_detector, query_cache
from src.services.news_session_manager import news_session_manager
from src.services.nous_service import nous_inference_service
from src.services.openrouter_service import openrouter_service
from src.services.persistent_storage import is_persistent_storage_available
from src.services.profiler_session_manager import profiler_session_manager
from src.services.rate_limiter import rate_limiter
from src.services.reminder_service import reminder_service
from src.services.scheduler_service import scheduler_service
from src.services.startup_data_loader import startup_loader
from src.services.translation_service import translation_service
from src.services.warning_service import init_warning_service

# ============================================================================
# Correlation ID Context (must be before logging setup)
# ============================================================================
from src.utils.correlation import reset_correlation_id, set_correlation_id
from src.utils.tracing import setup_tracing

# ============================================================================
# Logging Configuration
# ============================================================================
log_level = getattr(logging, settings.log_level.upper(), logging.INFO)
logging.basicConfig(
    level=logging.DEBUG if settings.debug else log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s",
)
logger = logging.getLogger(__name__)


def _service_display_name() -> str:
    """Return the public-facing service name for logs and health endpoints."""
    return get_bot_identity_service().get_profile().display_name


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
bot_user_id: str | None = None

# ModModeAgent reference for postback handlers
mod_mode_agent: "ModModeAgent | None" = None


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
    max_connections = client_config["limits"]["max_connections"]
    max_keepalive = client_config["limits"]["max_keepalive_connections"]
    limits = httpx.Limits(
        max_connections=max_connections,
        max_keepalive_connections=max_keepalive,
    )

    # Update connection pool metrics
    metrics_service.update_connection_pool_stats(
        max_connections=max_connections,
        max_keepalive=max_keepalive,
    )

    return httpx.AsyncClient(
        timeout=client_config["timeout"],
        limits=limits,
        http2=client_config["http2"],
        follow_redirects=True,
    )


async def _memory_monitor_check_loop() -> None:
    """Background task to periodically check memory pressure and trigger auto-flush."""
    monitor = get_memory_monitor()
    if not monitor:
        return

    while True:
        try:
            await asyncio.sleep(monitor.check_interval_seconds)
            await check_and_auto_flush()
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"❌ Memory monitor check failed: {e}", exc_info=True)


# Global reference to memory monitor task for graceful shutdown
_memory_monitor_task: asyncio.Task | None = None


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
    - Observability initialization
    """
    global bot_user_id, convex_http_client

    logging_service.info("🚀 TeacherBOY starting up")

    if is_persistent_storage_available():
        logging_service.info("💾 Persistent HF storage detected at /data", extra={"path": "/data"})
    else:
        logging_service.info("⚠️ Persistent HF storage unavailable; using local ./data fallback", extra={"path": "./data"})

    logger.info("=" * 80)
    logger.info(f"🚀 {_service_display_name()} Multi-Agent System - Starting Up")
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
            logger.info(f"🤖 Bot User ID: {bot_user_id} (self-message detection enabled)")
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
    nous_inference_service.set_client(http_client_pool)
    gemini_service.set_client(http_client_pool)
    hermes_service.set_client(http_client_pool)
    hf_inference_service.set_client(http_client_pool)
    logger.info("✅ HTTP client pool ready with connection pooling enabled")

    # ========================================================================
    # PHASE 2b: Privilege Service Initialization (Admin/Moderator Lists)
    # ========================================================================
    logger.info("🔐 Initializing privilege service (admin/moderator lists)...")
    from src.services.privilege_service import privilege_service

    privilege_service._ensure_settings_loaded()
    logger.info("✅ Privilege service ready")

    # ========================================================================
    # PHASE 2a: Conversation Memory Initialization
    # ========================================================================
    if settings.conversation_memory_enabled:
        if settings.is_conversation_memory_hf_configured():
            init_conversation_memory(
                hf_token=settings.hf_memory_token,
                hf_repo_id=settings.hf_memory_repo_id,
            )
            logger.info(f"💭 Conversation memory enabled (HF Hub: {settings.hf_memory_repo_id})")
        else:
            init_conversation_memory()  # In-memory only
            logger.info("💭 Conversation memory enabled (in-memory only)")
    else:
        logger.info("💭 Conversation memory disabled")

    # ========================================================================
    # PHASE 2a1: Document Memory Initialization
    # ========================================================================
    if settings.document_memory_enabled:
        if settings.is_document_memory_hf_configured():
            init_document_memory(
                hf_token=settings.hf_memory_token,
                hf_repo_id=settings.document_hf_repo_id,
                storage_path=settings.document_storage_path,
                max_file_size_mb=settings.document_max_file_size_mb,
                max_text_chars=settings.document_max_text_chars,
            )
            logger.info(f"📄 Document memory enabled (HF Hub: {settings.document_hf_repo_id})")
        else:
            init_document_memory(
                storage_path=settings.document_storage_path,
                max_file_size_mb=settings.document_max_file_size_mb,
                max_text_chars=settings.document_max_text_chars,
            )
            logger.info("📄 Document memory enabled (local-only)")
    else:
        logger.info("📄 Document memory disabled")

    # ========================================================================
    # PHASE 2a5: Image Analysis HF Persistence Initialization
    # ========================================================================
    if settings.images_hf_repo_id and settings.hf_memory_token:
        image_analyzer_session_manager.configure_hf_storage(settings.hf_memory_token, settings.images_hf_repo_id)
        logger.info(f"🖼️ Image analysis HF persistence enabled: {settings.images_hf_repo_id}")
    else:
        logger.info("🖼️ Image analysis HF persistence disabled")

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
            message=f"⚡ {_service_display_name()} Multi-Agent System starting up!",
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
    # PHASE 2a3b: Convex/Mod Mode Services Initialization
    # ========================================================================
    if settings.is_convex_configured():
        logger.info("🔗 Initializing Convex client for Mod Mode...")
        from src.services.convex_client import ConvexClient
        from src.services.convex_mod_repository import ConvexModRepository

        # Reuse main HTTP client pool for Convex (shared connection pool)
        convex_client = ConvexClient(
            base_url=str(settings.convex_deployment_url),
            sync_token=settings.convex_sync_token or "",
            http_client=http_client_pool,  # Reuse main pool
            timeout_seconds=settings.convex_request_timeout_seconds,
        )

        # Initialize Convex Mod Repository
        convex_mod_repo = ConvexModRepository(convex_client)

        # Initialize mod mode services
        init_mod_mode_service(convex_mod_repo)
        init_ban_list_service(convex_mod_repo)
        init_warning_service(convex_mod_repo)
        logger.info("✅ Mod Mode services initialized (ModModeService, BanListService, WarningService)")

        if settings.is_calendar_configured():
            from src.services.convex_calendar_repository import ConvexCalendarRepository
            convex_calendar_repo = ConvexCalendarRepository(convex_client)
            calendar_service.configure(
                repository=convex_calendar_repo,
            )
            logger.info("✅ Convex Calendar Repository initialized")

        # Initialize ModAuditLog if HF Hub configured
        if settings.is_history_log_configured() and settings.hf_memory_token:
            audit_repo_id = settings.history_log_hf_repo_id or settings.hf_memory_repo_id or "mod-audit-logs"
            init_mod_audit_log(
                token=settings.hf_memory_token,
                repo_id=audit_repo_id,
                local_path="./data/mod_audit",
            )
            logger.info("✅ ModAuditLog initialized (HF Hub audit trail)")
        else:
            logger.info("ℹ️ ModAuditLog not initialized (HF Hub not configured)")
    else:
        logger.info("ℹ️ Convex not configured - Mod Mode services disabled")

    # ========================================================================
    # PHASE 2a4: Synchronous Data Load from HF Hub (CRITICAL)
    # ========================================================================
    # This ensures all data is downloaded BEFORE the app starts serving requests.
    # Without this, the app would appear to have lost all calendar events and memory
    # because CommitScheduler downloads async in the background.
    logger.info("🔄 Loading persistent data from HF Hub...")
    load_results = await startup_loader.ensure_data_loaded(
        calendar_service=calendar_service if settings.is_calendar_configured() else None,
        memory_service=get_conversation_memory() if settings.conversation_memory_enabled else None,
        document_service=get_document_memory() if settings.document_memory_enabled else None,
        history_log=get_history_log() if settings.is_history_log_configured() else None,
    )
    if load_results["calendar"]:
        logger.info(f"✅ Calendar data loaded: {len(calendar_service._events)} events")
    if load_results["backup_created"]:
        logger.info("✅ LLM-readable backup created for disaster recovery")
    if load_results.get("documents"):
        logger.info("✅ Document data loaded")

    # ========================================================================
    # PHASE 2b: Translation Services Configuration
    # ========================================================================
    if settings.is_google_translate_configured():
        logger.info("✅ Google Cloud Translation API configured (PRIMARY)")
    else:
        logger.warning("⚠️  Google Translate API not configured - using fallback providers")

    libre_translate_configured = bool(getattr(settings, "libretranslate_api_url", None)) and bool(
        getattr(settings, "libretranslate_api_key", None)
    )
    if libre_translate_configured:
        logger.info("✅ LibreTranslate configured (FALLBACK)")
    else:
        logger.info("ℹ️  LibreTranslate skipped (no configured URL/key)")

    # ========================================================================
    # PHASE 2c: Hermes Fallback Provider Initialization
    # ========================================================================
    from src.utils.llm_fallback import hermes_service as _hermes_service

    _hermes_service.configure(
        base_url=settings.hermes_base_url or "",
        api_key=settings.hermes_api_key or "",
        model=settings.hermes_model,
    )
    if _hermes_service.is_configured():
        logger.info(f"🔁 Hermes fallback initialized (model={settings.hermes_model})")
    else:
        logger.info("ℹ️ Hermes fallback not configured (skipped)")

    # ========================================================================
    # PHASE 2d: Gemini Provider Initialization
    # ========================================================================
    gemini_service.configure(
        api_key=settings.gemini_api_key or "",
        base_url=settings.gemini_base_url or "",
        model=settings.gemini_model,
        vision_model=settings.gemini_vision_model,
    )
    if gemini_service.is_configured():
        logger.info(f"🤖 Gemini initialized (model={settings.gemini_model})")
    else:
        logger.info("ℹ️ Gemini not configured (skipped)")

    # ========================================================================
    # PHASE 3: Agent Registration
    # ========================================================================
    logger.info("📋 Registering intelligent agents...")

    # Import agents here (after HTTP client is ready)
    from src.agents.admin_agent import AdminAgent
    from src.agents.calendar_agent import CalendarAgent
    from src.agents.document_memory_agent import DocumentMemoryAgent
    from src.agents.help_agent import HelpAgent
    from src.agents.image_analyzer_agent import ImageAnalyzerAgent
    from src.agents.llm_agent import LLMAgent
    from src.agents.news_agent import NewsAgent
    from src.agents.profiler_agent import ProfilerAgent
    from src.agents.search_agent import SearchAgent
    from src.agents.special_news_agent import SpecialNewsAgent
    from src.agents.translation_agent import TranslationAgent
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
        admin_agent = AdminAgent(http_client=http_client_pool, news_api_key=settings.news_api_key)
        agent_router.register_agent(admin_agent)
        if admin_user_ids:
            logger.info(f"🔧 Admin Agent registered with {len(admin_user_ids)} authorized admin(s)")
        else:
            logger.info("🔧 Admin Agent registered (bootstrap enabled via ADMIN_SETUP_KEY)")
    else:
        logger.info("🔧 Admin Agent not registered (no ADMIN_USER_IDS configured)")

    # Register ModModeAgent (Priority: 4 - Intercepts messages in mod-enabled groups)
    # Must be registered before AdminAgent to intercept mod commands first
    # Register regardless of service availability - agent will handle missing services gracefully
    global mod_mode_agent
    from src.agents.mod_mode_agent import ModModeAgent
    from src.services.ban_list_service import get_ban_list_service
    from src.services.mod_mode_service import get_mod_mode_service
    from src.services.warning_service import get_warning_service

    mod_mode_svc = get_mod_mode_service()
    ban_list_svc = get_ban_list_service()
    warning_svc = get_warning_service()

    mod_dashboard = ModDashboardBuilder()
    mod_mode_agent = ModModeAgent(
        mod_mode_service=mod_mode_svc,
        ban_list_service=ban_list_svc,
        warning_service=warning_svc,
        harmful_detector=harmful_content_detector,
        audit_log=get_mod_audit_log(),
        dashboard_builder=mod_dashboard,
    )
    agent_router.register_agent(mod_mode_agent)

    if mod_mode_svc and ban_list_svc and warning_svc:
        logger.info("🛡️ ModModeAgent registered (Priority 4 - group moderation)")
    else:
        logger.info("🛡️ ModModeAgent registered (Priority 4) but running in degraded mode - some features unavailable")

    # Register Calendar Agent (Priority: 6 - Handles calendar/reminder commands)
    if settings.is_calendar_configured():
        calendar_agent = CalendarAgent(calendar_service=calendar_service)
        agent_router.register_agent(calendar_agent)
        logger.info("📅 Calendar Agent registered (events and reminders)")
    else:
        logger.info("📅 Calendar Agent not registered (calendar disabled)")

    # Register Document Memory Agent (Priority: 8 - Handles PDF/DOCX uploads)
    if settings.document_memory_enabled:
        document_service_opt: DocumentMemoryService | None = get_document_memory()
        if document_service_opt is not None:
            document_agent = DocumentMemoryAgent(document_service=document_service_opt)
            agent_router.register_agent(document_agent)
            logger.info("📄 Document Memory Agent registered (PDF/DOCX storage)")
        else:
            logger.info("📄 Document Memory Agent not registered (service unavailable)")
    else:
        logger.info("📄 Document Memory Agent not registered (disabled)")

    # Register Hannibal Profile Agent (Priority: 6 - Psychological profiling from message history)
    if settings.is_any_vision_provider_configured():
        from src.agents.hannibal_agent import HannibalProfileAgent

        hannibal_agent = HannibalProfileAgent(http_client=http_client_pool)
        agent_router.register_agent(hannibal_agent)
        logger.info("🎭 Hannibal Profile Agent registered (message history analysis)")
    else:
        logger.info("🎭 Hannibal Profile Agent not registered (no vision provider configured)")

    # Register Profiler Agent (Priority: 7 - Handles image messages for psychological profiling)
    if settings.is_profiler_configured():
        profiler_agent = ProfilerAgent(http_client=http_client_pool)
        agent_router.register_agent(profiler_agent)
        logger.info(f"🔬 Profiler Agent registered (Model: {settings.profiler_model})")
    else:
        logger.info("🔬 Profiler Agent not registered (profiler disabled)")

    # Register Image Analyzer Agent (Priority: 7 - Handles image Q&A)
    if settings.is_any_vision_provider_configured():
        image_analyzer_agent = ImageAnalyzerAgent(http_client=http_client_pool)
        agent_router.register_agent(image_analyzer_agent)
        logger.info("🖼️ Image Analyzer Agent registered (general image Q&A)")
    else:
        logger.info("🖼️ Image Analyzer Agent not registered (no vision provider configured)")

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
        cache_ttl_seconds=300,  # 5-minute cache for volatile news data
    )
    special_news_agent = SpecialNewsAgent(news_service=special_news_service)
    agent_router.register_agent(special_news_agent)
    logger.info("📰 Special News Agent registered (Thailand tourism, sports, international)")

    # Register News Agent (Priority: 15)
    news_data_service = NewsDataService(http_client=http_client_pool, news_api_key=settings.news_api_key)
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
        logger.info(f"   {status} | {agent_info['name']}: {agent_info['description']} (priority: {agent_info['priority']})")

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

    # Initialize memory monitor (HF Spaces)
    if settings.memory_monitor_enabled:
        init_memory_monitor(
            check_interval_seconds=settings.memory_monitor_check_interval_seconds,
            auto_flush_threshold=settings.memory_monitor_auto_flush_threshold,
            auto_flush_threshold_gb=settings.memory_monitor_auto_flush_threshold_gb,
            auto_flush_mode=settings.memory_monitor_auto_flush_mode,
            auto_flush_days=settings.memory_monitor_auto_flush_days,
        )
        # Start periodic memory check task
        global _memory_monitor_task
        _memory_monitor_task = asyncio.create_task(_memory_monitor_check_loop())
        logger.info("📊 Memory monitor started (HF Spaces auto-scaling enabled)")

    logger.info("✅ All cleanup tasks started")

    logger.info("=" * 80)
    logger.info(f"✅ {_service_display_name()} is READY to serve! 🎉")
    logger.info("=" * 80)

    yield

    # ========================================================================
    # GRACEFUL SHUTDOWN
    # ========================================================================
    logger.info("=" * 80)
    logger.info(f"🛑 {_service_display_name()} - Shutting down gracefully...")
    logger.info("=" * 80)

    # Stop memory monitor task
    logger.info("🧹 Stopping memory monitor task...")
    if _memory_monitor_task and not _memory_monitor_task.done():
        _memory_monitor_task.cancel()
        try:
            await asyncio.wait_for(_memory_monitor_task, timeout=5.0)
        except TimeoutError:
            logger.warning("⚠️ Memory monitor task shutdown timed out")
        except asyncio.CancelledError:
            pass
        logger.info("✅ Memory monitor task stopped")

    # Stop background cleanup tasks
    logger.info("🧹 Stopping background cleanup tasks...")
    await profiler_session_manager.stop_cleanup()
    await news_session_manager.stop_cleanup()
    await image_analyzer_session_manager.stop_cleanup()
    await calendar_session_manager.stop_cleanup()
    await message_buffer_service.stop_cleanup_task()
    await rate_limiter.stop_cleanup()
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
            message=f"🛑 {_service_display_name()} Multi-Agent System shutting down gracefully",
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

    from src.services.mod_audit_log import mod_audit_log
    if mod_audit_log:
        mod_audit_log.close()
        logger.info("✅ Mod audit log scheduler stopped")

    await http_client_pool.aclose()
    logger.info("✅ HTTP client pool closed")

    logger.info(f"👋 {_service_display_name()} shutdown complete. Goodbye!")
    logger.info("=" * 80)


# ============================================================================
# FastAPI Application Initialization
# ============================================================================
app = FastAPI(
    title=f"{_service_display_name()} - Multi-Agent Translation Bot",
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
async def root() -> dict[str, Any]:
    """
    Root endpoint with service information.

    Returns basic information about the service status and version.
    """
    return {
        "status": "operational",
        "service": f"{_service_display_name()} Multi-Agent Translation Bot",
        "version": "3.0.0",
        "api_docs": "/docs" if settings.debug else "disabled",
        "features": {
            "translation": "Thai ↔ English",
            "google_translate": settings.is_google_translate_configured(),
        },
    }


@app.get("/health", tags=["Health"])
async def health_check() -> dict[str, Any]:
    """
    Comprehensive health check endpoint with service status.

    Returns detailed status of all critical services and dependencies.
    """
    agents_registered = len(agent_router.list_agents())
    memory_svc = get_conversation_memory()
    document_svc = get_document_memory()
    history_svc = get_history_log()

    return {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "service": _service_display_name(),
        "version": "3.0.0",
        "checks": {
            "process": "alive",
            "startup_data": "ready" if startup_loader.is_ready() else "loading",
            "agents_registered": agents_registered,
            "conversation_memory": memory_svc.get_stats() if memory_svc else {"enabled": False},
            "document_memory": document_svc.get_stats() if document_svc else {"enabled": False},
            "history_log": history_svc.get_stats() if history_svc else {"enabled": False},
            "calendar": calendar_service.get_stats()
            if hasattr(calendar_service, "get_stats") and settings.is_calendar_configured()
            else {"enabled": settings.is_calendar_configured()},
            "llm_providers": {
                "openrouter": openrouter_service.is_configured(),
                "gemini": gemini_service.is_configured(),
                "hermes": hermes_service.is_configured(),
                "hf_inference": hf_inference_service.is_configured(),
            },
        },
    }


@app.get("/metrics", tags=["Observability"])
async def metrics_dashboard() -> dict[str, Any]:
    """
    Detailed metrics dashboard for observability.

    Returns:
    - Agent RED metrics (Rate, Errors, Duration)
    - Provider latency breakdowns (per model, per request type)
    - System metrics
    """
    snapshot = metrics_service.snapshot()
    n1_stats = n1_detector.get_stats()
    cache_stats = {
        "size": len(query_cache._cache),
        "max_size": query_cache.max_size,
        "ttl_seconds": query_cache.ttl_seconds,
    }

    # Calculate provider summaries
    provider_summaries = {}
    for provider in ["openrouter", "gemini", "hermes", "hf_inference"]:
        total_count = snapshot.provider_latency_ms_count.get(provider, 0)
        if total_count > 0:
            provider_summaries[provider] = {
                "avg_latency_ms": snapshot.provider_latency_ms_total.get(provider, 0) / total_count,
                "total_requests": total_count,
                "models": {},
                "request_types": {},
            }
            # Per-model breakdown
            for key, count in snapshot.provider_model_latency_count.items():
                if key.startswith(f"{provider}:"):
                    model = key.split(":", 1)[1]
                    total = snapshot.provider_model_latency_total.get(key, 0)
                    provider_summaries[provider]["models"][model] = {
                        "avg_latency_ms": total / count if count > 0 else 0,
                        "requests": count,
                    }
            # Per-request-type breakdown
            for key, count in snapshot.provider_request_type_latency_count.items():
                if key.startswith(f"{provider}:"):
                    req_type = key.split(":", 1)[1]
                    total = snapshot.provider_request_type_latency_total.get(key, 0)
                    provider_summaries[provider]["request_types"][req_type] = {
                        "avg_latency_ms": total / count if count > 0 else 0,
                        "requests": count,
                    }

    # Agent RED summaries
    agent_summaries = {}
    for key, count in snapshot.agent_requests_total.items():
        errors = snapshot.agent_errors_total.get(key, 0)
        agent_summaries[key] = {
            "requests": count,
            "errors": errors,
            "error_rate": errors / count if count > 0 else 0.0,
            "avg_latency_ms": snapshot.agent_latency_ms_total.get(key, 0) / snapshot.agent_latency_ms_count.get(key, 1)
            if snapshot.agent_latency_ms_count.get(key, 0) > 0
            else 0.0,
        }

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "uptime_seconds": metrics_service.get_uptime().total_seconds(),
        "system": {
            "translation_requests_total": snapshot.translation_requests_total,
            "translation_google_total": snapshot.translation_google_total,
            "translation_libre_total": snapshot.translation_libre_total,
            "news_requests_total": snapshot.news_requests_total,
            "rate_limited_requests": snapshot.rate_limited_requests,
            "failed_translations": snapshot.failed_translations,
            "admin_commands_total": snapshot.admin_commands_total,
            "unique_users": snapshot.unique_users_count,
            "unique_groups": snapshot.unique_groups_count,
            "cache_hits": snapshot.cache_hits_total,
            "cache_misses": snapshot.cache_misses_total,
            "cache_hit_rate": (
                snapshot.cache_hits_total / (snapshot.cache_hits_total + snapshot.cache_misses_total)
                if (snapshot.cache_hits_total + snapshot.cache_misses_total) > 0
                else 0.0
            ),
        },
        "providers": provider_summaries,
        "agents": agent_summaries,
        "connection_pool": {
            "max_connections": snapshot.connection_pool_max_connections,
            "max_keepalive_connections": snapshot.connection_pool_max_keepalive,
            "active_connections": snapshot.connection_pool_active_connections,
            "idle_connections": snapshot.connection_pool_idle_connections,
            "requests_queued": snapshot.connection_pool_requests_queued,
            "errors": snapshot.connection_pool_errors,
            "utilization_percent": (
                (snapshot.connection_pool_active_connections / snapshot.connection_pool_max_connections * 100)
                if snapshot.connection_pool_max_connections > 0
                else 0.0
            ),
        },
        "n1_queries": n1_stats,
        "cache": cache_stats,
    }


@app.get("/readiness", tags=["Health"])
async def readiness_check(response: Response) -> dict[str, Any]:
    """
    Readiness probe for orchestration systems.

    Returns detailed status of critical dependencies.
    """
    agents_registered = len(agent_router.list_agents())
    startup_ready = startup_loader.is_ready()
    ready = startup_ready and agents_registered > 0

    response.status_code = 200 if ready else 503

    return {
        "ready": ready,
        "checks": {
            "startup_data": "ready" if startup_ready else "loading",
            "agents_registered": agents_registered,
        },
        "google_translate_enabled": settings.is_google_translate_configured(),
    }


async def handle_postback_event(event: PostbackEvent, line_bot_api: MessagingApi) -> None:
    """
    Handle LINE PostbackEvent for interactive features.

    Routes to appropriate handlers based on postback data:
    - Admin log viewer (logs_preset, logs_filter, logs_page, logs_custom_*)
    - Mod mode dashboard actions
    """
    data = event.postback.data if event.postback else ""
    user_id = getattr(event.source, "user_id", None) if event.source else None

    # Admin log viewer postbacks
    if data.startswith("logs_"):
        from linebot.v3.messaging import FlexContainer, FlexMessage, QuickReply, ReplyMessageRequest

        from src.config import settings
        from src.services.history_log_service import DatePreset, get_history_log

        history_log = get_history_log()
        if not history_log:
            return

        # Parse postback data
        # Format: logs_preset=today, logs_filter=level=ERROR, logs_page=2, logs_custom_start=2026-01-15, etc.
        chat_id = None
        if event.source:
            if getattr(event.source, "group_id", None):
                chat_id = f"group_{event.source.group_id}"
            elif getattr(event.source, "room_id", None):
                chat_id = f"room_{event.source.room_id}"
            elif getattr(event.source, "user_id", None):
                chat_id = f"user_{event.source.user_id}"

        if not chat_id or not user_id:
            return

        # Check if user is admin
        admin_user_ids = settings.get_admin_user_ids()
        if user_id not in admin_user_ids:
            return

        # Handle different postback types
        preset = DatePreset.LAST_7_DAYS
        page = 1
        level_filter = None

        if data == "logs_cancel":
            preset = DatePreset.LAST_7_DAYS
        elif data.startswith("logs_preset="):
            preset_str = data.split("=", 1)[1]
            preset_map = {
                "today": DatePreset.TODAY,
                "yesterday": DatePreset.YESTERDAY,
                "last_7_days": DatePreset.LAST_7_DAYS,
                "last_30_days": DatePreset.LAST_30_DAYS,
            }
            preset = preset_map.get(preset_str, DatePreset.LAST_7_DAYS)
        elif data.startswith("logs_filter="):
            # Format: logs_filter=level=ERROR
            filter_part = data.split("=", 1)[1]  # level=ERROR
            if "=" in filter_part:
                filter_key, filter_value = filter_part.split("=", 1)
                if filter_key == "level" and filter_value != "ALL":
                    level_filter = filter_value
        elif data.startswith("logs_page="):
            page_str = data.split("=", 1)[1]
            try:
                page = int(page_str)
            except ValueError:
                page = 1
        elif data == "logs_custom_apply":
            preset = DatePreset.LAST_7_DAYS

        from src.services.history_log_service import LogLevel

        # Query logs with filter and pagination
        levels = [LogLevel(level_filter)] if level_filter else None

        # For total count, get all without limit
        all_logs = await history_log.query_logs_preset(preset, levels=levels, limit=1000)
        total_count = len(all_logs)

        # Calculate total pages
        total_pages = max(1, (total_count + 19) // 20)

        # Adjust page
        page = max(1, min(page, total_pages))

        # Get the specific page of logs
        start_idx = (page - 1) * 20
        end_idx = start_idx + 20
        page_logs = all_logs[start_idx:end_idx]

        bubble = history_log.build_log_flex_bubble(
            logs=page_logs,
            preset=preset,
            filters={"level": level_filter} if level_filter else {},
            page=page,
            total_pages=total_pages,
        )

        # Get quick-reply items
        quick_reply_items = history_log.get_log_quick_reply_items()

        # Send updated Flex message
        flex_message = FlexMessage(
            alt_text=f"Admin Logs - {preset.value}",
            contents=FlexContainer.from_dict(bubble),
        )

        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[flex_message],
                    quickReply=QuickReply(items=quick_reply_items) if quick_reply_items else None,
                    notificationDisabled=False,
                ),
            )
        return

    # ModMode dashboard postbacks (action=mod_*)
    if data.startswith("action=mod_"):
        await handle_modmode_postback(event, line_bot_api, data)
        return

    # Memory flush postbacks (flush_mode=*)
    if data.startswith("flush_mode="):
        await handle_memory_flush_postback(event, line_bot_api, data)
        return

    # Add "View Logs" button to admin dashboard
    # This will be added in the dashboard builder


# ============================================================================
# ModMode Postback Handlers
# ============================================================================


async def handle_modmode_postback(event: PostbackEvent, line_bot_api: MessagingApi, data: str) -> None:
    """Handle ModMode dashboard postback actions."""

    from src.agents.mod_mode.dashboard import ModDashboardBuilder
    from src.services.ban_list_service import get_ban_list_service
    from src.services.mod_mode_service import get_mod_mode_service
    from src.services.warning_service import get_warning_service

    mod_mode_svc = get_mod_mode_service()
    ban_list_svc = get_ban_list_service()
    warning_svc = get_warning_service()

    if not (mod_mode_svc and ban_list_svc and warning_svc):
        return

    user_id = getattr(event.source, "user_id", None) if event.source else None
    if not user_id:
        return

    # Check if user is admin
    from src.services.privilege_service import privilege_service

    if not privilege_service.is_admin(user_id):
        logger.warning(f"⚠️ Non-admin {user_id} attempted ModMode action: {data}")
        return

    source = event.source
    if not source or source.type not in ("group", "room"):
        return

    group_id = source.group_id if source.type == "group" else source.room_id
    if not group_id:
        return

    dashboard = ModDashboardBuilder()

    # Parse action and parameters
    # data format: "action=mod_kick&user=U123" or "action=mod_dashboard"
    action_parts = data.split("&")
    action = action_parts[0].replace("action=", "")

    # Extract user parameter if present
    target_user_id = None
    for part in action_parts[1:]:
        if part.startswith("user="):
            target_user_id = part.split("=", 1)[1]
            break

    try:
        if action == "mod_dashboard":
            info = await mod_mode_svc.get_mod_mode_info(group_id)
            flex_dict = dashboard.build_main_dashboard("Group", group_id, info or {})
            await _send_flex_reply(event, line_bot_api, flex_dict, "Moderator Mode Dashboard")

        elif action == "mod_banlist":
            bans = await ban_list_svc.get_ban_list(group_id)
            flex_dict = dashboard.build_ban_list_dashboard(group_id, bans)
            await _send_flex_reply(event, line_bot_api, flex_dict, "Ban List")

        elif action == "mod_warnlist":
            warnings = await warning_svc.get_warnings(group_id)
            flex_dict = dashboard.build_warn_list_dashboard(group_id, warnings)
            await _send_flex_reply(event, line_bot_api, flex_dict, "Warning List")

        elif action == "mod_settings":
            info = await mod_mode_svc.get_mod_mode_info(group_id)
            flex_dict = dashboard.build_settings_dashboard(group_id, info or {})
            await _send_flex_reply(event, line_bot_api, flex_dict, "Mod Mode Settings")

        elif action == "mod_deactivate":
            await mod_mode_svc.deactivate_mod_mode(group_id)
            from src.services.mod_audit_log import mod_audit_log

            if mod_audit_log:
                await mod_audit_log.log_mode_change(group_id, user_id, "all", False)
            flex_dict = dashboard.build_main_dashboard("Group", group_id, {})
            await _send_flex_reply(event, line_bot_api, flex_dict, "Moderator Mode Deactivated")

        elif action == "mod_set_all":
            await mod_mode_svc.activate_mod_mode(group_id, user_id, "all")
            from src.services.mod_audit_log import mod_audit_log

            if mod_audit_log:
                await mod_audit_log.log_mode_change(group_id, user_id, "all", True)
            info = await mod_mode_svc.get_mod_mode_info(group_id)
            flex_dict = dashboard.build_main_dashboard("Group", group_id, info or {})
            await _send_flex_reply(event, line_bot_api, flex_dict, "Mod Mode: ALL USERS")

        elif action == "mod_set_special":
            if not target_user_id:
                # Show confirmation to select user
                await _send_text_reply(
                    event,
                    line_bot_api,
                    "Usage: Select a user first, then use /modmode special @user",
                )
                return
            await mod_mode_svc.set_special_user(group_id, target_user_id)
            from src.services.mod_audit_log import mod_audit_log

            if mod_audit_log:
                await mod_audit_log.log_mode_change(group_id, user_id, "special", True, target_user_id)
            info = await mod_mode_svc.get_mod_mode_info(group_id)
            flex_dict = dashboard.build_main_dashboard("Group", group_id, info or {})
            await _send_flex_reply(event, line_bot_api, flex_dict, f"Mod Mode: SPECIAL (admin + @{target_user_id})")

        elif action == "mod_kick":
            if target_user_id:
                # Show confirm dialog
                flex_dict = dashboard.build_kick_confirm(group_id, target_user_id, target_user_id)
                await _send_flex_reply(event, line_bot_api, flex_dict, f"Confirm Kick: {target_user_id}")
            else:
                await _send_text_reply(event, line_bot_api, "Select a user to kick")

        elif action == "mod_kick_confirm":
            if target_user_id and mod_mode_agent:
                await mod_mode_agent._kick_user(group_id, target_user_id, line_bot_api, "Kicked by moderator")
                await _send_text_reply(event, line_bot_api, f"✅ Kicked {target_user_id}")
            else:
                await _send_text_reply(event, line_bot_api, "User ID required")

        elif action == "mod_warn":
            if target_user_id:
                flex_dict = dashboard.build_warn_confirm(group_id, target_user_id, target_user_id)
                await _send_flex_reply(event, line_bot_api, flex_dict, f"Confirm Warn: {target_user_id}")
            else:
                await _send_text_reply(event, line_bot_api, "Select a user to warn")

        elif action == "mod_warn_confirm":
            if target_user_id:
                result = await warning_svc.warn_user(group_id, target_user_id, user_id, "Warned by moderator")
                count = result["count"]
                if result["should_ban"]:
                    from src.services.mod_audit_log import mod_audit_log

                    if mod_audit_log:
                        await mod_audit_log.log_ban(group_id, target_user_id, user_id, f"Auto-ban after {count} warnings")
                    if mod_mode_agent:
                        await mod_mode_agent._kick_user(group_id, target_user_id, line_bot_api, f"Auto-ban ({count} warnings)")
                    await _send_text_reply(event, line_bot_api, f"🔨 @{target_user_id} BANNED after {count} warnings")
                else:
                    from src.services.mod_audit_log import mod_audit_log

                    if mod_audit_log:
                        await mod_audit_log.log_warn(group_id, target_user_id, user_id, "Warned by moderator", count)
                    await _send_text_reply(event, line_bot_api, f"⚠️ @{target_user_id} Warning {count}/3")
            else:
                await _send_text_reply(event, line_bot_api, "User ID required")

        elif action == "mod_ban":
            if target_user_id:
                await ban_list_svc.ban_user(group_id, target_user_id, user_id, "Banned by moderator")
                from src.services.mod_audit_log import mod_audit_log

                if mod_audit_log:
                    await mod_audit_log.log_ban(group_id, target_user_id, user_id, "Banned by moderator")
                if mod_mode_agent:
                    await mod_mode_agent._kick_user(group_id, target_user_id, line_bot_api, "Banned by moderator")
                await _send_text_reply(event, line_bot_api, f"🔨 Banned {target_user_id}")
            else:
                await _send_text_reply(event, line_bot_api, "Select a user to ban")

        elif action == "mod_unban":
            if target_user_id:
                await ban_list_svc.unban_user(group_id, target_user_id)
                from src.services.mod_audit_log import mod_audit_log

                if mod_audit_log:
                    await mod_audit_log.log_unban(group_id, target_user_id, user_id)
                await _send_text_reply(event, line_bot_api, f"✅ Unbanned {target_user_id}")
            else:
                await _send_text_reply(event, line_bot_api, "User ID required")

        elif action == "mod_cancel":
            info = await mod_mode_svc.get_mod_mode_info(group_id)
            flex_dict = dashboard.build_main_dashboard("Group", group_id, info or {})
            await _send_flex_reply(event, line_bot_api, flex_dict, "Action Cancelled")

    except Exception as e:
        logger.error(f"❌ ModMode postback error: {e}", exc_info=True)


async def handle_memory_flush_postback(event: PostbackEvent, line_bot_api: MessagingApi, data: str) -> None:
    """Handle memory flush mode selection postback."""
    from linebot.v3.messaging import ReplyMessageRequest, TextMessage

    from src.config import settings
    from src.services.conversation_memory_service import FlushMode, FlushParams, get_conversation_memory
    from src.services.document_memory_service import FlushMode as DocFlushMode
    from src.services.document_memory_service import FlushParams as DocFlushParams
    from src.services.document_memory_service import get_document_memory

    user_id = getattr(event.source, "user_id", None) if event.source else None

    # Check if user is admin
    admin_user_ids = settings.get_admin_user_ids()
    if user_id not in admin_user_ids:
        return

    # Parse mode: flush_mode=time_based|size_based|manual|full
    mode_str = data.split("=", 1)[1] if "=" in data else "time_based"

    mode_map = {
        "time_based": FlushMode.TIME_BASED,
        "size_based": FlushMode.SIZE_BASED,
        "manual": FlushMode.MANUAL_SELECTION,
        "full": FlushMode.FULL_PURGE,
    }

    mode = mode_map.get(mode_str.lower(), FlushMode.TIME_BASED)

    # Execute flush
    conv_memory = get_conversation_memory()
    doc_memory = get_document_memory()

    params = FlushParams(dry_run=False, older_than_days=7)
    results = []

    if conv_memory:
        conv_result = await conv_memory.flush_memory(mode, params)
        results.append(f"💬 Conversations: {conv_result}")

    if doc_memory:
        doc_params = DocFlushParams(dry_run=False, older_than_days=7)
        doc_result = await doc_memory.purge_documents(DocFlushMode(mode.value), doc_params)
        results.append(f"📄 Documents: {doc_result}")

    response_text = "✅ Memory Flush Executed\n━━━━━━━━━━━━━━━━\n\n" + "\n".join(results)

    if event.reply_token:
        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response_text, quickReply=None, quoteToken=None)],
                notificationDisabled=False,
            ),
        )

    logger.info(f"🧹 Manual memory flush by admin {user_id}: {mode_str}")


async def _send_flex_reply(
    event: PostbackEvent,
    line_bot_api: MessagingApi,
    flex_dict: dict,
    alt_text: str,
) -> None:
    """Send a Flex message reply."""
    from linebot.v3.messaging import FlexContainer, FlexMessage, ReplyMessageRequest

    if not event.reply_token:
        return
    flex_message = FlexMessage(  # type: ignore[call-arg]
        alt_text=alt_text,
        contents=FlexContainer.from_dict(flex_dict),
    )
    await asyncio.to_thread(
        line_bot_api.reply_message,
        ReplyMessageRequest(replyToken=event.reply_token, messages=[flex_message], notificationDisabled=False),
    )


async def _send_text_reply(event: PostbackEvent, line_bot_api: MessagingApi, text: str) -> None:
    """Send a simple text reply."""
    from linebot.v3.messaging import ReplyMessageRequest, TextMessage

    if not event.reply_token:
        return
    await asyncio.to_thread(
        line_bot_api.reply_message,
        ReplyMessageRequest(
            replyToken=event.reply_token,
            messages=[TextMessage(text=text, quick_reply=None, quote_token=None)],  # type: ignore[call-arg]
            notificationDisabled=False,
        ),
    )


# Webhook rate limiter - simple in-memory per-IP limiter
_webhook_rate_limiter: dict[str, list[float]] = defaultdict(list)
WEBHOOK_RATE_LIMIT = 100  # requests per minute per IP
WEBHOOK_RATE_WINDOW = 60  # seconds


def _check_webhook_rate_limit(ip: str) -> bool:
    """Check if IP is within rate limit. Returns True if allowed."""
    now = time.time()
    window_start = now - WEBHOOK_RATE_WINDOW
    # Clean old entries
    _webhook_rate_limiter[ip] = [ts for ts in _webhook_rate_limiter[ip] if ts > window_start]
    # Check limit
    if len(_webhook_rate_limiter[ip]) >= WEBHOOK_RATE_LIMIT:
        return False
    _webhook_rate_limiter[ip].append(now)
    return True


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
    # Generate correlation ID for request tracing
    correlation_id = uuid.uuid4().hex[:16]
    token = set_correlation_id(correlation_id)

    try:
        # Rate limit by client IP
        client_ip = request.client.host if request.client else "unknown"
        if not _check_webhook_rate_limit(client_ip):
            logger.warning(f"🚫 Webhook rate limit exceeded for IP: {client_ip}", extra={"correlation_id": correlation_id})
            raise HTTPException(status_code=429, detail="Rate limit exceeded")

        # Extract signature up front; raw body decoding stays inside the protected path.
        signature = request.headers.get("X-Line-Signature", "")

        body = await request.body()
        body_text = body.decode("utf-8")

        logger.info(f"📨 Received webhook request ({len(body_text)} bytes)", extra={"correlation_id": correlation_id})

        # Parse and validate events using LINE SDK v3
        events = webhook_parser.parse(body_text, signature)  # type: ignore[union-attr]

        # Ensure events is a list
        if not isinstance(events, list):
            events = []

        # Create API client for sending replies
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            blob_api = MessagingApiBlob(api_client)

            # Process each event
            for event in events:
                try:
                    if isinstance(event, MessageEvent):
                        user_id = getattr(event.source, "user_id", None) if event.source else None

                        if isinstance(event.message, TextMessageContent):
                            # Store message in buffer for "zeus scrape" feature
                            # Skip bot's own messages to avoid polluting date extraction with bot responses
                            user_id = getattr(event.source, "user_id", None) if event.source else None
                            if bot_user_id and user_id == bot_user_id:
                                logger.debug(
                                    "🔒 Skipping message buffer storage for bot's own message",
                                    extra={"correlation_id": correlation_id},
                                )
                            else:
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
                                        message_id=event.message.id if hasattr(event.message, "id") else None,
                                    )

                            # CRITICAL: Check if message is from bot itself (prevent infinite loop)
                            # Skip agent routing for bot's own messages to prevent responding to itself
                            if bot_user_id and user_id == bot_user_id:
                                logger.debug(
                                    "🔒 Skipping agent routing for bot's own message (stored in buffer only)",
                                    extra={"correlation_id": correlation_id},
                                )
                                continue

                            # Route text message to appropriate agent
                            await agent_router.route_message(event, line_bot_api)

                        elif isinstance(event.message, ImageMessageContent):
                            # Route image message to ProfilerAgent via agent router
                            logger.info(f"📷 Received image message from {user_id}", extra={"correlation_id": correlation_id})
                            
                            # Download and save the image immediately in the background
                            message_id = event.message.id
                            chat_id = None
                            if event.source:
                                if getattr(event.source, "group_id", None):
                                    chat_id = f"group_{event.source.group_id}"
                                elif getattr(event.source, "room_id", None):
                                    chat_id = f"room_{event.source.room_id}"
                                elif getattr(event.source, "user_id", None):
                                    chat_id = f"user_{event.source.user_id}"

                            if chat_id and message_id:
                                try:
                                    logger.info(f"📸 Downloading and saving incoming image {message_id} in background...")
                                    response = await asyncio.to_thread(blob_api.get_message_content, message_id)
                                    if response is not None:
                                        if isinstance(response, bytes):
                                            image_bytes = response
                                        elif isinstance(response, bytearray):
                                            image_bytes = bytes(response)
                                        elif hasattr(response, "read") and callable(getattr(response, "read", None)):
                                            image_bytes = response.read()
                                        else:
                                            chunks = []
                                            for chunk in response:
                                                chunks.append(chunk)
                                            image_bytes = b"".join(chunks)

                                        # Store in filesystem
                                        from src.services.image_storage_service import image_storage_service
                                        image_storage_service.store_incoming_image(chat_id, message_id, image_bytes)
                                except Exception as download_error:
                                    logger.error(f"❌ Failed to download and store background image: {download_error}", exc_info=True)

                            await agent_router.route_message(event, line_bot_api)

                    elif isinstance(event, JoinEvent):
                        # Bot joined a group/room
                        await handle_join_event(event, line_bot_api)

                    elif isinstance(event, FollowEvent):
                        # User added bot as friend
                        user_id = getattr(event.source, "user_id", None) if getattr(event, "source", None) else None
                        metrics_service.record_friend_added(user_id)
                        logger.info("➕ Follow event received (friend added)", extra={"correlation_id": correlation_id})

                        # Send welcome message
                        if user_id:
                            welcome_msg = TextMessage(
                                text=(
                                    "Welcome!\n\n"
                                    "I'm Ms. Green — calm, curious, and actually glad you're here.\n\n"
                                    "You can chat in English or Thai, ask questions, or just say hi. "
                                    "I translate when it helps and I don't rush.\n\n"
                                    "If you ever want a quick intro later, just ask who I am."
                                )
                            )  # type: ignore[call-arg]
                            try:
                                await asyncio.to_thread(
                                    line_bot_api.push_message,
                                    PushMessageRequest(  # type: ignore[call-arg]
                                        to=user_id,
                                        messages=[welcome_msg],
                                        customAggregationUnits=None,  # Explicitly None to avoid SDK serialization issues
                                    ),
                                )
                                logger.info(
                                    f"✅ Sent welcome message to new friend {user_id}",
                                    extra={"correlation_id": correlation_id},
                                )
                            except Exception as e:
                                logger.error(
                                    f"❌ Failed to send welcome message: {e}", extra={"correlation_id": correlation_id}
                                )

                    elif isinstance(event, UnfollowEvent):
                        # User blocked/removed bot
                        user_id = getattr(event.source, "user_id", None) if getattr(event, "source", None) else None
                        metrics_service.record_friend_removed(user_id)
                        logger.info("➖ Unfollow event received", extra={"correlation_id": correlation_id})

                    elif isinstance(event, LeaveEvent):
                        # Bot left a group/room
                        await handle_leave_event(event, line_bot_api)

                    elif isinstance(event, MemberJoinedEvent):
                        # New member joined group/room
                        await handle_member_joined_event(event, line_bot_api)

                    elif isinstance(event, MemberLeftEvent):
                        # Member left group/room
                        await handle_member_left_event(event, line_bot_api)

                    elif isinstance(event, PostbackEvent):
                        # Handle postback events (admin log viewer, mod mode, etc.)
                        await handle_postback_event(event, line_bot_api)

                    else:
                        logger.debug(f"Unhandled event type: {type(event).__name__}", extra={"correlation_id": correlation_id})

                except Exception as event_error:
                    logger.error(
                        f"❌ Error processing event {type(event).__name__}: {event_error}",
                        exc_info=True,
                        extra={"correlation_id": correlation_id},
                    )
                    # Continue processing other events even if one fails
                    continue

        return JSONResponse(content={"status": "success", "processed": len(events)})

    except InvalidSignatureError:
        logger.error("❌ Invalid LINE signature - possible security threat!", extra={"correlation_id": correlation_id})
        raise HTTPException(status_code=400, detail="Invalid signature. Request rejected for security.")

    except Exception as e:
        logger.error(f"❌ Webhook processing error: {str(e)}", exc_info=True, extra={"correlation_id": correlation_id})
        return JSONResponse(
            content={"status": "error", "detail": "Internal server error"},
            status_code=500,
        )

    finally:
        reset_correlation_id(token)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=settings.debug)
