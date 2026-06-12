### Task 3: Create BanListService

**Objective:** Service for ban list operations with auto-kick logic.

**Files:**
- Create: `src/services/ban_list_service.py`
- Test: `tests/services/test_ban_list_service.py`

**Step 1: Write failing test**

```python
# tests/services/test_ban_list_service.py
import pytest
from unittest.mock import AsyncMock
from src.services.ban_list_service import BanListService

@pytest.fixture
def mock_repo():
    return AsyncMock()

@pytest.fixture
def service(mock_repo):
    return BanListService(mock_repo)

@pytest.mark.asyncio
async def test_ban_user(service, mock_repo):
    mock_repo.ban_user.return_value = {"userId": "U999", "reason": "spam"}
    result = await service.ban_user("C123", "U999", "U456", "spam")
    assert result["userId"] == "U999"
    mock_repo.ban_user.assert_called_once()

@pytest.mark.asyncio
async def test_is_banned(service, mock_repo):
    mock_repo.is_user_banned.return_value = True
    result = await service.is_banned("C123", "U999")
    assert result is True

@pytest.mark.asyncio
async def test_unban_user(service, mock_repo):
    mock_repo.unban_user.return_value = True
    result = await service.unban_user("C123", "U999")
    assert result is True

@pytest.mark.asyncio
async def test_get_ban_list(service, mock_repo):
    mock_repo.get_ban_list.return_value = [{"userId": "U1"}, {"userId": "U2"}]
    result = await service.get_ban_list("C123")
    assert len(result) == 2
```

**Step 2: Run test to verify failure**

```bash
pytest tests/services/test_ban_list_service.py -v
```

**Step 3: Write implementation**

```python
# src/services/ban_list_service.py
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
```

**Step 4: Run test to verify pass**

```bash
pytest tests/services/test_ban_list_service.py -v
```

**Step 5: Commit**

```bash
git add src/services/ban_list_service.py tests/services/test_ban_list_service.py
git commit -m "feat(mod-mode): add BanListService"
```