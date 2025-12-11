"""Message deduplication service to prevent repeated translation of identical messages."""

import logging
import hashlib
from datetime import datetime, timedelta
from collections import defaultdict
from typing import Dict

logger = logging.getLogger(__name__)


class MessageDeduplicator:
    """
    Deduplicates messages within a time window to prevent redundant translations.

    This is especially important to prevent:
    1. Accidental double-sends by users
    2. Bot message loops
    3. Unnecessary API costs from duplicate requests
    """

    def __init__(self, ttl_seconds: int = 60):
        """
        Initialize message deduplicator.

        Args:
            ttl_seconds: Time-to-live for seen messages in seconds
        """
        self.ttl = timedelta(seconds=ttl_seconds)
        # Structure: {chat_id: {msg_hash: timestamp}}
        self.seen: Dict[str, Dict[str, datetime]] = defaultdict(dict)

    def is_duplicate(self, chat_id: str, text: str) -> bool:
        """
        Check if a message is a duplicate within the TTL window.

        Uses SHA-256 hash for efficient message comparison while protecting
        user privacy (we don't store actual message content). SHA-256 provides
        better collision resistance than MD5.

        Args:
            chat_id: Unique identifier for the chat/group
            text: Message text to check

        Returns:
            True if message is a duplicate, False if it's new
        """
        # Create a hash of the message (16 chars is sufficient for collision resistance)
        msg_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        now = datetime.now()

        # Clean up expired entries for this chat
        self.seen[chat_id] = {
            h: timestamp
            for h, timestamp in self.seen[chat_id].items()
            if now - timestamp < self.ttl
        }

        # Check if we've seen this message hash recently
        if msg_hash in self.seen[chat_id]:
            time_since = now - self.seen[chat_id][msg_hash]
            logger.info(
                f"🔁 Duplicate message detected for chat {chat_id} "
                f"(seen {time_since.seconds}s ago, hash: {msg_hash})"
            )
            return True

        # Record this message
        self.seen[chat_id][msg_hash] = now
        logger.debug(f"✅ New message recorded for chat {chat_id} (hash: {msg_hash})")
        return False

    def clear_chat_history(self, chat_id: str):
        """
        Clear deduplication history for a specific chat.

        Useful when ending a session or for testing.

        Args:
            chat_id: Unique identifier for the chat/group
        """
        if chat_id in self.seen:
            del self.seen[chat_id]
            logger.info(f"🗑️ Cleared deduplication history for chat {chat_id}")

    def cleanup_all(self):
        """
        Clean up expired messages across all chats.

        Should be called periodically to prevent memory growth.
        """
        now = datetime.now()
        total_before = sum(len(msgs) for msgs in self.seen.values())

        for chat_id in list(self.seen.keys()):
            self.seen[chat_id] = {
                h: timestamp
                for h, timestamp in self.seen[chat_id].items()
                if now - timestamp < self.ttl
            }
            # Remove empty chat entries
            if not self.seen[chat_id]:
                del self.seen[chat_id]

        total_after = sum(len(msgs) for msgs in self.seen.values())
        if total_before != total_after:
            logger.info(
                f"🧹 Cleaned up deduplication cache: {total_before} → {total_after} messages"
            )


# Singleton instance with configurable TTL from settings
# This is initialized here, but can be reconfigured in main.py if needed
from src.config import settings

message_dedup = MessageDeduplicator(ttl_seconds=settings.message_dedup_ttl_seconds)
