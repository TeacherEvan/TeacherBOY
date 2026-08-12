"""Coordinator for destructive admin actions that require DM confirmation."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from threading import Lock
from typing import Any

from linebot.v3.messaging import MessagingApi

from src.services.admin_confirmation_service import AdminConfirmationService
from src.services.history_log_service import (
    AccessLevel,
    EventType,
    LogLevel,
    get_history_log,
)
from src.services.rate_limiter import RateLimiter

logger = logging.getLogger(__name__)

_NORMALIZED_CHAT_ID_PREFIXES = ("user_", "group_", "room_")

ParseLeaveTarget = Callable[[str, str | None], tuple[str | None, str | None, str | None]]
PushPreview = Callable[[MessagingApi, str, str], bool]
ExecuteAction = Callable[[str, MessagingApi, Mapping[str, Any]], Awaitable[str]]


@dataclass(frozen=True)
class DestructiveActionRequest:
    action: str
    target_chat_id: str
    payload: dict[str, Any]
    effect_summary: str


class DestructiveActionFlow:
    """Manage DM-only preview, confirmation, and execution for destructive admin actions."""

    _SUPPORTED_ACTIONS = {"leave", "purge", "reset"}

    def __init__(
        self,
        *,
        confirmation_service: AdminConfirmationService,
        rate_limiter: RateLimiter,
        parse_leave_target: ParseLeaveTarget,
        push_preview: PushPreview,
        execute_action: ExecuteAction,
        agent_name: str = "AdminAgent",
    ):
        self._confirmation_service = confirmation_service
        self._rate_limiter = rate_limiter
        self._parse_leave_target = parse_leave_target
        self._push_preview = push_preview
        self._execute_action = execute_action
        self._agent_name = agent_name
        self._reservation_lock = Lock()

    async def request(
        self,
        *,
        action: str,
        current_chat_id: str,
        user_id: str | None,
        arg: str | None,
        line_bot_api: MessagingApi,
    ) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        normalized_action = self._classify_action(action)
        if not normalized_action:
            return "❌ Unknown destructive admin action."

        request, error = self._build_request(
            normalized_action,
            current_chat_id=current_chat_id,
            arg=arg,
        )
        if error or request is None:
            return error or "❌ Could not determine destructive action target."

        reservation_token, created_at, expires_at = self._confirmation_service.issue_token()
        with self._reservation_lock:
            reserved, limit_message = self._rate_limiter.reserve_admin_destructive_request(
                user_id=user_id,
                target_chat_id=request.target_chat_id,
                token=reservation_token,
                expires_at=expires_at,
            )
        if not reserved:
            return limit_message or "⚠️ Destructive admin request blocked."

        preview_text = self._build_preview_text(
            request,
            token=reservation_token,
            expires_at=expires_at,
        )

        pushed = await asyncio.to_thread(self._push_preview, line_bot_api, user_id, preview_text)
        if not pushed:
            self._rate_limiter.release_admin_destructive_request(
                token=reservation_token,
                target_chat_id=request.target_chat_id,
                rollback_history=True,
            )
            return "⚠️ Private preview could not be opened. Start a private chat with the bot and try again."

        pending = self._confirmation_service.create(
            action=normalized_action,
            requested_by_user_id=user_id,
            requested_from_chat_id=current_chat_id,
            payload=request.payload,
            preview_text=request.effect_summary,
            preview_fields={
                "target_chat_id": request.target_chat_id,
                "effect_summary": request.effect_summary,
            },
            token=reservation_token,
            created_at=created_at,
            expires_at=expires_at,
        )
        await self._log_admin_action(
            phase="armed",
            action=normalized_action,
            requested_by_user_id=user_id,
            requested_from_chat_id=current_chat_id,
            target_chat_id=request.target_chat_id,
            metadata={
                "effect_summary": request.effect_summary,
                "token": pending.token,
            },
        )

        if self._is_private_chat(current_chat_id):
            return "✅ Private preview sent. Review it in this chat and confirm when ready."
        return "✅ Private preview sent. Review it in your private chat to continue."

    async def confirm(
        self,
        *,
        chat_id: str,
        user_id: str | None,
        token: str | None,
        line_bot_api: MessagingApi,
    ) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        token_value = (token or "").strip()
        if not token_value:
            return "Usage: /admin confirm <token>"

        if not self._is_private_chat(chat_id):
            return "❌ Please confirm in your private chat with the bot."

        pending = self._confirmation_service.get(token_value)
        if not pending:
            return "❌ Unknown or expired confirmation token."
        if pending.requested_by_user_id != user_id:
            return "❌ This confirmation token belongs to another admin."

        normalized_action = self._classify_action(pending.action)
        if not normalized_action:
            return "❌ Unknown pending action type."

        target_chat_id = self._target_chat_id_from_payload(normalized_action, pending.payload)
        if not target_chat_id:
            return "❌ Pending destructive action is missing a target."

        confirmed, message = self._confirmation_service.confirm(token_value, user_id)
        if not confirmed:
            return message

        try:
            result = await self._execute_action(
                normalized_action,
                line_bot_api,
                confirmed.payload,
            )
            phase = self._execution_phase_for_result(result)
            await self._log_admin_action(
                phase=phase,
                action=normalized_action,
                requested_by_user_id=user_id,
                requested_from_chat_id=confirmed.requested_from_chat_id,
                target_chat_id=target_chat_id,
                metadata={"token": token_value},
            )
            return result
        except Exception as exc:
            await self._log_admin_action(
                phase="failed",
                action=normalized_action,
                requested_by_user_id=user_id,
                requested_from_chat_id=confirmed.requested_from_chat_id,
                target_chat_id=target_chat_id,
                metadata={
                    "token": token_value,
                    "error": str(exc),
                },
            )
            raise
        finally:
            self._rate_limiter.release_admin_destructive_request(
                token=token_value,
                target_chat_id=target_chat_id,
            )

    async def cancel(
        self,
        *,
        chat_id: str,
        user_id: str | None,
        token: str | None,
    ) -> str:
        if not user_id:
            return "❌ Could not determine your LINE user ID."

        token_value = (token or "").strip()
        if not token_value:
            return "Usage: /admin cancel <token>"

        if not self._is_private_chat(chat_id):
            return "❌ Please cancel in your private chat with the bot."

        pending = self._confirmation_service.get(token_value)
        ok, message = self._confirmation_service.cancel(token_value, user_id)
        if ok and pending:
            normalized_action = self._classify_action(pending.action)
            target_chat_id = self._target_chat_id_from_payload(
                normalized_action,
                pending.payload,
            )
            self._rate_limiter.release_admin_destructive_request(
                token=token_value,
                target_chat_id=target_chat_id,
            )
            await self._log_admin_action(
                phase="cancelled",
                action=pending.action,
                requested_by_user_id=user_id,
                requested_from_chat_id=pending.requested_from_chat_id,
                target_chat_id=target_chat_id,
                metadata={"token": token_value},
            )
        return message

    def _build_request(
        self,
        action: str,
        *,
        current_chat_id: str,
        arg: str | None,
    ) -> tuple[DestructiveActionRequest | None, str | None]:
        if action == "leave":
            kind, target_id, error = self._parse_leave_target(current_chat_id, arg)
            if error or not kind or not target_id:
                return None, error or "❌ Could not determine leave target."
            target_chat_id = f"{kind}_{target_id}"
            return (
                DestructiveActionRequest(
                    action=action,
                    target_chat_id=target_chat_id,
                    payload={
                        "kind": kind,
                        "target_id": target_id,
                        "chat_id": target_chat_id,
                    },
                    effect_summary=f"The bot will leave {kind} {target_id}.",
                ),
                None,
            )

        explicit_target = (arg or "").strip()
        target_chat_id: str | None = None
        if explicit_target:
            target_chat_id = self._normalize_explicit_target(explicit_target)
            if not target_chat_id:
                return (
                    None,
                    "❌ Invalid target. Use user_<id>, group_<id>, or room_<id>.",
                )
        else:
            target_chat_id = current_chat_id

        if action == "purge":
            effect_summary = (
                "This will clear bot session state, message history, sleep state, "
                f"and related flow state for {target_chat_id}."
            )
        else:
            effect_summary = f"This will reset bot session state, message history, and sleep state for {target_chat_id}."

        return (
            DestructiveActionRequest(
                action=action,
                target_chat_id=target_chat_id,
                payload={"chat_id": target_chat_id},
                effect_summary=effect_summary,
            ),
            None,
        )

    def _normalize_explicit_target(self, raw_target: str) -> str | None:
        target = raw_target.strip()
        if target.startswith(_NORMALIZED_CHAT_ID_PREFIXES):
            prefix, _, suffix = target.partition("_")
            if suffix:
                return f"{prefix}_{suffix}"
        return None

    def _build_preview_text(
        self,
        request: DestructiveActionRequest,
        *,
        token: str,
        expires_at: datetime,
    ) -> str:
        return (
            "🔐 Admin destructive action preview\n"
            "━━━━━━━━━━━━━━━━\n\n"
            f"Action: {request.action}\n"
            f"Target: {request.target_chat_id}\n"
            f"Effect: {request.effect_summary}\n"
            f"Token: {token}\n"
            f"Expires: {expires_at.strftime('%H:%M:%S')} UTC\n\n"
            f"Confirm: /admin confirm {token}\n"
            f"Cancel: /admin cancel {token}"
        )

    def _target_chat_id_from_payload(
        self,
        action: str | None,
        payload: Mapping[str, Any],
    ) -> str | None:
        if action == "leave":
            chat_id = payload.get("chat_id")
            if isinstance(chat_id, str) and chat_id:
                return chat_id

            kind = payload.get("kind")
            target_id = payload.get("target_id")
            if isinstance(kind, str) and isinstance(target_id, str) and kind and target_id:
                return f"{kind}_{target_id}"
            return None

        chat_id = payload.get("chat_id")
        if isinstance(chat_id, str) and chat_id:
            return chat_id
        return None

    def _classify_action(self, action: str | None) -> str | None:
        normalized = (action or "").strip().lower()
        if normalized in self._SUPPORTED_ACTIONS:
            return normalized
        return None

    def _is_private_chat(self, chat_id: str) -> bool:
        return chat_id.startswith("user_")

    def _execution_phase_for_result(self, result: str) -> str:
        normalized = result.lstrip()
        if normalized.startswith(("❌", "⚠️")):
            return "failed"
        return "executed"

    async def _log_admin_action(
        self,
        *,
        phase: str,
        action: str,
        requested_by_user_id: str,
        requested_from_chat_id: str,
        target_chat_id: str | None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        history_log = get_history_log()
        if not history_log:
            return

        try:
            await history_log.log(
                event_type=EventType.ADMIN_ACTION,
                message=f"Admin destructive action {phase}: {action}",
                level=LogLevel.INFO,
                access_level=AccessLevel.ADMIN,
                chat_id=requested_from_chat_id,
                user_id=requested_by_user_id,
                agent_name=self._agent_name,
                metadata={
                    "phase": phase,
                    "action": action,
                    "target_chat_id": target_chat_id,
                    **(metadata or {}),
                },
            )
        except Exception:
            logger.warning("Failed to write admin destructive audit log", exc_info=True)
