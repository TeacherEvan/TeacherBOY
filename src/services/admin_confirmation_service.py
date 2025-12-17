"""Admin confirmation workflow (process-local).

Used for sensitive admin actions that should be confirmed in private chat.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Optional
import secrets


@dataclass(frozen=True)
class PendingAdminAction:
    token: str
    action: str
    requested_by_user_id: str
    requested_from_chat_id: str
    payload: dict[str, Any]
    created_at: datetime
    expires_at: datetime


class AdminConfirmationService:
    def __init__(self, default_ttl_seconds: int = 300):
        self._default_ttl_seconds = default_ttl_seconds
        self._pending: dict[str, PendingAdminAction] = {}

    def _generate_token(self) -> str:
        # Short, URL-safe token suitable for typing.
        return secrets.token_urlsafe(6)

    def create(
        self,
        *,
        action: str,
        requested_by_user_id: str,
        requested_from_chat_id: str,
        payload: dict[str, Any],
        ttl_seconds: Optional[int] = None,
    ) -> PendingAdminAction:
        now = datetime.utcnow()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        token = self._generate_token()
        pending = PendingAdminAction(
            token=token,
            action=action,
            requested_by_user_id=requested_by_user_id,
            requested_from_chat_id=requested_from_chat_id,
            payload=payload,
            created_at=now,
            expires_at=now + timedelta(seconds=ttl),
        )
        self._pending[token] = pending
        return pending

    def _cleanup(self) -> None:
        now = datetime.utcnow()
        expired = [tok for tok, p in self._pending.items() if p.expires_at <= now]
        for tok in expired:
            self._pending.pop(tok, None)

    def count_pending(self) -> int:
        self._cleanup()
        return len(self._pending)

    def get(self, token: str) -> Optional[PendingAdminAction]:
        self._cleanup()
        return self._pending.get(token)

    def cancel(self, token: str, user_id: str) -> tuple[bool, str]:
        self._cleanup()
        pending = self._pending.get(token)
        if not pending:
            return False, "❌ Unknown or expired confirmation token."
        if pending.requested_by_user_id != user_id:
            return False, "❌ This token belongs to a different admin."
        self._pending.pop(token, None)
        return True, "✅ Cancelled."

    def confirm(self, token: str, user_id: str) -> tuple[Optional[PendingAdminAction], str]:
        self._cleanup()
        pending = self._pending.get(token)
        if not pending:
            return None, "❌ Unknown or expired confirmation token."
        if pending.requested_by_user_id != user_id:
            return None, "❌ This token belongs to a different admin."
        self._pending.pop(token, None)
        return pending, "✅ Confirmed."


admin_confirmation_service = AdminConfirmationService()
