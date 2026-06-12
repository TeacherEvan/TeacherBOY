"""Ban list operations for Moderator Mode."""

from typing import Optional
from src.services.convex_mod_repository import ConvexModRepository


class BanListService:
    """Manage ban lists and banned user checks."""

    def __init__(self, repo: ConvexModRepository):
        self._repo = repo

    async def ban_user(
        self,
        group_id: str,
        user_id: str,
        banned_by: str,
        reason: Optional[str] = None,
    ) -> dict:
        """Ban a user in a group."""
        return await self._repo.ban_user(group_id, user_id, banned_by, reason)

    async def is_banned(self, group_id: str, user_id: str) -> bool:
        """Check if user is banned."""
        return await self._repo.is_user_banned(group_id, user_id)

    async def unban_user(self, group_id: str, user_id: str) -> bool:
        """Remove user from ban list."""
        return await self._repo.unban_user(group_id, user_id)

    async def get_ban_list(self, group_id: str) -> list[dict]:
        """Get all banned users in group."""
        return await self._repo.get_ban_list(group_id)