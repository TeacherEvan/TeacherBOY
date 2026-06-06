"""Consent handling for image analysis literal mode."""

from __future__ import annotations

from collections.abc import Iterable

from src.services.privilege_service import privilege_service


class ImageConsentService:
    """Decides whether a user has consented to literal image analysis."""

    def __init__(self, owner_user_ids: Iterable[str] | None = None) -> None:
        self._owner_user_ids: set[str] = {user_id for user_id in (owner_user_ids or []) if user_id}

    def is_owner_scoped_user(self, user_id: str | None) -> bool:
        return bool(user_id and user_id in self._owner_user_ids)

    def is_consented_owner(self, user_id: str | None) -> bool:
        if not user_id:
            return False
        return privilege_service.is_admin(user_id) or self.is_owner_scoped_user(user_id)

    def should_use_literal_mode(
        self,
        user_id: str | None,
        declared_ai_generated: bool,
    ) -> bool:
        return bool(declared_ai_generated and self.is_consented_owner(user_id))


image_consent_service = ImageConsentService()
