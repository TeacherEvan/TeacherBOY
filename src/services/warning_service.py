"""3-strike warning system for Moderator Mode."""

from src.services.convex_mod_repository import ConvexModRepository


class WarningService:
    """Manage user warnings with 3-strike auto-ban."""

    MAX_WARNINGS = 3

    def __init__(self, repo: ConvexModRepository):
        self._repo = repo

    async def warn_user(
        self,
        group_id: str,
        user_id: str,
        warned_by: str,
        reason: str | None = None,
    ) -> dict:
        """Issue warning to user. Returns dict with count and should_ban flag."""
        result = await self._repo.add_warning(group_id, user_id, warned_by, reason)
        count = result.get("count", 0)
        return {
            "count": count,
            "should_ban": count >= self.MAX_WARNINGS,
            "reason": reason,
        }

    async def get_warning_count(self, group_id: str, user_id: str) -> int:
        """Get current warning count."""
        return await self._repo.get_warning_count(group_id, user_id)

    async def mark_warning_read(self, group_id: str, user_id: str) -> dict:
        """Mark user's warning as acknowledged (read warning counts)."""
        return await self._repo.mark_warning_read(group_id, user_id)

    async def get_warnings(self, group_id: str) -> list[dict]:
        """Get all warnings in group."""
        return await self._repo.get_warnings(group_id)

    async def reset_warnings(self, group_id: str, user_id: str) -> bool:
        """Admin manually reset warnings (unban path)."""
        # Convex upsert with count=0
        await self._repo.add_warning(group_id, user_id, "system", "reset")
        return True


# Singleton instance - used by main.py and other modules
# Requires Convex to be configured
warning_service: WarningService | None = None


def get_warning_service() -> WarningService | None:
    """Get the global warning service instance."""
    return warning_service


def init_warning_service(repo: "ConvexModRepository") -> WarningService:
    """Initialize the global warning service."""
    global warning_service
    warning_service = WarningService(repo)
    return warning_service
