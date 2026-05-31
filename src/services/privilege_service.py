"""Privilege service.

Tracks in-memory privilege that cannot live in environment variables.

Important: unit tests in this repo often patch the module-local `settings` object
inside agents (e.g. `src.agents.news_agent.settings`). If this service depended
directly on `src.config.settings`, those tests would not affect privilege checks.

So this service intentionally ONLY tracks runtime (in-memory) privileges, while
static privileges (admins/moderators from env) are still read via each agent's
module-local `settings`.
"""

from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class PrivilegeService:
    """Tracks and answers privilege queries for users."""

    def __init__(self) -> None:
        self._claimed_admin_user_ids: set[str] = set()
        self._claimed_moderator_user_ids: set[str] = set()
        # Load persisted moderators if available
        try:
            import json, os
            if os.path.exists("data/moderators.json"):
                with open("data/moderators.json", "r") as f:
                    self._claimed_moderator_user_ids = set(json.load(f))
        except Exception as e:
            logger.warning(f"⚠️ Failed to load persisted moderators: {e}")
            
        # Cache admin/moderator lists from settings for performance
        self._env_admin_user_ids: list[str] = []
        self._env_moderator_user_ids: list[str] = []
        self._settings_loaded = False

    def _ensure_settings_loaded(self) -> None:
        """Lazy-load admin/moderator lists from settings."""
        if self._settings_loaded:
            return
        try:
            from src.config import settings
            self._env_admin_user_ids = settings.get_admin_user_ids()
            self._env_moderator_user_ids = settings.get_moderator_user_ids()
            self._settings_loaded = True
        except Exception as e:
            logger.warning(f"⚠️ Failed to load privilege settings: {e}")
            self._env_admin_user_ids = []
            self._env_moderator_user_ids = []

    def claim_admin(self, user_id: str) -> None:
        """Grant in-memory admin rights for this running process."""
        if not user_id:
            return
        self._claimed_admin_user_ids.add(user_id)
        logger.info(f"🔓 In-memory admin granted: {user_id}")

    def claim_moderator(self, user_id: str) -> None:
        """Grant persistent moderator rights."""
        if not user_id:
            return
        self._claimed_moderator_user_ids.add(user_id)
        logger.info(f"🔓 Moderator granted: {user_id}")
        try:
            import json, os
            os.makedirs("data", exist_ok=True)
            with open("data/moderators.json", "w") as f:
                json.dump(list(self._claimed_moderator_user_ids), f)
        except Exception as e:
            logger.error(f"❌ Failed to persist moderators: {e}")

    def is_claimed_admin(self, user_id: Optional[str]) -> bool:
        """Return True if user was granted admin via `/admin claim` in this process."""
        return bool(user_id and user_id in self._claimed_admin_user_ids)

    def is_admin(self, user_id: Optional[str]) -> bool:
        """Check if user is an admin (claimed or environment-based)."""
        if not user_id:
            return False
        # Check claimed admins first (no settings access needed)
        if user_id in self._claimed_admin_user_ids:
            return True
        # Check environment-based admins
        self._ensure_settings_loaded()
        return user_id in self._env_admin_user_ids

    def is_moderator(self, user_id: Optional[str]) -> bool:
        """Check if user is a moderator (claimed or environment-based)."""
        if not user_id:
            return False
        if user_id in self._claimed_moderator_user_ids:
            return True
        self._ensure_settings_loaded()
        return user_id in self._env_moderator_user_ids

    def is_privileged(self, user_id: Optional[str]) -> bool:
        """Check if user is admin or moderator (both get same privileges)."""
        return self.is_admin(user_id) or self.is_moderator(user_id)

    def _reset_for_testing(self) -> None:
        """Reset cached settings for testing. NOT FOR PRODUCTION USE."""
        self._claimed_admin_user_ids.clear()
        self._env_admin_user_ids = []
        self._env_moderator_user_ids = []
        self._settings_loaded = False


# Singleton instance
privilege_service = PrivilegeService()
