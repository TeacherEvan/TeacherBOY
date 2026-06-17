"""Admin Model Handler - Handles /admin model commands for NOUS Portal model management."""

import asyncio
import logging

from linebot.v3.messaging import (
    MessageAction,
    MessagingApi,
    QuickReply,
    QuickReplyItem,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

from src.config import settings
from src.services.metrics_service import metrics_service
from src.services.nous_service import NOUS_FREE_MODELS, nous_inference_service

logger = logging.getLogger(__name__)


class AdminModelHandler:
    """Handles /admin model commands for NOUS Portal model management."""

    def __init__(
        self,
        http_client=None,
        is_admin_check=None,
    ):
        self._http_client = http_client
        self._is_admin_check = is_admin_check

    async def handle(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        arg: str | None,
    ) -> bool:
        """
        Handle /admin model command.

        Args:
            event: The LINE message event
            line_bot_api: LINE Bot API client
            arg: Optional subcommand (list, set <model_id>, vision)

        Returns:
            True if handled, False otherwise
        """
        from src.services.nous_service import NOUS_FREE_MODELS

        # Authorization check - only admins can change model
        user_id = getattr(event.source, "user_id", None) if event.source else None
        if not await self._is_admin(user_id):
            await self._send_error(event, line_bot_api, "❌ Admin only command.")
            return True

        parts = (arg or "").strip().split(None, 1)
        subcommand = parts[0] if parts else "list"
        subarg = parts[1] if len(parts) > 1 else None

        metrics_service.record_admin_command()

        if subcommand == "list":
            await self._send_model_list(event, line_bot_api, vision_only=False)
            return True
        elif subcommand == "vision":
            await self._send_model_list(event, line_bot_api, vision_only=True)
            return True
        elif subcommand == "set":
            if not subarg:
                await self._send_error(event, line_bot_api, "❌ Usage: /admin model set <model_id>")
                return True

            # Validate model exists
            valid_models = [m["id"] for m in NOUS_FREE_MODELS]
            if subarg not in valid_models:
                await self._send_error(
                    event,
                    line_bot_api,
                    f"❌ Unknown model: {subarg}\n\nValid models: {', '.join(valid_models)}",
                )
                return True

            # Update config (in-memory only - requires env var + restart to persist)
            # Note: settings.nous_model is a Pydantic field; runtime mutation here is ephemeral.
            # For persistence, admin must set NOUS_MODEL=<id> in .env and restart the service.
            settings.nous_model = subarg
            nous_inference_service.default_model = subarg

            await self._send_reply(
                event,
                line_bot_api,
                f"✅ Default NOUS model set to: {subarg}\n\n⚠️ Change is in-memory only. Set NOUS_MODEL={subarg} in environment and restart to persist.",
            )
            return True
        else:
            await self._send_error(
                event,
                line_bot_api,
                "❌ Unknown model subcommand. Use: list, vision, set <model_id>",
            )
            return True

    async def _send_model_list(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        vision_only: bool = False,
    ) -> None:
        """Send Quick Reply dropdown with available NOUS models."""
        models = self._filter_models(NOUS_FREE_MODELS, vision_only)
        message_text = self._build_model_list_text(models, vision_only)
        quick_reply = self._build_model_quick_reply(models)

        await self._send_reply(event, line_bot_api, message_text, quick_reply)

    def _filter_models(self, models: list[dict], vision_only: bool) -> list[dict]:
        """Filter NOUS models by vision capability."""
        if vision_only:
            return [m for m in models if m["vision"]]
        return models

    def _build_model_list_text(self, models: list[dict], vision_only: bool) -> str:
        """Build the text message for model list display."""
        current_model = nous_inference_service.default_model
        current_vision = nous_inference_service.default_vision_model

        lines = ["🤖 NOUS Portal Models", "━━━━━━━━━━━━━━━━━━━━", ""]
        if vision_only:
            lines.append("👁️ Vision Models Only")
        else:
            lines.append("💬 Chat Models (add 'vision' filter for vision models)")
        lines.append("")

        for m in models:
            marker = ""
            if m["id"] == current_model:
                marker = " ✅ (current chat)"
            elif m["id"] == current_vision:
                marker = " 👁️ (current vision)"
            lines.append(f"• {m['name']} ({m['id']}){marker}")
            lines.append(f"  {m['description']}")
            if m["vision"]:
                lines.append("  👁️ Vision capable")
            lines.append("")

        lines.append("━━━━━━━━━━━━━━━━━━━━")
        lines.append("Commands:")
        lines.append("  /admin model list      - Show all models")
        lines.append("  /admin model vision    - Show vision models only")
        lines.append("  /admin model set <id>  - Set default model")

        return "\n".join(lines)

    def _build_model_quick_reply(self, models: list[dict]) -> QuickReply | None:
        """Build QuickReply buttons for model selection."""
        quick_reply_items = []
        for m in models[:11]:  # LINE limit: 13 items max
            label = m["name"]
            if m["vision"]:
                label += " 👁️"
            quick_reply_items.append(
                QuickReplyItem(
                    type="action",
                    imageUrl=None,
                    action=MessageAction(label=label[:20], text=f"/admin model set {m['id']}"),
                )
            )

        # Add back button
        quick_reply_items.append(
            QuickReplyItem(
                type="action",
                imageUrl=None,
                action=MessageAction(label="🔙 Back", text="/admin model list"),
            )
        )

        return QuickReply(items=quick_reply_items) if quick_reply_items else None

    async def _is_admin(self, user_id: str | None) -> bool:
        """Check if user is admin."""
        if self._is_admin_check:
            return self._is_admin_check(user_id)
        # Default: check privilege service
        from src.services.privilege_service import privilege_service

        return privilege_service.is_admin(user_id) if user_id else False

    async def _send_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
        quick_reply: QuickReply | None = None,
    ) -> None:
        """Send a text reply with optional quick reply."""
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[TextMessage(text=text, quickReply=quick_reply, quoteToken=None)],
                    notificationDisabled=False,
                ),
            )

    async def _send_error(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
    ) -> None:
        """Send an error reply."""
        await self._send_reply(event, line_bot_api, text)
