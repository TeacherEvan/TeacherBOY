"""Ban list operations for Moderator Mode."""

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
        reason: str | None = None,
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


# Singleton instance - used by main.py and other modules
# Requires Convex to be configured
ban_list_service: BanListService | None = None


def get_ban_list_service() -> BanListService | None:
    """Get the global ban list service instance."""
    return ban_list_service


def init_ban_list_service(repo: "ConvexModRepository") -> BanListService:
    """Initialize the global ban list service."""
    global ban_list_service
    ban_list_service = BanListService(repo)
    return ban_list_service