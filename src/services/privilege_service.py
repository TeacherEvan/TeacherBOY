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

    def claim_admin(self, user_id: str) -> None:
        """Grant in-memory admin rights for this running process."""
        if not user_id:
            return
        self._claimed_admin_user_ids.add(user_id)
        logger.info(f"🔓 In-memory admin granted: {user_id}")

    def is_claimed_admin(self, user_id: Optional[str]) -> bool:
        """Return True if user was granted admin via `/admin claim` in this process."""
        return bool(user_id and user_id in self._claimed_admin_user_ids)


# Singleton instance
privilege_service = PrivilegeService()
