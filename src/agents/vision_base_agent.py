import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from linebot.v3.messaging import MessagingApiBlob
from linebot.v3.webhooks import MessageEvent

from src.agents.base_agent import BaseAgent
from src.utils.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)


class VisionBaseAgent(BaseAgent):
    def __init__(self, name: str, description: str, messaging_api_blob: MessagingApiBlob | None = None):
        super().__init__(name, description)
        self.blob_api = messaging_api_blob

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        """Not implemented — VisionBaseAgent is a utility base class, not a handler."""
        return False

    async def handle(self, event: MessageEvent, text: str, line_bot_api) -> bool:
        """Not implemented — VisionBaseAgent is a utility base class, not a handler."""
        return False

    def _get_chat_id(self, event: MessageEvent) -> str:
        """Extract chat ID from event."""
        if event.source and hasattr(event.source, "group_id"):
            group_id = getattr(event.source, "group_id", None)
            if group_id:
                return f"group_{group_id}"
        if event.source and hasattr(event.source, "room_id"):
            room_id = getattr(event.source, "room_id", None)
            if room_id:
                return f"room_{room_id}"
        if event.source:
            user_id = getattr(event.source, "user_id", "unknown")
            return f"user_{user_id}"
        return "user_unknown"

    async def _download_image(self, message_id: str) -> bytes | None:
        """Download image content from LINE servers."""
        try:
            if not self.blob_api:
                logger.error("MessagingApiBlob client not initialized for image download.")
                return None

            response = await self.blob_api.get_message_content(message_id)

            if response is None:
                logger.warning("❌ Response is None from LINE API")
                return None

            if isinstance(response, bytes):
                return response
            elif isinstance(response, bytearray):
                return bytes(response)
            elif hasattr(response, "read") and callable(getattr(response, "read", None)):
                return response.read()
            else:
                chunks = []
                try:
                    for chunk in response:  # type: ignore[union-attr]
                        chunks.append(chunk)
                    return b"".join(chunks)
                except TypeError:
                    logger.error(f"❌ Unexpected response type: {type(response)}")
                    return None

        except Exception as e:
            logger.error(f"❌ Failed to download image {message_id}: {e}", exc_info=True)
            return None

    def _build_vision_message(self, image_data_url: str, question: str, scene_mode: str = "standard") -> list:
        """Build the vision API message structure."""
        bangkok_tz = ZoneInfo("Asia/Bangkok")
        today = datetime.now(bangkok_tz)
        today_str = today.strftime("%B %d, %Y")
        current_year = today.year
        question_lower = (question or "").lower().strip()

        neutral_scene_terms = [
            "baby",
            "newborn",
            "breastfeed",
            "breast feeding",
            "breastfeeding",
            "family",
            "mother",
            "father",
            "child",
            "medical",
            "hospital",
            "food",
            "menu",
            "sign",
            "document",
            "receipt",
            "package",
            "product",
            "pet",
            "home",
            "household",
            "care",
        ]

        extra_conservative_instruction = ""
        if scene_mode == "literal" or any(term in question_lower for term in neutral_scene_terms):
            extra_conservative_instruction = (
                "This looks like a normal everyday scene. "
                "Stay extremely literal and calm; do not sexualize, sensationalize, or assume hidden intent. "
                "If the image is simply caregiving, feeding, family, medical, or household context, describe it plainly. "
            )

        system_prompt = (
            "You are Ms. Green, a polite and observant assistant. "
            "You speak with calm clarity and practical warmth. "
            "When analyzing images, be maximally literal, neutral, and conservative. "
            "Prefer plain description over speculation; if something is ambiguous, say so. "
            "Treat ordinary family, caregiving, infant-feeding, medical, pet, food, document, and household scenes as normal unless the user asks otherwise. "
            "Do not overreact to benign content; keep a steady, careful tone. "
            f"{extra_conservative_instruction}"
            f"TODAY'S DATE: {today_str} (Year: {current_year}) "
            "IMPORTANT: If you detect any dates, deadlines, events, or schedules in the image, "
            "always include a section at the end of your response with the following format: "
            "---DATES_DETECTED---\n"
            '\'[{"date": "2026-01-15", "title": "Event title", "description": "Brief description"}]\'\n'
            "---END_DATES---\n"
            "Use ISO format (YYYY-MM-DD) for dates. ALWAYS use the actual year number (e.g., {current_year}), never 'YYYY' as a placeholder. "
            "Only include this section if you actually find date-related information in the image. "
        )

        return [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": f"Examine this image and answer my question:\\n\\n{question}",
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_data_url,
                        },
                    },
                ],
            },
        ]

    def _get_vision_error_detail(self) -> tuple[int | None, str | None, str | None]:
        """Collect the most recent vision API error detail."""
        from src.services.github_models_service import github_models_service
        from src.services.openrouter_service import openrouter_service

        for svc in (github_models_service, openrouter_service):
            try:
                detail = svc.get_last_error()
            except AttributeError:
                continue
            if detail and detail[1]:
                return detail
        return (None, None, None)
