"""Group membership tracking for the bot - persists which groups/rooms the bot is in."""

import json
import logging
from typing import Any

from src.services.persistent_storage import get_storage_subdir

logger = logging.getLogger(__name__)


class GroupMembershipService:
    """Track which groups/rooms the bot is a member of."""

    def __init__(self):
        self._storage_dir = get_storage_subdir("group_membership")
        self._file_path = self._storage_dir / "membership.json"
        self._membership: dict[str, dict[str, Any]] = {}
        self._load()

    def _load(self):
        """Load membership from persistent storage."""
        if self._file_path.exists():
            try:
                content = self._file_path.read_text(encoding="utf-8")
                self._membership = json.loads(content)
                logger.info(f"📋 Loaded group membership: {len(self._membership)} chats")
            except Exception as e:
                logger.warning(f"⚠️ Failed to load group membership: {e}")
                self._membership = {}
        else:
            self._membership = {}

    def _save(self):
        """Save membership to persistent storage."""
        try:
            self._file_path.write_text(
                json.dumps(self._membership, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception as e:
            logger.error(f"❌ Failed to save group membership: {e}")

    def add_group(self, chat_id: str, chat_type: str, title: str | None = None):
        """Record that bot joined a group/room."""
        if chat_id not in self._membership:
            self._membership[chat_id] = {
                "type": chat_type,  # "group" or "room"
                "title": title or "Unknown",
                "joined_at": None,  # Could add timestamp
            }
            self._save()
            logger.info(f"➕ Added {chat_type} to membership: {chat_id}")

    def remove_group(self, chat_id: str) -> bool:
        """Record that bot left a group/room."""
        if chat_id in self._membership:
            removed = self._membership.pop(chat_id)
            self._save()
            logger.info(f"➖ Removed from membership: {chat_id} ({removed.get('type')})")
            return True
        return False

    def update_title(self, chat_id: str, title: str):
        """Update group/room title if known."""
        if chat_id in self._membership:
            self._membership[chat_id]["title"] = title
            self._save()

    def get_all_groups(self) -> dict[str, dict[str, Any]]:
        """Get all groups/rooms the bot is a member of."""
        return self._membership.copy()

    def get_groups_list(self) -> list[dict[str, Any]]:
        """Get formatted list of groups for admin display."""
        groups = []
        for chat_id, info in self._membership.items():
            groups.append(
                {
                    "chat_id": chat_id,
                    "type": info.get("type", "unknown"),
                    "title": info.get("title", "Unknown"),
                }
            )
        # Sort: groups first, then rooms, then by title
        groups.sort(key=lambda x: (x["type"] != "group", x["title"].lower()))
        return groups

    def is_member(self, chat_id: str) -> bool:
        """Check if bot is tracked as member of a chat."""
        return chat_id in self._membership

    def get_count(self) -> tuple[int, int]:
        """Get count of groups and rooms."""
        group_count = sum(1 for v in self._membership.values() if v.get("type") == "group")
        room_count = sum(1 for v in self._membership.values() if v.get("type") == "room")
        return group_count, room_count


# Singleton instance
group_membership_service = GroupMembershipService()
