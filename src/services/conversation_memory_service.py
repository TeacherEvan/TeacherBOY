"""
Conversation Memory Service - Session-based context persistence for Zeus LLM.

This service provides conversation history storage and retrieval to enable
contextual multi-turn conversations. It supports two storage backends:

1. Hugging Face Hub (persistent): Stores conversations in a private HF dataset
2. In-memory (ephemeral): Falls back when HF token is not configured

Security features:
- Chat IDs are hashed before storage (SHA-256 prefix)
- Messages are encrypted in transit to HF Hub (HTTPS)
- Private dataset by default
- Automatic cleanup of old conversations
"""

import hashlib
import json
import logging
from collections import OrderedDict
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.config import settings
from src.services.conversation_summary_service import ConversationSummarizer
from src.services.hf_storage_mixin import HFStorageMixin

logger = logging.getLogger(__name__)

# Configuration constants
MAX_MESSAGES_PER_SESSION = 20  # Maximum messages to keep in context
MAX_CONTEXT_TOKENS = 4000  # Approximate token limit for context window
SESSION_TTL_HOURS = 24  # Session expiration time
CLEANUP_INTERVAL_MINUTES = 30  # How often to run cleanup
HF_SYNC_INTERVAL_MINUTES = 5  # How often to sync to HF Hub


class FlushMode(StrEnum):
    """Memory flush modes."""

    TIME_BASED = "time_based"           # Delete older than N days
    SIZE_BASED = "size_based"           # Cap total messages / per-chat
    MANUAL_SELECTION = "manual"         # Admin picks specific chats
    FULL_PURGE = "full"                 # Everything (with confirmation)


class FlushParams:
    """Parameters for memory flush operations."""

    def __init__(
        self,
        older_than_days: int | None = None,
        max_total_messages: int | None = None,
        max_messages_per_chat: int | None = None,
        chat_ids: list[str] | None = None,
        dry_run: bool = False,
        include_documents: bool = False,
        include_images: bool = False,
    ):
        self.older_than_days = older_than_days
        self.max_total_messages = max_total_messages
        self.max_messages_per_chat = max_messages_per_chat
        self.chat_ids = chat_ids
        self.dry_run = dry_run
        self.include_documents = include_documents
        self.include_images = include_images


class FlushResult:
    """Result of a memory flush operation."""

    def __init__(
        self,
        deleted_chats: int = 0,
        deleted_messages: int = 0,
        freed_bytes_mb: float = 0.0,
        dry_run: bool = False,
        mode: FlushMode | None = None,
    ):
        self.deleted_chats = deleted_chats
        self.deleted_messages = deleted_messages
        self.freed_bytes_mb = freed_bytes_mb
        self.dry_run = dry_run
        self.mode = mode

    def __repr__(self) -> str:
        action = "Dry run" if self.dry_run else "Executed"
        return (f"FlushResult({action}: deleted_chats={self.deleted_chats}, "
                f"deleted_messages={self.deleted_messages}, freed_mb={self.freed_bytes_mb:.2f})")


