# Moderator Mode — Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Build a dedicated Moderator Mode agent (Priority 4) for LINE groups with kick/warn/ban, two modes (all/special), admin Flex dashboard, Convex state + HF audit logs.

**Architecture:** Dedicated ModModeAgent intercepting messages in mod-enabled groups, with ModModeService/BanListService/WarningService/HarmfulContentDetector backing it. Convex for active state (indexed by groupId/userId), HF for audit logs.

**Tech Stack:** Python 3.11, FastAPI, LINE Bot SDK v3, Convex HTTP client, HuggingFace Hub (CommitScheduler), pytest, Ruff.

---

### Task 1: Create Convex Repository Classes for Mod Mode Tables

**Objective:** Add Convex data access layer for the three new tables (modModeState, banList, userWarnings).

**Files:**
- Create: `src/services/convex_mod_repository.py`
- Modify: `src/services/convex_client.py` (if needed for new methods)

**Step 1: Write failing test**

```python
# tests/services/test_convex_mod_repository.py
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.convex_mod_repository import ConvexModRepository

@pytest.fixture
def mock_convex_client():
    return AsyncMock()

@pytest.fixture
def repo(mock_convex_client):
    return ConvexModRepository(mock_convex_client)

@pytest.mark.asyncio
async def test_get_mod_mode_state(repo, mock_convex_client):
    mock_convex_client.get.return_value = {"groupId": "C123", "mode": "all", "activatedBy": "U456", "isActive": True}
    result = await repo.get_mod_mode_state("C123")
    assert result is not None
    assert result["mode"] == "all"
    mock_convex_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_set_mod_mode_state(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"groupId": "C123", "mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    result = await repo.set_mod_mode_state("C123", "special", "U456", "U789")
    assert result["mode"] == "special"
    assert result["specialUserId"] == "U789"
    mock_convex_client.post.assert_called_once()

@pytest.mark.asyncio
async def test_ban_user(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"groupId": "C123", "userId": "U999", "bannedBy": "U456", "reason": "spam"}
    result = await repo.ban_user("C123", "U999", "U456", "spam")
    assert result["userId"] == "U999"
    mock_convex_client.post.assert_called_once()

@pytest.mark.asyncio
async def test_is_user_banned(repo, mock_convex_client):
    mock_convex_client.get.return_value = {"groupId": "C123", "userId": "U999"}
    result = await repo.is_user_banned("C123", "U999")
    assert result is True
    mock_convex_client.get.assert_called_once()

@pytest.mark.asyncio
async def test_unban_user(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"success": True}
    result = await repo.unban_user("C123", "U999")
    assert result is True

@pytest.mark.asyncio
async def test_add_warning(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"groupId": "C123", "userId": "U999", "count": 1}
    result = await repo.add_warning("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 1

@pytest.mark.asyncio
async def test_get_warning_count(repo, mock_convex_client):
    mock_convex_client.get.return_value = {"count": 2}
    result = await repo.get_warning_count("C123", "U999")
    assert result == 2

@pytest.mark.asyncio
async def test_mark_warning_read(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"readByUser": True}
    result = await repo.mark_warning_read("C123", "U999")
    assert result["readByUser"] is True
```

**Step 2: Run test to verify failure**

```bash
pytest tests/services/test_convex_mod_repository.py -v
```
Expected: FAIL — module not found

**Step 3: Write minimal implementation**

```python
# src/services/convex_mod_repository.py
"""Convex repository for Moderator Mode tables."""

from typing import Any, Optional
from src.services.convex_client import ConvexClient


class ConvexModRepository:
    """Data access for modModeState, banList, userWarnings tables."""

    def __init__(self, convex_client: ConvexClient):
        self._client = convex_client

    # ===== modModeState =====

    async def get_mod_mode_state(self, group_id: str) -> Optional[dict[str, Any]]:
        """Get mod mode state for a group."""
        response = await self._client.get(
            "/modModeState/getByGroup",
            {"groupId": group_id}
        )
        return response.get("data") if response else None

    async def set_mod_mode_state(
        self,
        group_id: str,
        mode: str,
        activated_by: str,
        special_user_id: Optional[str] = None,
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
        return response.get("data", payload)

    async def deactivate_mod_mode(self, group_id: str) -> bool:
        """Deactivate mod mode for a group."""
        response = await self._client.post("/modModeState/deactivate", {"groupId": group_id})
        return response.get("success", False)

    # ===== banList =====

    async def ban_user(
        self,
        group_id: str,
        user_id: str,
        banned_by: str,
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Add user to ban list."""
        payload = {
            "groupId": group_id,
            "userId": user_id,
            "bannedBy": banned_by,
            "bannedAt": int(__import__("time").time() * 1000),
        }
        if reason:
            payload["reason"] = reason
        response = await self._client.post("/banList/upsert", payload)
        return response.get("data", payload)

    async def is_user_banned(self, group_id: str, user_id: str) -> bool:
        """Check if user is banned in group."""
        response = await self._client.get(
            "/banList/getByGroupUser",
            {"groupId": group_id, "userId": user_id}
        )
        return response.get("data") is not None

    async def unban_user(self, group_id: str, user_id: str) -> bool:
        """Remove user from ban list."""
        response = await self._client.post("/banList/remove", {"groupId": group_id, "userId": user_id})
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
        reason: Optional[str] = None,
    ) -> dict[str, Any]:
        """Increment warning count for user (3-strike)."""
        # Get current count
        current = await self.get_warning_count(group_id, user_id)
        new_count = current + 1
        payload = {
            "groupId": group_id,
            "userId": user_id,
            "count": new_count,
            "lastWarningAt": int(__import__("time").time() * 1000),
            "lastWarningBy": warned_by,
            "lastWarningReason": reason or "",
            "readByUser": False,
        }
        response = await self._client.post("/userWarnings/upsert", payload)
        return response.get("data", payload)

    async def get_warning_count(self, group_id: str, user_id: str) -> int:
        """Get current warning count for user."""
        response = await self._client.get(
            "/userWarnings/getByGroupUser",
            {"groupId": group_id, "userId": user_id}
        )
        data = response.get("data")
        return data.get("count", 0) if data else 0

    async def mark_warning_read(self, group_id: str, user_id: str) -> dict[str, Any]:
        """Mark user's warning as read (for 'read warning counts')."""
        payload = {
            "groupId": group_id,
            "userId": user_id,
            "readByUser": True,
            "readAt": int(__import__("time").time() * 1000),
        }
        response = await self._client.post("/userWarnings/upsert", payload)
        return response.get("data", payload)

    async def get_warnings(self, group_id: str) -> list[dict[str, Any]]:
        """Get all warnings in a group."""
        response = await self._client.get("/userWarnings/getByGroup", {"groupId": group_id})
        return response.get("data", [])
```

**Step 4: Run test to verify pass**

```bash
pytest tests/services/test_convex_mod_repository.py -v
```
Expected: PASS (after Convex HTTP endpoints exist)

**Step 5: Commit**

```bash
git add src/services/convex_mod_repository.py tests/services/test_convex_mod_repository.py
git commit -m "feat(mod-mode): add Convex repository for mod mode tables"
```