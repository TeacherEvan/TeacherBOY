### Task 4: Create WarningService

**Objective:** 3-strike warning system with read tracking for "read warning counts" feature.

**Files:**
- Create: `src/services/warning_service.py`
- Test: `tests/services/test_warning_service.py`

**Step 1: Write failing test**

```python
# tests/services/test_warning_service.py
import pytest
from unittest.mock import AsyncMock
from src.services.warning_service import WarningService

@pytest.fixture
def mock_repo():
    return AsyncMock()

@pytest.fixture
def service(mock_repo):
    return WarningService(mock_repo)

@pytest.mark.asyncio
async def test_warn_user_first_strike(service, mock_repo):
    mock_repo.add_warning.return_value = {"count": 1}
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 1
    assert result["should_ban"] is False

@pytest.mark.asyncio
async def test_warn_user_third_strike_bans(service, mock_repo):
    mock_repo.add_warning.return_value = {"count": 3}
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 3
    assert result["should_ban"] is True

@pytest.mark.asyncio
async def test_get_warning_count(service, mock_repo):
    mock_repo.get_warning_count.return_value = 2
    count = await service.get_warning_count("C123", "U999")
    assert count == 2

@pytest.mark.asyncio
async def test_mark_warning_read(service, mock_repo):
    mock_repo.mark_warning_read.return_value = {"readByUser": True}
    result = await service.mark_warning_read("C123", "U999")
    assert result["readByUser"] is True
```

**Step 2: Run test to verify failure**

```bash
pytest tests/services/test_warning_service.py -v
```

**Step 3: Write implementation**

```python
# src/services/warning_service.py
"""3-strike warning system for Moderator Mode."""

from typing: Optional
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
        reason: Optional[str] = None,
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
        return await self._repo.add_warning(group_id, user_id, "system", "reset")
```

**Step 4: Run test to verify pass**

```bash
pytest tests/services/test_warning_service.py -v
```

**Step 5: Commit**

```bash
git add src/services/warning_service.py tests/services/test_warning_service.py
git commit -m "feat(mod-mode): add WarningService with 3-strike logic"
```