class ConversationMemoryService(HFStorageMixin):
    """
    Service for managing conversation memory with optional HF Hub persistence.

    The service maintains an in-memory cache of recent conversations and
    optionally syncs to Hugging Face Hub for persistence across restarts.
    """

    def __init__(
        self,
        hf_token: str | None = None,
        hf_repo_id: str | None = None,
        max_messages: int = MAX_MESSAGES_PER_SESSION,
        session_ttl_hours: int = SESSION_TTL_HOURS,
        storage_path: str = "./data/conversations",
    ):
        """
        Initialize conversation memory service.

        Args:
            hf_token: Hugging Face API token for persistent storage
            hf_repo_id: HF dataset repo ID (e.g., "username/zeus-memory")
            max_messages: Maximum messages to retain per session
            session_ttl_hours: Hours before session expires
            storage_path: Local directory for conversation memory persistence
        """
        # Set up HF storage mixin attributes before calling super().__init__ equivalent
        self.hf_token = hf_token
        self.hf_repo_id = hf_repo_id
        self.storage_path = Path(storage_path)
        self.hf_sync_interval = HF_SYNC_INTERVAL_MINUTES
        self.hf_squash_history = True
        self.hf_path_in_repo = "conversations"
        self._hf_enabled = bool(hf_token and hf_repo_id)
        super().__init__()  # Call mixin __init__ (which is just object.__init__)

        self.max_messages = max_messages
        self.session_ttl = timedelta(hours=session_ttl_hours)

        # In-memory conversation store
        # Format: {hashed_chat_id: {"messages": [...], "summary": str, "last_activity": datetime, "metadata": {...}}}
        self._conversations: OrderedDict[str, dict[str, Any]] = OrderedDict()

        # Initialize conversation summarizer (if enabled)
        self._summarizer: ConversationSummarizer | None = None
        if settings.enable_conversation_summarization:
            self._summarizer = ConversationSummarizer(
                max_tokens_before_summary=settings.conversation_summary_interval * 200,  # Estimate 200 tokens/msg
                messages_to_keep_full=settings.conversation_messages_to_keep_full,
            )
            logger.info(f"📝 Conversation summarization enabled (keep_recent={settings.conversation_messages_to_keep_full})")

        # Last cleanup timestamp
        self._last_cleanup = datetime.now(UTC)

        # Initialize HF storage if enabled (calls _setup_hf_storage from mixin)
        if self._hf_enabled:
            self._setup_hf_storage()
        else:
            logger.info("💭 Conversation memory initialized (in-memory only)")

    def _hash_chat_id(self, chat_id: str) -> str:
        """
        Hash chat ID for privacy-preserving storage.

        Args:
            chat_id: Original chat identifier

        Returns:
            SHA-256 hash prefix (16 chars) of the chat ID
        """
        return hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]

    def _estimate_tokens(self, text: str) -> int:
        """
        Estimate token count for text (rough approximation).

        Uses ~4 characters per token as a heuristic.

        Args:
            text: Text to estimate tokens for

        Returns:
            Estimated token count
        """
        return len(text) // 4 + 1

    def _trim_to_token_limit(
        self, messages: list[dict[str, str]], max_tokens: int = MAX_CONTEXT_TOKENS
    ) -> list[dict[str, str]]:
        """
        Trim messages to fit within token limit, keeping most recent.

        Args:
            messages: List of message dicts
            max_tokens: Maximum tokens allowed

        Returns:
            Trimmed list of messages
        """
        if not messages:
            return []

        total_tokens = 0
        trimmed: list[dict[str, str]] = []

        # Process in reverse (most recent first)
        for msg in reversed(messages):
            msg_tokens = self._estimate_tokens(msg.get("content", ""))
            if total_tokens + msg_tokens > max_tokens:
                break
            trimmed.insert(0, msg)
            total_tokens += msg_tokens

        return trimmed

    async def _maybe_cleanup(self) -> None:
        """Run cleanup if interval has passed."""
        now = datetime.now(UTC)
        if now - self._last_cleanup > timedelta(minutes=CLEANUP_INTERVAL_MINUTES):
            await self._cleanup_expired()
            self._last_cleanup = now

    async def _cleanup_expired(self) -> None:
        """Remove conversations older than session TTL."""
        now = datetime.now(UTC)
        cutoff = now - self.session_ttl

        expired = []
        for hashed_id, conv in self._conversations.items():
            last_activity = conv.get("last_activity")
            if isinstance(last_activity, datetime) and last_activity < cutoff:
                expired.append(hashed_id)

        for hashed_id in expired:
            del self._conversations[hashed_id]

        if self._hf_enabled:
            for hashed_id in expired:
                if self._hf_sync_folder:
                    file_path = self._hf_sync_folder / f"{hashed_id}.json"
                    if file_path.exists():
                        file_path.unlink()

        if expired:
            logger.info(f"💭 Cleaned up {len(expired)} expired conversation(s)")

    async def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        user_id: str | None = None,
    ) -> None:
        """
        Add a message to the conversation history.

        Args:
            chat_id: Chat identifier (group/room/user ID)
            role: Message role ("user" or "assistant")
            content: Message content
            user_id: Optional user ID for the message sender
        """
        # Run cleanup periodically
        await self._maybe_cleanup()

        hashed_id = self._hash_chat_id(chat_id)
        now = datetime.now(UTC)

        # Initialize conversation if new
        if hashed_id not in self._conversations:
            self._conversations[hashed_id] = {
                "messages": [],
                "last_activity": now,
                "metadata": {
                    "created_at": now.isoformat(),
                    "user_ids": set(),
                },
            }

        conv = self._conversations[hashed_id]

        # Add message
        message = {
            "role": role,
            "content": content,
            "timestamp": now.isoformat(),
        }
        if user_id:
            message["user_id"] = user_id
            conv["metadata"]["user_ids"].add(user_id)

        conv["messages"].append(message)
        conv["last_activity"] = now

        # Trim if exceeding max messages
        if len(conv["messages"]) > self.max_messages:
            conv["messages"] = conv["messages"][-self.max_messages:]

        # Handle summarization
        if self._summarizer and len(conv["messages"]) >= self._summarizer.threshold // 200:
            messages = conv["messages"]
            current_summary = conv.get("summary")
            new_summary, recent_messages = await self._summarizer.maybe_summarize(messages, current_summary)
            if new_summary:
                conv["summary"] = new_summary
                conv["messages"] = recent_messages

        # Save to local storage for HF sync
        if self._hf_enabled:
            await self._save_to_local_storage(hashed_id, conv)

        # Move to end (most recent)
        self._conversations.move_to_end(hashed_id)

    async def _save_to_local_storage(self, hashed_id: str, conv: dict[str, Any]) -> None:
        """Save conversation to local storage for HF Hub sync."""
        if not self._hf_sync_folder:
            return

        try:
            file_path = self._hf_sync_folder / f"{hashed_id}.json"

            # Prepare serializable data
            last_activity = conv.get("last_activity")
            data = {
                "messages": conv.get("messages", []),
                "last_activity": last_activity.isoformat() if last_activity else None,
                "metadata": {
                    "created_at": conv.get("metadata", {}).get("created_at"),
                    "user_ids": list(conv.get("metadata", {}).get("user_ids", set())),
                },
            }

            # Write atomically
            temp_path = file_path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.rename(file_path)

        except Exception as e:
            logger.error(f"❌ Failed to save conversation {hashed_id[:8]}: {e}")

    def load_conversations_from_hub(self, max_files: int = 100) -> int:
        """
        Load existing conversations from HF Hub on startup.

        Args:
            max_files: Maximum number of conversation files to load

        Returns:
            Number of conversations loaded
        """
        def post_process(hashed_id: str, data: dict[str, Any]) -> dict[str, Any]:
            # Restore datetime objects
            last_activity = data.get("last_activity")
            if last_activity:
                last_activity = datetime.fromisoformat(last_activity)
            else:
                last_activity = datetime.now(UTC)

            self._conversations[hashed_id] = {
                "messages": data.get("messages", []),
                "last_activity": last_activity,
                "metadata": {
                    "created_at": data.get("metadata", {}).get("created_at"),
                    "user_ids": set(data.get("metadata", {}).get("user_ids", [])),
                },
            }
            return data

        return super().load_from_hub(
            file_extension=".json",
            max_files=max_files,
            post_process=post_process,
        )

    def stop(self) -> None:
        """Stop the commit scheduler (call during shutdown)."""
        self.stop_hf_storage()

    def get_stats(self) -> dict[str, Any]:
        """
        Get service statistics.

        Returns:
            Dict with memory service stats
        """
        total_messages = sum(len(conv.get("messages", [])) for conv in self._conversations.values())
        hf_stats = self.get_hf_stats()

        return {
            "active_conversations": len(self._conversations),
            "total_messages": total_messages,
            "max_messages_per_session": self.max_messages,
            "session_ttl_hours": self.session_ttl.total_seconds() / 3600,
            **hf_stats,
        }

    async def flush_memory(
        self,
        mode: FlushMode,
        params: FlushParams,
    ) -> FlushResult:
        """
        Flush conversation memory based on mode and parameters.

        Args:
            mode: Flush mode (TIME_BASED, SIZE_BASED, MANUAL_SELECTION, FULL_PURGE)
            params: Flush parameters

        Returns:
            FlushResult with deletion statistics
        """
        result = FlushResult(mode=mode, dry_run=params.dry_run)

        if mode == FlushMode.TIME_BASED:
            return await self._flush_time_based(params, result)
        elif mode == FlushMode.SIZE_BASED:
            return await self._flush_size_based(params, result)
        elif mode == FlushMode.MANUAL_SELECTION:
            return await self._flush_manual_selection(params, result)
        elif mode == FlushMode.FULL_PURGE:
            return await self._flush_full_purge(params, result)
        else:
            raise ValueError(f"Unknown flush mode: {mode}")

    async def _flush_time_based(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Flush conversations older than specified days."""
        if params.older_than_days is None:
            params.older_than_days = 30

        cutoff = datetime.now(UTC) - timedelta(days=params.older_than_days)
        to_delete = []

        for hashed_id, conv in self._conversations.items():
            last_activity = conv.get("last_activity")
            if isinstance(last_activity, datetime):
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=UTC)
                if last_activity < cutoff:
                    to_delete.append(hashed_id)

        result.deleted_chats = len(to_delete)
        for hashed_id in to_delete:
            conv = self._conversations[hashed_id]
            result.deleted_messages += len(conv.get("messages", []))

        if not params.dry_run:
            for hashed_id in to_delete:
                del self._conversations[hashed_id]
                # Also delete from local storage if HF enabled
                if self._hf_enabled and self._hf_sync_folder:
                    file_path = self._hf_sync_folder / f"{hashed_id}.json"
                    if file_path.exists():
                        file_path.unlink()

        return result

    async def _flush_size_based(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Flush to cap total messages or per-chat messages."""
        total_messages = sum(len(conv.get("messages", [])) for conv in self._conversations.values())

        # If per-chat limit specified, trim each chat
        if params.max_messages_per_chat:
            for hashed_id, conv in self._conversations.items():
                messages = conv.get("messages", [])
                if len(messages) > params.max_messages_per_chat:
                    removed = len(messages) - params.max_messages_per_chat
                    result.deleted_messages += removed
                    if not params.dry_run:
                        conv["messages"] = messages[-params.max_messages_per_chat:]
                        # Update local storage
                        if self._hf_enabled:
                            await self._save_to_local_storage(hashed_id, conv)

        # If total limit specified, remove oldest chats first
        if params.max_total_messages and total_messages > params.max_total_messages:
            # Sort by last_activity (oldest first)
            sorted_chats = sorted(
                self._conversations.items(),
                key=lambda x: x[1].get("last_activity", datetime.min.replace(tzinfo=UTC))
            )
            excess = total_messages - params.max_total_messages
            for hashed_id, conv in sorted_chats:
                if excess <= 0:
                    break
                messages = conv.get("messages", [])
                if not messages:
                    continue
                to_remove = min(excess, len(messages))
                result.deleted_messages += to_remove
                excess -= to_remove
                if not params.dry_run:
                    if to_remove >= len(messages):
                        del self._conversations[hashed_id]
                        result.deleted_chats += 1
                        if self._hf_enabled and self._hf_sync_folder:
                            file_path = self._hf_sync_folder / f"{hashed_id}.json"
                            if file_path.exists():
                                file_path.unlink()
                    else:
                        conv["messages"] = messages[-len(messages) + to_remove:]
                        if self._hf_enabled:
                            await self._save_to_local_storage(hashed_id, conv)

        return result

    async def _flush_manual_selection(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Flush specific chat IDs provided by admin."""
        if not params.chat_ids:
            return result

        for chat_id in params.chat_ids:
            hashed_id = self._hash_chat_id(chat_id)
            if hashed_id in self._conversations:
                conv = self._conversations[hashed_id]
                result.deleted_chats += 1
                result.deleted_messages += len(conv.get("messages", []))
                if not params.dry_run:
                    del self._conversations[hashed_id]
                    if self._hf_enabled and self._hf_sync_folder:
                        file_path = self._hf_sync_folder / f"{hashed_id}.json"
                        if file_path.exists():
                            file_path.unlink()

        return result

    async def _flush_full_purge(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Flush all conversations (requires confirmation via params.dry_run=False)."""
        for _hashed_id, conv in self._conversations.items():
            result.deleted_chats += 1
            result.deleted_messages += len(conv.get("messages", []))

        if not params.dry_run:
            self._conversations.clear()
            if self._hf_enabled and self._hf_sync_folder:
                for file_path in self._hf_sync_folder.glob("*.json"):
                    file_path.unlink()

        return result

    async def get_context_messages(self, chat_id: str) -> list[dict[str, str]]:
        """
        Get conversation context messages for a chat.

        Args:
            chat_id: Chat identifier

        Returns:
            List of message dicts with role and content
        """
        hashed_id = self._hash_chat_id(chat_id)
        conv = self._conversations.get(hashed_id)
        if not conv:
            return []

        messages = conv.get("messages", [])
        return [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    async def clear_conversation(self, chat_id: str) -> None:
        """
        Clear conversation history for a chat.

        Args:
            chat_id: Chat identifier
        """
        hashed_id = self._hash_chat_id(chat_id)
        if hashed_id in self._conversations:
            del self._conversations[hashed_id]
            if self._hf_enabled and self._hf_sync_folder:
                file_path = self._hf_sync_folder / f"{hashed_id}.json"
                if file_path.exists():
                    file_path.unlink()

    async def get_conversation_summary(self, chat_id: str) -> dict[str, Any]:
        """
        Get summary statistics for a conversation.

        Args:
            chat_id: Chat identifier

        Returns:
            Dict with message_count, unique_users, last_activity, etc.
        """
        hashed_id = self._hash_chat_id(chat_id)
        conv = self._conversations.get(hashed_id)
        if not conv:
            return {
                "message_count": 0,
                "unique_users": 0,
                "last_activity": None,
            }

        messages = conv.get("messages", [])
        metadata = conv.get("metadata", {})
        user_ids = metadata.get("user_ids", set())
        last_activity = conv.get("last_activity")

        return {
            "message_count": len(messages),
            "unique_users": len(user_ids),
            "last_activity": last_activity.isoformat() if last_activity else None,
        }

    @property
    def local_storage_path(self) -> Path:
        """Return the local storage path for backward compatibility."""
        return self.storage_path

    @property
    def _local_storage_path(self) -> Path:
        """Return the HF sync folder for backward compatibility with tests."""
        if self._hf_sync_folder is None:
            # Create a dummy path for tests that check this attribute
            return Path(str(self.storage_path) + "/hf_sync")
        return self._hf_sync_folder


# Module-level singleton management
_conversation_memory_instance: ConversationMemoryService | None = None


def init_conversation_memory(
    hf_token: str | None = None,
    hf_repo_id: str | None = None,
    storage_path: str | None = None,
) -> ConversationMemoryService:
    """
    Initialize the singleton conversation memory service.

    Args:
        hf_token: Hugging Face API token for persistent storage
        hf_repo_id: HF dataset repo ID
        storage_path: Local directory for conversation memory persistence

    Returns:
        Initialized ConversationMemoryService instance
    """
    global _conversation_memory_instance

    from src.config import settings

    if storage_path is None:
        storage_path = settings.conversation_storage_path

    _conversation_memory_instance = ConversationMemoryService(
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
        storage_path=storage_path,
    )
    return _conversation_memory_instance


def get_conversation_memory() -> ConversationMemoryService | None:
    """
    Get the singleton conversation memory service instance.

    Returns:
        ConversationMemoryService instance or None if not initialized
    """
    return _conversation_memory_instance
