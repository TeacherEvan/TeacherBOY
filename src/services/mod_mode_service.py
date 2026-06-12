"""Business logic for Moderator Mode activation and state."""

from src.services.convex_mod_repository import ConvexModRepository


class ModModeService:
    """High-level mod mode operations."""

    def __init__(self, repo: ConvexModRepository):
        self._repo = repo

    async def activate_mod_mode(
        self,
        group_id: str,
        admin_id: str,
        mode: str,
        special_user_id: str | None = None,
    ) -> dict:
        """Activate mod mode for a group.

        Args:
            admin_id: Activating admin's LINE user ID
            mode: "all" or "special"
            special_user_id: Required if mode="special"
        """
        if mode not in ("all", "special"):
            raise ValueError(f"Invalid mode: {mode}. Must be 'all' or 'special'")
        if mode == "special" and not special_user_id:
            raise ValueError("special_user_id required for 'special' mode")

        return await self._repo.set_mod_mode_state(
            group_id=group_id,
            mode=mode,
            activated_by=admin_id,
            special_user_id=special_user_id,
        )

    async def is_mod_mode_active(self, group_id: str) -> bool:
        """Check if mod mode is active in group."""
        state = await self._repo.get_mod_mode_state(group_id)
        return state is not None and state.get("isActive", False)

    async def get_mod_mode_info(self, group_id: str) -> dict | None:
        """Get full mod mode info for dashboard."""
        state = await self._repo.get_mod_mode_state(group_id)
        if not state:
            return None
        return {
            "mode": state.get("mode"),
            "activated_by": state.get("activatedBy"),
            "special_user_id": state.get("specialUserId"),
            "is_active": state.get("isActive", False),
        }

    async def is_user_allowed(self, group_id: str, user_id: str) -> bool:
        """Check if user can speak in mod-enabled group."""
        state = await self._repo.get_mod_mode_state(group_id)
        if not state or not state.get("isActive"):
            return True  # No mod mode = everyone allowed

        mode = state.get("mode")
        if mode == "all":
            return True  # Banning checked separately

        if mode == "special":
            admin_id = state.get("activatedBy")
            special_id = state.get("specialUserId")
            return user_id in (admin_id, special_id)

        return True

    async def deactivate_mod_mode(self, group_id: str) -> bool:
        """Deactivate mod mode for a group."""
        return await self._repo.deactivate_mod_mode(group_id)

    async def set_special_user(self, group_id: str, new_special_user_id: str) -> dict:
        """Change the special user in 'special' mode."""
        state = await self._repo.get_mod_mode_state(group_id)
        if not state or state.get("mode") != "special":
            raise ValueError("Group not in 'special' mode")
        return await self._repo.set_mod_mode_state(
            group_id=group_id,
            mode="special",
            activated_by=state["activatedBy"],
            special_user_id=new_special_user_id,
        )


# Singleton instance - used by main.py and other modules
# Requires Convex to be configured
mod_mode_service: ModModeService | None = None


def get_mod_mode_service() -> ModModeService | None:
    """Get the global mod mode service instance."""
    return mod_mode_service


def init_mod_mode_service(repo: "ConvexModRepository") -> ModModeService:
    """Initialize the global mod mode service."""
    global mod_mode_service
    mod_mode_service = ModModeService(repo)
    return mod_mode_service