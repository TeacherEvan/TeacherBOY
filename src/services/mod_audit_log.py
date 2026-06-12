"""HF Hub audit logging for Moderator Mode actions."""

import json
import logging
import time
import os
from datetime import datetime
from typing import Any, Optional

from huggingface_hub import HfApi

logger = logging.getLogger(__name__)


class ModAuditLog:
    """Append-only audit log to HF Hub dataset."""

    def __init__(self, token: str, repo_id: str, local_path: str = "./data/mod_audit"):
        self._api = HfApi(token=token)
        self._repo_id = repo_id
        self._local_path = local_path
        self._init_local_dir()

    def _init_local_dir(self):
        """Initialize local directory for JSONL files."""
        os.makedirs(self._local_path, exist_ok=True)
        logger.info(f"📜 ModAuditLog initialized: {self._repo_id}")

    def _write_local(self, entry: dict):
        """Write entry to local JSONL file."""
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
        """Flush and close (placeholder for future CommitScheduler integration)."""
        logger.info("📜 ModAuditLog closed")