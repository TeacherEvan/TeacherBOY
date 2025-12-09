"""Main FastAPI application for TeacherBOY LINE translation bot."""

import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

# LINE Bot SDK v3 imports
import linebot.v3
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent,
    JoinEvent,
    LeaveEvent,
    MemberJoinedEvent,
    MemberLeftEvent
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
from src.agents.agent_router import AgentRouter
from src.agents.translation_agent import TranslationAgent
from src.handlers.message_handler import (
    handle_join_event,
    handle_leave_event,
    handle_member_joined_event,
    handle_member_left_event
)

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# LINE Bot SDK v3 Configuration
configuration = Configuration(access_token=settings.line_channel_access_token)
parser = linebot.v3.WebhookParser(settings.line_channel_secret)

# Initialize Agent Router (global singleton)
agent_router = AgentRouter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle and resources."""
    # Startup: Initialize HTTP client for translation services
    logger.info("🚀 Starting up TeacherBOY Multi-Agent System...")
    client = httpx.AsyncClient(timeout=30.0)
    translation_service.set_client(client)
    
    # Initialize Google Translate if API key is provided
    if settings.google_translate_api_key:
        google_translation_service.api_key = settings.google_translate_api_key
        google_translation_service.set_client(client)
        logger.info("✅ Google Cloud Translation API configured (primary)")
    else:
        logger.warning("⚠️  Google Translate API key not found - using LibreTranslate only")
    
    logger.info("✅ LibreTranslate configured (fallback)")
    
    # Register agents
    logger.info("📋 Registering agents...")
    translation_agent = TranslationAgent()
    agent_router.register_agent(translation_agent)
    
    # Log registered agents
    agents_info = agent_router.list_agents()
    logger.info(f"✅ Registered {len(agents_info)} agent(s):")
    for agent_info in agents_info:
        logger.info(f"   - {agent_info['name']}: {agent_info['description']} (priority: {agent_info['priority']})")
    
    yield
    
    # Shutdown: Close HTTP client
    logger.info("Shutting down TeacherBOY...")
    await client.aclose()


# Initialize FastAPI app
app = FastAPI(
    title="TeacherBOY - Thai/English Translation Bot",
    description="Automatic Thai/English translation bot for LINE",
    version="2.0.0",
    lifespan=lifespan
)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "TeacherBOY Translation Bot",
        "version": "2.0.0"
    }


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.post("/webhook")
async def webhook(request: Request):
    """LINE webhook endpoint to receive messages."""
    signature = request.headers.get('X-Line-Signature', '')
    body = await request.body()
    body_text = body.decode('utf-8')
    
    logger.info("Received webhook request")
    
    try:
        # Parse events using v3 SDK (returns list of events)
        events = parser.parse(body_text, signature)  # type: ignore[union-attr]

        # Create API client for replies
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            
            for event in events:  # type: ignore[union-attr]
                if isinstance(event, MessageEvent):
                    if isinstance(event.message, TextMessageContent):
                        # Route message to appropriate agent
                        await agent_router.route_message(event, line_bot_api)
                elif isinstance(event, JoinEvent):
                    # Handle bot joining a group
                    await handle_join_event(event, line_bot_api)
                elif isinstance(event, LeaveEvent):
                    # Handle bot leaving a group
                    await handle_leave_event(event, line_bot_api)
                elif isinstance(event, MemberJoinedEvent):
                    # Handle new member joining
                    await handle_member_joined_event(event, line_bot_api)
                elif isinstance(event, MemberLeftEvent):
                    # Handle member leaving
                    await handle_member_left_event(event, line_bot_api)
                
    except InvalidSignatureError:
        logger.error("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error handling webhook: {str(e)}")
        return JSONResponse(content={"status": "error", "detail": str(e)}, status_code=500)
    
    return JSONResponse(content={"status": "ok"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )
