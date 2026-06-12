### Task 2: Create ModModeService (Business Logic Layer)

**Objective:** Service layer wrapping ConvexModRepository with mod mode activation, deactivation, and state queries.

**Files:**
- Create: `src/services/mod_mode_service.py`
- Test: `tests/services/test_mod_mode_service.py`

**Step 1: Write failing test**

```python
# tests/services/test_mod_mode_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.mod_mode_service import ModModeService

@pytest.fixture
def mock_repo():
    return AsyncMock()

@pytest.fixture
def service(mock_repo):
    return ModModeService(mock_repo)

@pytest.mark.asyncio
async def test_activate_mod_mode_all(service, mock_repo):
    mock_repo.set_mod_mode_state.return_value = {"mode": "all", "activatedBy": "U456", "isActive": True}
    result = await service.activate_mod_mode("C123", "U456", "all")
    assert result["mode"] == "all"
    assert result["activatedBy"] == "U456"
    mock_repo.set_mod_mode_state.assert_called_once_with("C123", "all", "U456", None)

@pytest.mark.asyncio
async def test_activate_mod_mode_special(service, mock_repo):
    mock_repo.set_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    result = await service.activate_mod_mode("C123", "U456", "special", "U789")
    assert result["mode"] == "special"
    assert result["specialUserId"] == "U789"
    mock_repo.set_mod_mode_state.assert_called_once_with("C123", "special", "U456", "U789")

@pytest.mark.asyncio
async def test_is_mod_mode_active(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"isActive": True, "mode": "all"}
    result = await service.is_mod_mode_active("C123")
    assert result is True

@pytest.mark.asyncio
async def test_get_mod_mode_info(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    info = await service.get_mod_mode_info("C123")
    assert info["mode"] == "special"
    assert info["special_user_id"] == "U789"

@pytest.mark.asyncio
async def test_is_user_allowed_in_special_mode(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    # Admin allowed
    assert await service.is_user_allowed("C123", "U456") is True
    # Special user allowed
    assert await service.is_user_allowed("C123", "U789") is True
    # Other user NOT allowed
    assert await service.is_user_allowed("C123", "U999") is False

@pytest.mark.asyncio
async def test_is_user_allowed_in_all_mode(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "all", "activatedBy": "U456", "isActive": True}
    # Everyone allowed in 'all' mode (banning handled separately)
    assert await service.is_user_allowed("C123", "U999") is True

@pytest.mark.asyncio
async def test_deactivate_mod_mode(service, mock_repo):
    mock_repo.deactivate_mod_mode.return_value = True
    result = await service.deactivate_mod_mode("C123")
    assert result is True
```

**Step 2: Run test to verify failure**

```bash
pytest tests/services/test_mod_mode_service.py -v
```
Expected: FAIL — module not found

**Step 3: Write minimal implementation**

```python
# src/services/mod_mode_service.py
"""Business logic for Moderator Mode activation and state."""

from typing import Optional
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
        special_user_id: Optional[str] = None,
    ) -> dict:
        """Activate mod mode for a group.
        
        Args:
            group_id: LINE group/room ID
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

    async def get_mod_mode_info(self, group_id: str) -> Optional[dict]:
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
```

**Step 4: Run test to verify pass**

```bash
pytest tests/services/test_mod_mode_service.py -v
```
Expected: PASS

**Step 5: Commit**

```bash
git add src/services/mod_mode_service.py tests/services/test_mod_mode_service.py
git commit -m "feat(mod-mode): add ModModeService business logic layer"
```