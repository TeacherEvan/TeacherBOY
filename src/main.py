"""
TeacherBOY - Production-Grade Multi-Agent LINE Translation Bot.

This module implements a FastAPI application with intelligent agent routing,
high-performance async I/O, and production-ready error handling.
"""

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
    TextMessage,
    FlexMessage,
    FlexBubble,
)
from linebot.v3.exceptions import InvalidSignatureError

from src.config import settings
from src.services.translation_service import translation_service
from src.services.google_translation import google_translation_service
from src.services.scheduler_service import scheduler_service
from src.agents.agent_router import AgentRouter
from src.agents.translation_agent import TranslationAgent
from src.agents.admin_agent import AdminAgent
from src.agents.calendar_agent import CalendarAgent
from src.handlers.message_handler import (
    handle_join_event,
    handle_leave_event,
    handle_member_joined_event,
    handle_member_left_event,
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

# Global references for scheduler callbacks (properly typed)
calendar_agent_instance: Optional[CalendarAgent] = None
line_bot_api_global: Optional[MessagingApi] = None

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
    global calendar_agent_instance, line_bot_api_global, bot_user_id

    logger.info("=" * 80)
    logger.info("🚀 TeacherBOY Multi-Agent System - Starting Up")
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
            bot_info = line_bot_api.get_bot_info()
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
        admin_agent = AdminAgent()
        agent_router.register_agent(admin_agent)
        if admin_user_ids:
            logger.info(f"🔧 Admin Agent registered with {len(admin_user_ids)} authorized admin(s)")
        else:
            logger.info("🔧 Admin Agent registered (bootstrap enabled via ADMIN_SETUP_KEY)")
    else:
        logger.info("🔧 Admin Agent not registered (no ADMIN_USER_IDS configured)")

    # Register Translation Agent (Priority: 10)
    translation_agent = TranslationAgent()
    agent_router.register_agent(translation_agent)

    # Register Calendar Agent if configured (Priority: 20)
    if settings.is_calendar_configured():
        calendar_agent_instance = CalendarAgent(
            group_chat_id=settings.google_calendar_group_id
        )
        agent_router.register_agent(calendar_agent_instance)

        # Initialize global LINE API client for scheduler
        with ApiClient(configuration) as api_client:
            line_bot_api_global = MessagingApi(api_client)

        # ====================================================================
        # PHASE 4: Scheduler Configuration
        # ====================================================================
        scheduler_service.start()

        # Morning reminder job (07:00 by default)
        async def execute_morning_reminder():
            """Execute daily morning calendar reminder."""
            if calendar_agent_instance and line_bot_api_global:
                try:
                    await calendar_agent_instance.send_daily_reminder(
                        line_bot_api_global
                    )
                    logger.info("✅ Morning reminder sent successfully")
                except Exception as e:
                    logger.error(f"❌ Morning reminder failed: {e}", exc_info=True)

        scheduler_service.add_daily_job(
            execute_morning_reminder,
            hour=settings.calendar_morning_hour,
            minute=0,
            name="daily_morning_calendar_reminder",
        )

        # Afternoon overview job (14:00 by default)
        async def execute_afternoon_overview():
            """Execute weekly afternoon calendar overview."""
            if calendar_agent_instance and line_bot_api_global:
                try:
                    await calendar_agent_instance.send_weekly_overview(
                        line_bot_api_global
                    )
                    logger.info("✅ Afternoon overview sent successfully")
                except Exception as e:
                    logger.error(f"❌ Afternoon overview failed: {e}", exc_info=True)

        scheduler_service.add_daily_job(
            execute_afternoon_overview,
            hour=settings.calendar_afternoon_hour,
            minute=0,
            name="weekly_afternoon_calendar_overview",
        )

        logger.info(
            f"📅 Calendar reminders scheduled: "
            f"{settings.calendar_morning_hour:02d}:00 and "
            f"{settings.calendar_afternoon_hour:02d}:00 ({settings.calendar_timezone})"
        )
    else:
        logger.info(
            "📅 Calendar Agent not configured (GOOGLE_CALENDAR_GROUP_ID not set)"
        )

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
    logger.info("✅ TeacherBOY is READY to serve! 🎉")
    logger.info("=" * 80)

    yield

    # ========================================================================
    # GRACEFUL SHUTDOWN
    # ========================================================================
    logger.info("=" * 80)
    logger.info("🛑 TeacherBOY - Shutting down gracefully...")
    logger.info("=" * 80)

    scheduler_service.stop()
    logger.info("✅ Scheduler stopped")

    await http_client_pool.aclose()
    logger.info("✅ HTTP client pool closed")

    logger.info("👋 TeacherBOY shutdown complete. Goodbye!")
    logger.info("=" * 80)


# ============================================================================
# FastAPI Application Initialization
# ============================================================================
app = FastAPI(
    title="TeacherBOY - Multi-Agent Translation Bot",
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
        "service": "TeacherBOY Multi-Agent Translation Bot",
        "version": "3.0.0",
        "api_docs": "/docs" if settings.debug else "disabled",
        "features": {
            "translation": "Thai ↔ English",
            "calendar_reminders": settings.is_calendar_configured(),
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
        "calendar_enabled": settings.is_calendar_configured(),
    }


# ============================================================================
# Debug/Testing Endpoints (Calendar)
# ============================================================================


@app.get("/calendar/test-daily", tags=["Debug"])
async def test_daily_reminder() -> Dict[str, str]:
    """
    Test endpoint to manually trigger daily calendar reminder.

    For debugging and testing the calendar integration.
    """
    global calendar_agent_instance, line_bot_api_global

    if not calendar_agent_instance:
        raise HTTPException(status_code=503, detail="Calendar agent not configured")

    if not line_bot_api_global:
        raise HTTPException(status_code=503, detail="LINE API not initialized")

    try:
        await calendar_agent_instance.send_daily_reminder(line_bot_api_global)
        return {"status": "success", "message": "Daily reminder sent"}
    except Exception as e:
        logger.error(f"Test daily reminder failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to send reminder: {str(e)}"
        )


@app.get("/calendar/test-weekly", tags=["Debug"])
async def test_weekly_overview() -> Dict[str, str]:
    """
    Test endpoint to manually trigger weekly calendar overview.

    For debugging and testing the calendar integration.
    """
    global calendar_agent_instance, line_bot_api_global

    if not calendar_agent_instance:
        raise HTTPException(status_code=503, detail="Calendar agent not configured")

    if not line_bot_api_global:
        raise HTTPException(status_code=503, detail="LINE API not initialized")

    try:
        await calendar_agent_instance.send_weekly_overview(line_bot_api_global)
        return {"status": "success", "message": "Weekly overview sent"}
    except Exception as e:
        logger.error(f"Test weekly overview failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to send overview: {str(e)}"
        )


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

        # Create API client for sending replies
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)

            # Process each event
            for event in events:  # type: ignore[union-attr]
                try:
                    if isinstance(event, MessageEvent):
                        # CRITICAL: Check if message is from bot itself (prevent infinite loop)
                        if (
                            bot_user_id
                            and hasattr(event.source, "user_id")
                            and event.source.user_id == bot_user_id
                        ):
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
