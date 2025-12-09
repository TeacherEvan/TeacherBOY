"""Main FastAPI application for TeacherBOY LINE translation bot."""

import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage

from src.config import settings
from src.services.translation_service import translation_service
from src.handlers.message_handler import handle_text_message

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle and resources."""
    # Startup: Initialize HTTP client
    logger.info("Starting up TeacherBOY...")
    client = httpx.AsyncClient(timeout=30.0)
    translation_service.set_client(client)
    
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

# Initialize LINE Bot API
line_bot_api = LineBotApi(settings.line_channel_access_token)
handler = WebhookHandler(settings.line_channel_secret)


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
        # Parse events manually to allow async handling
        # handler.parser is available in standard line-bot-sdk v2/v3
        events = handler.parser.parse(body_text, signature)

        for event in events:
            if isinstance(event, MessageEvent) and isinstance(event.message, TextMessage):
                # Handle message asynchronously
                await handle_text_message(event, line_bot_api)
                
    except InvalidSignatureError as e:
        logger.error("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature") from e
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
