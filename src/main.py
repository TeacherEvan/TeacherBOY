"""Ms. Green - Production-Grade Multi-Agent LINE Translation Bot.

This module implements a FastAPI application with intelligent agent routing,
high-performance async I/O, and production-ready error handling.
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any

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
from src.services.ban_list_service import ban_list_service, init_ban_list_service
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
from src.services.github_models_service import github_models_service
from src.services.google_translation import google_translation_service
from src.services.harmful_content_detector import harmful_content_detector
from src.services.history_log_service import (
    EventType,
    LogLevel,
    get_history_log,
    init_history_log,
)
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.logging_service import logging_service
from src.services.message_buffer_service import message_buffer_service
from src.services.metrics_service import metrics_service
from src.services.memory_monitor_service import (
    get_memory_monitor,
    init_memory_monitor,
    check_and_auto_flush,
)
from src.services.mod_audit_log import init_mod_audit_log, mod_audit_log
from src.services.mod_mode_service import init_mod_mode_service, mod_mode_service
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
from src.services.warning_service import init_warning_service, warning_service
from src.utils.tracing import setup_tracing

# ============================================================================
# Logging Configuration
# ============================================================================
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
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

# Convex HTTP client for Mod Mode (separate from main pool)
convex_http_client: httpx.AsyncClient | None = None


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
    github_models_service.set_client(http_client_pool)
    nous_inference_service.set_client(http_client_pool)
    gemini_service.set_client(http_client_pool)
    logger.info("✅ HTTP client pool ready with connection pooling enabled")

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
    if settings.images_hf_enabled and settings.images_hf_repo_id:
        if not image_analyzer_session_manager._images_hf_enabled:
            image_analyzer_session_manager._images_hf_token = settings.hf_memory_token
            image_analyzer_session_manager._images_hf_repo_id = settings.images_hf_repo_id
            image_analyzer_session_manager._setup_images_hf_storage()
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

        # Initialize Convex client
        convex_http_client = create_optimized_http_client()
        convex_client = ConvexClient(
            base_url=str(settings.convex_deployment_url),
            sync_token=settings.convex_sync_token or "",
            http_client=convex_http_client,
            timeout_seconds=settings.convex_request_timeout_seconds,
        )

        # Initialize Convex Mod Repository
        convex_mod_repo = ConvexModRepository(convex_client)

        # Initialize mod mode services
        init_mod_mode_service(convex_mod_repo)
        init_ban_list_service(convex_mod_repo)
        init_warning_service(convex_mod_repo)
        logger.info("✅ Mod Mode services initialized (ModModeService, BanListService, WarningService)")

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
        google_translation_service.api_key = settings.google_translate_api_key
        google_translation_service.set_client(http_client_pool)
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
    if mod_mode_service and ban_list_service and warning_service:
        from src.agents.mod_mode_agent import ModModeAgent

        mod_dashboard = ModDashboardBuilder()
        mod_agent = ModModeAgent(
            mod_mode_service=mod_mode_service,
            ban_list_service=ban_list_service,
            warning_service=warning_service,
            harmful_detector=harmful_content_detector,
            audit_log=mod_audit_log,
            dashboard_builder=mod_dashboard,
        )
        agent_router.register_agent(mod_agent)
        logger.info("🛡️ ModModeAgent registered (Priority 4 - group moderation)")
    else:
        logger.info("🛡️ ModModeAgent not registered (Convex not configured)")

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
            auto_flush_mode=settings.memory_monitor_auto_flush_mode,
            auto_flush_days=settings.memory_monitor_auto_flush_days,
        )
        # Start periodic memory check task
        asyncio.create_task(_memory_monitor_check_loop())
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

    await http_client_pool.aclose()
    logger.info("✅ HTTP client pool closed")

    if convex_http_client:
        await convex_http_client.aclose()
        logger.info("✅ Convex HTTP client pool closed")

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
    Liveness-only health check endpoint.

    Returns a cheap process-level status without probing external services.
    """
    agents_registered = len(agent_router.list_agents())

    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "process": "alive",
            "startup_data": "ready" if startup_loader.is_ready() else "loading",
            "agents_registered": agents_registered,
        },
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
        from src.services.history_log_service import get_history_log, DatePreset
        from linebot.v3.messaging import QuickReply, QuickReplyItem, FlexMessage, FlexContainer, ReplyMessageRequest
        from src.config import settings

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
        # Query logs with filter and pagination
        levels = [LogLevel(level_filter)] if level_filter else None
        logs = await history_log.query_logs_preset(preset, levels=levels, limit=20, include_sensitive=False)
        
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

    # Add "View Logs" button to admin dashboard
    # This will be added in the dashboard builder


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
    # Extract signature up front; raw body decoding stays inside the protected path.
    signature = request.headers.get("X-Line-Signature", "")

    try:
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

                        if isinstance(event.message, TextMessageContent):
                            # Store message in buffer for "zeus scrape" feature
                            # NOTE: We now store ALL messages including bot's own messages
                            # This allows Zeus to scrape dates from his own responses
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
                                logger.debug("🔒 Skipping agent routing for bot's own message (stored in buffer only)")
                                continue

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
                        user_id = getattr(event.source, "user_id", None) if getattr(event, "source", None) else None
                        metrics_service.record_friend_added(user_id)
                        logger.info("➕ Follow event received (friend added)")

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
                                logger.info(f"✅ Sent welcome message to new friend {user_id}")
                            except Exception as e:
                                logger.error(f"❌ Failed to send welcome message: {e}")

                    elif isinstance(event, UnfollowEvent):
                        # User blocked/removed bot
                        user_id = getattr(event.source, "user_id", None) if getattr(event, "source", None) else None
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

                    elif isinstance(event, PostbackEvent):
                        # Handle postback events (admin log viewer, mod mode, etc.)
                        await handle_postback_event(event, line_bot_api)

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
        raise HTTPException(status_code=400, detail="Invalid signature. Request rejected for security.")

    except Exception as e:
        logger.error(f"❌ Webhook processing error: {str(e)}", exc_info=True)
        return JSONResponse(
            content={"status": "error", "detail": "Internal server error"},
            status_code=500,
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("src.main:app", host=settings.host, port=settings.port, reload=settings.debug)
