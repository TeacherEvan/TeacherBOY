"""Convex repository for Moderator Mode tables."""

import time
from typing import Any

from src.services.convex_client import ConvexClient
from src.services.n1_detector import query_cache


class ConvexModRepository:
    """Data access for modModeState, banList, userWarnings tables."""

    def __init__(self, convex_client: ConvexClient):
        self._client = convex_client

    def _invalidate_group_cache(self, group_id: str) -> None:
        """Invalidate all cached queries for a group."""
        query_cache.invalidate("convex", "/modModeState/getByGroup", group_id)
        query_cache.invalidate("convex", "/banList/getByGroup", group_id)
        query_cache.invalidate("convex", "/banList/getByGroupUser", group_id)
        query_cache.invalidate("convex", "/userWarnings/getByGroup", group_id)
        query_cache.invalidate("convex", "/userWarnings/getByGroupUser", group_id)

    def _invalidate_user_cache(self, group_id: str, user_id: str) -> None:
        """Invalidate cached queries for a specific user in a group."""
        query_cache.invalidate("convex", "/banList/getByGroupUser", group_id, user_id)
        query_cache.invalidate("convex", "/userWarnings/getByGroupUser", group_id, user_id)

    # ===== modModeState =====

    async def get_mod_mode_state(self, group_id: str) -> dict[str, Any] | None:
        """Get mod mode state for a group."""
        response = await self._client.get("/modModeState/getByGroup", {"groupId": group_id})
        return response.get("data") if response else None

    async def set_mod_mode_state(
        self,
        group_id: str,
        mode: str,
        activated_by: str,
        special_user_id: str | None = None,
    ) -> dict[str, Any]:
        """Activate or update mod mode for a group."""
        payload = {
            "groupId": group_id,
            "mode": mode,
            "activatedBy": activated_by,
            "isActive": True,
        }
        if special_user_id:
            payload["specialUserId"] = special_user_id
        response = await self._client.post("/modModeState/upsert", payload)
        self._invalidate_group_cache(group_id)
        return response.get("data", payload)

    async def deactivate_mod_mode(self, group_id: str) -> bool:
        """Deactivate mod mode for a group."""
        response = await self._client.post("/modModeState/deactivate", {"groupId": group_id})
        self._invalidate_group_cache(group_id)
        return response.get("success", False)

    # ===== banList =====

    async def ban_user(
        self,
        group_id: str,
        user_id: str,
        banned_by: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Add user to ban list."""
        payload = {
            "groupId": group_id,
            "userId": user_id,
            "bannedBy": banned_by,
            "bannedAt": int(time.time() * 1000),
        }
        if reason:
            payload["reason"] = reason
        response = await self._client.post("/banList/upsert", payload)
        self._invalidate_group_cache(group_id)
        return response.get("data", payload)

    async def is_user_banned(self, group_id: str, user_id: str) -> bool:
        """Check if user is banned in group."""
        response = await self._client.get("/banList/getByGroupUser", {"groupId": group_id, "userId": user_id})
        return response.get("data") is not None

    async def unban_user(self, group_id: str, user_id: str) -> bool:
        """Remove user from ban list."""
        response = await self._client.post("/banList/remove", {"groupId": group_id, "userId": user_id})
        self._invalidate_user_cache(group_id, user_id)
        return response.get("success", False)

    async def get_ban_list(self, group_id: str) -> list[dict[str, Any]]:
        """Get all banned users in a group."""
        response = await self._client.get("/banList/getByGroup", {"groupId": group_id})
        return response.get("data", [])

    # ===== userWarnings =====

    async def add_warning(
        self,
        group_id: str,
        user_id: str,
        warned_by: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Increment warning count for user (3-strike)."""
        # Get current count
        current = await self.get_warning_count(group_id, user_id)
        new_count = current + 1
        payload = {
            "groupId": group_id,
            "userId": user_id,
            "count": new_count,
            "lastWarningAt": int(time.time() * 1000),
            "lastWarningBy": warned_by,
            "lastWarningReason": reason or "",
            "readByUser": False,
        }
        response = await self._client.post("/userWarnings/upsert", payload)
        self._invalidate_user_cache(group_id, user_id)
        return response.get("data", payload)

    async def get_warning_count(self, group_id: str, user_id: str) -> int:
        """Get current warning count for user."""
        response = await self._client.get("/userWarnings/getByGroupUser", {"groupId": group_id, "userId": user_id})
        data = response.get("data")
        return data.get("count", 0) if data else 0

    async def mark_warning_read(self, group_id: str, user_id: str) -> dict[str, Any]:
        """Mark user's warning as read (for 'read warning counts')."""
        payload = {
            "groupId": group_id,
            "userId": user_id,
            "readByUser": True,
            "readAt": int(time.time() * 1000),
        }
        response = await self._client.post("/userWarnings/upsert", payload)
        self._invalidate_user_cache(group_id, user_id)
        return response.get("data", payload)

    async def get_warnings(self, group_id: str) -> list[dict[str, Any]]:
        """Get all warnings in a group."""
        response = await self._client.get("/userWarnings/getByGroup", {"groupId": group_id})
        return response.get("data", [])

    async def reset_warnings(self, group_id: str, user_id: str) -> bool:
        """Reset warning count for user (admin unban path)."""
        response = await self._client.post("/userWarnings/resetWarnings", {"groupId": group_id, "userId": user_id})
        self._invalidate_user_cache(group_id, user_id)
        return response.get("success", False)
