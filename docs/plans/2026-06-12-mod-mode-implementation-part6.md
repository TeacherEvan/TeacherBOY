### Task 6: Create ModAuditLog (HF Hub Audit Trail)

**Objective:** Append-only audit logging to HF Hub for compliance.

**Files:**
- Create: `src/services/mod_audit_log.py`
- Test: `tests/services/test_mod_audit_log.py`

**Step 1: Write failing test**

```python
# tests/services/test_mod_audit_log.py
import pytest
from unittest.mock import AsyncMock, patch
from src.services.mod_audit_log import ModAuditLog

@pytest.fixture
def mock_hf():
    with patch("src.services.mod_audit_log.HfApi") as mock:
        yield mock

@pytest.fixture
def audit_log(mock_hf):
    return ModAuditLog(token="test_token", repo_id="test/repo")

@pytest.mark.asyncio
async def test_log_kick(audit_log, mock_hf):
    await audit_log.log_kick("C123", "U999", "U456", "spam")
    # Verify file was written

@pytest.mark.asyncio
async def test_log_warn(audit_log, mock_hf):
    await audit_log.log_warn("C123", "U999", "U456", "inappropriate", 1)

@pytest.mark.asyncio
async def test_log_ban(audit_log, mock_hf):
    await audit_log.log_ban("C123", "U999", "U456", "spam")

@pytest.mark.asyncio
async def test_log_mode_change(audit_log, mock_hf):
    await audit_log.log_mode_change("C123", "U456", "all", True)
```

**Step 2: Run test to verify failure**

```bash
pytest tests/services/test_mod_audit_log.py -v
```

**Step 3: Write implementation**

```python
# src/services/mod_audit_log.py
"""HF Hub audit logging for Moderator Mode actions."""

import json
import logging
import time
from datetime import datetime
from typing import Any, Optional

from huggingface_hub import HfApi, CommitScheduler

logger = logging.getLogger(__name__)


class ModAuditLog:
    """Append-only audit log to HF Hub dataset."""

    def __init__(self, token: str, repo_id: str, local_path: str = "./data/mod_audit"):
        self._api = HfApi(token=token)
        self._repo_id = repo_id
        self._local_path = local_path
        self._scheduler: Optional[CommitScheduler] = None
        self._buffer: list[dict] = []
        self._init_scheduler()

    def _init_scheduler(self):
        """Initialize CommitScheduler for auto-push."""
        try:
            import os
            os.makedirs(self._local_path, exist_ok=True)
            self._scheduler = CommitScheduler(
                repo_id=self._repo_id,
                repo_type="dataset",
                path_pattern="mod_audit_*.jsonl",
                every=60,  # Push every 60 seconds
                token=self._api.token,
            )
            logger.info(f"📜 ModAuditLog initialized: {self._repo_id}")
        except Exception as e:
            logger.warning(f"⚠️ ModAuditLog scheduler init failed: {e}")

    def _write_local(self, entry: dict):
        """Write entry to local JSONL file."""
        import os
        os.makedirs(self._local_path, exist_ok=True)
        filename = f"mod_audit_{datetime.now().strftime('%Y-%m-%d')}.jsonl"
        filepath = os.path.join(self._local_path, filename)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    async def log_action(
        self,
        action: str,
        group_id: str,
        target_user_id: str,
        actor_user_id: str,
        details: Optional[dict] = None,
    ):
        """Log a moderation action."""
        entry = {
            "timestamp": int(time.time() * 1000),
            "action": action,  # "kick", "warn", "ban", "unban", "mode_activate", "mode_deactivate", "mode_change"
            "groupId": group_id,
            "targetUserId": target_user_id,
            "actorUserId": actor_user_id,
            "details": details or {},
        }
        self._write_local(entry)
        logger.info(f"📜 Audit: {action} group={group_id} target={target_user_id} by={actor_user_id}")

    async def log_kick(
        self,
        group_id: str,
        target_user_id: str,
        actor_user_id: str,
        reason: Optional[str] = None,
    ):
        await self.log_action("kick", group_id, target_user_id, actor_user_id, {"reason": reason})

    async def log_warn(
        self,
        group_id: str,
        target_user_id: str,
        actor_user_id: str,
        reason: str,
        warning_count: int,
    ):
        await self.log_action("warn", group_id, target_user_id, actor_user_id, {
            "reason": reason,
            "warningCount": warning_count,
        })

    async def log_ban(
        self,
        group_id: str,
        target_user_id: str,
        actor_user_id: str,
        reason: Optional[str] = None,
    ):
        await self.log_action("ban", group_id, target_user_id, actor_user_id, {"reason": reason})

    async def log_unban(
        self,
        group_id: str,
        target_user_id: str,
        actor_user_id: str,
    ):
        await self.log_action("unban", group_id, target_user_id, actor_user_id, {})

    async def log_mode_change(
        self,
        group_id: str,
        actor_user_id: str,
        mode: str,
        is_active: bool,
        special_user_id: Optional[str] = None,
    ):
        await self.log_action("mode_change", group_id, actor_user_id, actor_user_id, {
            "mode": mode,
            "isActive": is_active,
            "specialUserId": special_user_id,
        })

    def close(self):
        """Flush and close."""
        if self._scheduler:
            self._scheduler.__exit__(None, None, None)