"""Main FastAPI application for TeacherBOY LINE translation bot."""

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage
import logging

from src.config import settings
from src.handlers.message_handler import handle_text_message_sync

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.debug else logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="TeacherBOY - Thai/English Translation Bot",
    description="Automatic Thai/English translation bot for LINE",
    version="1.0.0",
)

# Initialize LINE Bot API
line_bot_api = LineBotApi(settings.line_channel_access_token)
handler = WebhookHandler(settings.line_channel_secret)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "service": "TeacherBOY Translation Bot", "version": "1.0.0"}


@app.get("/health")
async def health_check():
    """Health check endpoint for monitoring."""
    return {"status": "healthy"}


@app.post("/webhook")
async def webhook(request: Request):
    """LINE webhook endpoint to receive messages."""
    signature = request.headers.get("X-Line-Signature", "")
    body = await request.body()
    body_text = body.decode("utf-8")

    logger.info(f"Received webhook request")

    try:
        handler.handle(body_text, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception as e:
        logger.error(f"Error handling webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

    return JSONResponse(content={"status": "ok"})


@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    """Handle incoming text messages from LINE."""
    try:
        handle_text_message_sync(event, line_bot_api)
    except Exception as e:
        logger.error(f"Error handling message: {str(e)}")
        line_bot_api.reply_message(
            event.reply_token,
            TextMessage(text="Sorry, an error occurred while processing your message."),
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app", host=settings.host, port=settings.port, reload=settings.debug
    )
