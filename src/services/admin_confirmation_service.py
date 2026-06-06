"""Admin confirmation workflow (process-local).

Used for sensitive admin actions that should be confirmed in private chat.
"""

from __future__ import annotations

import secrets
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Any


def _default_created_at() -> datetime:
    return datetime.utcnow()


def _default_expires_at() -> datetime:
    return datetime.utcnow() + timedelta(minutes=5)


def _default_preview_fields() -> Mapping[str, Any]:
    return MappingProxyType({})


@dataclass(frozen=True)
class PendingAdminAction:
    token: str
    action: str
    requested_by_user_id: str
    requested_from_chat_id: str
    payload: Mapping[str, Any]
    created_at: datetime = field(default_factory=_default_created_at)
    expires_at: datetime = field(default_factory=_default_expires_at)
    revision: str = ""
    preview_text: str | None = field(default=None, kw_only=True)
    preview_fields: Mapping[str, Any] = field(
        default_factory=_default_preview_fields,
        kw_only=True,
    )

    @property
    def nonce(self) -> str:
        return self.revision


class AdminConfirmationService:
    def __init__(self, default_ttl_seconds: int = 300):
        self._default_ttl_seconds = default_ttl_seconds
        self._pending: dict[str, PendingAdminAction] = {}

    def issue_token(self, ttl_seconds: int | None = None) -> tuple[str, datetime, datetime]:
        now = datetime.utcnow()
        ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
        return self._generate_token(), now, now + timedelta(seconds=ttl)

    def _generate_token(self) -> str:
        # Short, URL-safe token suitable for typing.
        return secrets.token_urlsafe(6)

    def _generate_revision(self) -> str:
        return secrets.token_urlsafe(4)

    def _validate_on_duplicate(self, on_duplicate: str) -> str:
        if on_duplicate not in {"allow", "reject", "replace"}:
            raise ValueError("Invalid on_duplicate value. Expected 'allow', 'reject' or 'replace'.")
        return on_duplicate

    def _mappings_match(
        self,
        left: Mapping[str, Any],
        right: Mapping[str, Any],
    ) -> bool:
        try:
            return left == right
        except Exception:
            return False

    def _freeze_preview_fields(
        self,
        preview_fields: dict[str, Any] | None,
    ) -> Mapping[str, Any]:
        if preview_fields:
            copied_preview_fields = {key: self._snapshot_value(value) for key, value in preview_fields.items()}
        else:
            copied_preview_fields = {}
        return MappingProxyType(copied_preview_fields)

    def _has_custom_object_state(self, value: Any) -> bool:
        if getattr(value, "__dict__", None):
            return True

        slots = getattr(type(value), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        return any(slot not in {"__dict__", "__weakref__"} for slot in slots)

    def _snapshot_custom_object(self, value: Any) -> Any:
        try:
            copied = object.__new__(type(value))
        except Exception:
            return value

        copied_any_state = False
        for attr_name, attr_value in getattr(value, "__dict__", {}).items():
            object.__setattr__(copied, attr_name, self._snapshot_value(attr_value))
            copied_any_state = True

        slots = getattr(type(value), "__slots__", ())
        if isinstance(slots, str):
            slots = (slots,)
        for slot_name in slots:
            if slot_name in {"__dict__", "__weakref__"}:
                continue
            if not hasattr(value, slot_name):
                continue
            object.__setattr__(
                copied,
                slot_name,
                self._snapshot_value(getattr(value, slot_name)),
            )
            copied_any_state = True

        if copied_any_state:
            return copied
        return value

    def _snapshot_value(self, value: Any) -> Any:
        try:
            copied = deepcopy(value)
        except Exception:
            pass
        else:
            if copied is not value:
                if isinstance(value, (dict, list, tuple, set, bytearray)):
                    return copied
                if self._has_custom_object_state(value):
                    return copied
                return value

        if isinstance(value, dict):
            return {key: self._snapshot_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._snapshot_value(item) for item in value]
        if isinstance(value, tuple):
            return tuple(self._snapshot_value(item) for item in value)
        if isinstance(value, set):
            return {self._snapshot_value(item) for item in value}
        return self._snapshot_custom_object(value)

    def _snapshot_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {key: self._snapshot_value(value) for key, value in payload.items()}

    def _copy_pending_action(self, pending: PendingAdminAction) -> PendingAdminAction:
        return PendingAdminAction(
            token=pending.token,
            action=pending.action,
            requested_by_user_id=pending.requested_by_user_id,
            requested_from_chat_id=pending.requested_from_chat_id,
            payload=self._snapshot_payload(pending.payload),
            created_at=pending.created_at,
            expires_at=pending.expires_at,
            revision=pending.revision,
            preview_text=pending.preview_text,
            preview_fields=self._freeze_preview_fields(dict(pending.preview_fields)),
        )

    def _matches_duplicate_identity(
        self,
        pending: PendingAdminAction,
        *,
        action: str,
        requested_by_user_id: str,
        requested_from_chat_id: str,
        payload: Mapping[str, Any],
        preview_text: str | None,
        preview_fields: Mapping[str, Any],
    ) -> bool:
        if pending.action != action:
            return False
        if pending.requested_by_user_id != requested_by_user_id:
            return False
        if pending.requested_from_chat_id != requested_from_chat_id:
            return False
        if pending.preview_text != preview_text:
            return False
        if not self._mappings_match(pending.preview_fields, preview_fields):
            return False
        if not self._mappings_match(pending.payload, payload):
            return False
        return True

    def _find_duplicates(
        self,
        *,
        action: str,
        requested_by_user_id: str,
        requested_from_chat_id: str,
        payload: Mapping[str, Any],
        preview_text: str | None,
        preview_fields: Mapping[str, Any],
    ) -> list[PendingAdminAction]:
        duplicates: list[PendingAdminAction] = []
        for pending in self._pending.values():
            if self._matches_duplicate_identity(
                pending,
                action=action,
                requested_by_user_id=requested_by_user_id,
                requested_from_chat_id=requested_from_chat_id,
                payload=payload,
                preview_text=preview_text,
                preview_fields=preview_fields,
            ):
                duplicates.append(pending)
        return duplicates

    def create(
        self,
        *,
        action: str,
        requested_by_user_id: str,
        requested_from_chat_id: str,
        payload: dict[str, Any],
        preview_text: str | None = None,
        preview_fields: dict[str, Any] | None = None,
        on_duplicate: str = "allow",
        ttl_seconds: int | None = None,
        token: str | None = None,
        created_at: datetime | None = None,
        expires_at: datetime | None = None,
        revision: str | None = None,
    ) -> PendingAdminAction:
        on_duplicate = self._validate_on_duplicate(on_duplicate)
        self._cleanup()
        snapshotted_payload = self._snapshot_payload(payload)
        frozen_preview_fields = self._freeze_preview_fields(preview_fields)
        duplicates = self._find_duplicates(
            action=action,
            requested_by_user_id=requested_by_user_id,
            requested_from_chat_id=requested_from_chat_id,
            payload=snapshotted_payload,
            preview_text=preview_text,
            preview_fields=frozen_preview_fields,
        )
        if duplicates:
            if on_duplicate == "reject":
                return self._copy_pending_action(duplicates[0])
            if on_duplicate == "replace":
                for duplicate in duplicates:
                    self._pending.pop(duplicate.token, None)

        now = created_at or datetime.utcnow()
        if expires_at is None:
            ttl = ttl_seconds if ttl_seconds is not None else self._default_ttl_seconds
            expires_at = now + timedelta(seconds=ttl)
        token = token or self._generate_token()
        pending = PendingAdminAction(
            token=token,
            action=action,
            requested_by_user_id=requested_by_user_id,
            requested_from_chat_id=requested_from_chat_id,
            payload=snapshotted_payload,
            preview_text=preview_text,
            preview_fields=frozen_preview_fields,
            created_at=now,
            expires_at=expires_at,
            revision=revision or self._generate_revision(),
        )
        self._pending[token] = pending
        return self._copy_pending_action(pending)

    def _cleanup(self) -> None:
        now = datetime.utcnow()
        expired = [tok for tok, p in self._pending.items() if p.expires_at <= now]
        for tok in expired:
            self._pending.pop(tok, None)

    def count_pending(self) -> int:
        self._cleanup()
        return len(self._pending)

    def get(self, token: str) -> PendingAdminAction | None:
        self._cleanup()
        pending = self._pending.get(token)
        if pending is None:
            return None
        return self._copy_pending_action(pending)

    def list_pending_for_user(self, user_id: str) -> list[PendingAdminAction]:
        self._cleanup()
        pending_for_user = [pending for pending in self._pending.values() if pending.requested_by_user_id == user_id]
        pending_for_user.sort(key=lambda pending: pending.expires_at)
        return [self._copy_pending_action(pending) for pending in pending_for_user]

    def cancel(self, token: str, user_id: str) -> tuple[bool, str]:
        self._cleanup()
        pending = self._pending.get(token)
        if not pending:
            return False, "❌ Unknown or expired confirmation token."
        if pending.requested_by_user_id != user_id:
            return False, "❌ This token belongs to a different admin."
        self._pending.pop(token, None)
        return True, "✅ Cancelled."

    def confirm(self, token: str, user_id: str) -> tuple[PendingAdminAction | None, str]:
        self._cleanup()
        pending = self._pending.get(token)
        if not pending:
            return None, "❌ Unknown or expired confirmation token."
        if pending.requested_by_user_id != user_id:
            return None, "❌ This token belongs to a different admin."
        self._pending.pop(token, None)
        return self._copy_pending_action(pending), "✅ Confirmed."


admin_confirmation_service = AdminConfirmationService()
