"""Admin Dashboard Handler - Handles admin dashboard commands and rendering."""

import asyncio
from collections.abc import Callable

from linebot.v3.messaging import (
    FlexMessage,
    MessagingApi,
    PushMessageRequest,
    ReplyMessageRequest,
    TextMessage,
)
from linebot.v3.webhooks import MessageEvent

from src.agents.admin.dashboard_builder import (
    build_admin_dashboard,
    build_dashboard_delivery_failure_message,
    build_dashboard_handoff_message,
)
from src.services.admin_confirmation_service import admin_confirmation_service
from src.services.session_manager import session_manager

# Import settings lazily to avoid circular imports
# from src.agents.admin_agent import settings


class AdminDashboardHandler:
    """Handles admin dashboard commands and rendering."""

    _push_flex_to_user: Callable | None = None

    def __init__(
        self,
        is_admin_check: Callable | None = None,
        is_private_chat_check: Callable | None = None,
        push_flex_to_user: Callable | None = None,
        get_chat_id: Callable | None = None,
        persistence_backend: str | None = None,
    ):
        self._is_admin_check = is_admin_check
        self._is_private_chat_check = is_private_chat_check
        self._push_flex_to_user = push_flex_to_user
        self._get_chat_id = get_chat_id
        self._persistence_backend = persistence_backend

    def _build_dashboard(self, target_chat_id: str, user_id: str | None) -> FlexMessage:
        """Build the admin dashboard Flex message."""
        pending_confirmations = 0
        if user_id:
            pending_confirmations = len(admin_confirmation_service.list_pending_for_user(user_id))

        # Use injected persistence_backend or fall back to settings (from AdminAgent's module)
        pb = self._persistence_backend
        if pb is None:
            from src.agents.admin_agent import settings as admin_settings

            pb = admin_settings.persistence_backend

        return build_admin_dashboard(
            target_chat_id=target_chat_id,
            persistence_backend=pb,
            is_sleeping=bool(session_manager.is_sleeping(target_chat_id)),
            pending_confirmations=pending_confirmations,
        )

    async def handle_dashboard_command(
        self,
        event: MessageEvent,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Handle /admin dashboard command."""
        if not await self._is_admin(user_id):
            await self._send_error(
                event,
                line_bot_api,
                "❌ Admin only command.",
            )
            return True

        if not user_id:
            return False

        dashboard = self._build_dashboard(chat_id, user_id)

        if await self._is_private_chat(chat_id):
            if not event.reply_token:
                return False
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[dashboard],
                    notificationDisabled=False,
                ),
            )
            return True

        pushed = False
        if self._push_flex_to_user:
            pushed = await self._push_flex_to_user_impl(line_bot_api, user_id, dashboard)

        response_text = build_dashboard_handoff_message() if pushed else build_dashboard_delivery_failure_message()

        if not event.reply_token:
            return pushed

        await asyncio.to_thread(
            line_bot_api.reply_message,
            ReplyMessageRequest(
                replyToken=event.reply_token,
                messages=[TextMessage(text=response_text, quickReply=None, quoteToken=None)],
                notificationDisabled=False,
            ),
        )
        return True

    async def handle_confirmations_command(
        self,
        event: MessageEvent,
        chat_id: str,
        user_id: str | None,
        line_bot_api: MessagingApi,
    ) -> bool:
        """Handle /admin confirmations command."""
        if not await self._is_admin(user_id):
            await self._send_error(
                event,
                line_bot_api,
                "❌ Admin only command.",
            )
            return True

        if not user_id:
            return False

        if not self._is_private_chat_check or not self._is_private_chat_check(chat_id):
            await self._send_error(
                event,
                line_bot_api,
                "❌ Please open confirmations in your private chat with the bot.",
            )
            return True

        pending_items = admin_confirmation_service.list_pending_for_user(user_id)

        if not pending_items:
            text = "✅ No pending destructive previews for your account."
        else:
            lines = ["🔐 Pending destructive previews"]
            for pending in pending_items:
                target_chat_id = pending.preview_fields.get("target_chat_id") or pending.payload.get("chat_id")
                effect_summary = pending.preview_fields.get("effect_summary") or pending.preview_text
                expires_at = pending.expires_at.strftime("%Y-%m-%d %H:%M UTC")
                lines.extend(
                    [
                        "",
                        f"🎯 Target: {target_chat_id}",
                        f"📋 Effect: {effect_summary}",
                        f"⏱️ Expires: {expires_at}",
                        f"🆔 Token: {pending.token[:8]}...",
                        "---",
                    ]
                )
            text = "\n".join(lines)

        await self._send_reply(
            event,
            line_bot_api,
            text,
        )
        return True

    async def _is_admin(self, user_id: str | None) -> bool:
        """Check if user is admin."""
        if self._is_admin_check:
            result = self._is_admin_check(user_id)
            if asyncio.iscoroutine(result):
                return await result
            return result
        # Default: check privilege service
        from src.services.privilege_service import privilege_service

        return privilege_service.is_admin(user_id) if user_id else False

    async def _is_private_chat(self, chat_id: str) -> bool:
        """Check if chat is private."""
        if self._is_private_chat_check:
            result = self._is_private_chat_check(chat_id)
            if asyncio.iscoroutine(result):
                return await result
            return result
        # Default implementation
        return not chat_id.startswith(("group_", "room_"))

    async def _push_flex_to_user_impl(
        self,
        line_bot_api: MessagingApi,
        user_id: str,
        flex_message: FlexMessage,
    ) -> bool:
        """Push a Flex message to a user's private chat."""
        try:
            if not hasattr(line_bot_api, "push_message"):
                return False
            await asyncio.to_thread(
                line_bot_api.push_message,
                PushMessageRequest(
                    to=user_id,
                    messages=[flex_message],
                    notificationDisabled=False,
                    customAggregationUnits=None,
                ),
            )
            return True
        except Exception:
            return False

    async def _send_reply(
        self,
        event: MessageEvent,
        line_bot_api: MessagingApi,
        text: str,
    ) -> None:
        """Send a text reply."""
        if event.reply_token:
            await asyncio.to_thread(
                line_bot_api.reply_message,
                ReplyMessageRequest(
                    replyToken=event.reply_token,
                    messages=[TextMessage(text=text, quickReply=None, quoteToken=None)],
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
