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

import asyncio
import hashlib
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict

from src.config import settings
from src.services.conversation_summary_service import ConversationSummarizer

logger = logging.getLogger(__name__)

# Configuration constants
MAX_MESSAGES_PER_SESSION = 20  # Maximum messages to keep in context
MAX_CONTEXT_TOKENS = 4000  # Approximate token limit for context window
SESSION_TTL_HOURS = 24  # Session expiration time
CLEANUP_INTERVAL_MINUTES = 30  # How often to run cleanup
HF_SYNC_INTERVAL_MINUTES = 5  # How often to sync to HF Hub


class ConversationMemoryService:
    """
    Service for managing conversation memory with optional HF Hub persistence.
    
    The service maintains an in-memory cache of recent conversations and
    optionally syncs to Hugging Face Hub for persistence across restarts.
    """

    def __init__(
        self,
        hf_token: Optional[str] = None,
        hf_repo_id: Optional[str] = None,
        max_messages: int = MAX_MESSAGES_PER_SESSION,
        session_ttl_hours: int = SESSION_TTL_HOURS,
    ):
        """
        Initialize conversation memory service.

        Args:
            hf_token: Hugging Face API token for persistent storage
            hf_repo_id: HF dataset repo ID (e.g., "username/zeus-memory")
            max_messages: Maximum messages to retain per session
            session_ttl_hours: Hours before session expires
        """
        self.hf_token = hf_token
        self.hf_repo_id = hf_repo_id
        self.max_messages = max_messages
        self.session_ttl = timedelta(hours=session_ttl_hours)
        
        # In-memory conversation store
        # Format: {hashed_chat_id: {"messages": [...], "summary": str, "last_activity": datetime, "metadata": {...}}}
        self._conversations: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        
        # Initialize conversation summarizer (if enabled)
        self._summarizer: Optional[ConversationSummarizer] = None
        if settings.enable_conversation_summarization:
            self._summarizer = ConversationSummarizer(
                max_tokens_before_summary=settings.conversation_summary_interval * 200,  # Estimate 200 tokens/msg
                messages_to_keep_full=settings.conversation_messages_to_keep_full,
            )
            logger.info(f"📝 Conversation summarization enabled (keep_recent={settings.conversation_messages_to_keep_full})")
        
        # Track if HF Hub is configured
        self._hf_enabled = bool(hf_token and hf_repo_id)
        self._hf_api: Optional[Any] = None
        self._commit_scheduler: Optional[Any] = None
        self._local_storage_path: Optional[Path] = None
        
        # Last cleanup timestamp
        self._last_cleanup = datetime.now(timezone.utc)
        
        if self._hf_enabled:
            self._setup_hf_storage()
        else:
            logger.info("💭 Conversation memory initialized (in-memory only)")

    def _setup_hf_storage(self):
        """Initialize Hugging Face Hub storage backend."""
        if not self.hf_token or not self.hf_repo_id:
            self._hf_enabled = False
            return

        try:
            import importlib

            hf = importlib.import_module("huggingface_hub")
            HfApi = getattr(hf, "HfApi")
            CommitScheduler = getattr(hf, "CommitScheduler")

            hf_api = HfApi(token=self.hf_token)
            self._hf_api = hf_api
            
            # Create local storage directory for CommitScheduler
            self._local_storage_path = Path("./data/conversations")
            self._local_storage_path.mkdir(parents=True, exist_ok=True)
            
            # Ensure the dataset repo exists
            try:
                hf_api.create_repo(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    private=True,
                    exist_ok=True,
                )
                logger.info(f"💭 HF Hub dataset ready: {self.hf_repo_id}")
            except Exception as e:
                logger.warning(f"⚠️ Could not create/verify HF repo: {e}")
                self._hf_enabled = False
                return
            
            # Set up scheduled commits (every 5 minutes)
            self._commit_scheduler = CommitScheduler(
                repo_id=self.hf_repo_id,
                repo_type="dataset",
                folder_path=str(self._local_storage_path),
                every=HF_SYNC_INTERVAL_MINUTES,
                token=self.hf_token,
                private=True,
                squash_history=True,  # Keep repo size small
            )
            
            # Load existing conversations from HF Hub
            asyncio.create_task(self._load_from_hub())
            
            logger.info(f"💭 Conversation memory initialized with HF Hub persistence")
            
        except ModuleNotFoundError:
            logger.warning("⚠️ huggingface_hub not installed, using in-memory storage only")
            self._hf_enabled = False
        except Exception as e:
            logger.error(f"❌ Failed to initialize HF storage: {e}")
            self._hf_enabled = False

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
        self, messages: List[Dict[str, str]], max_tokens: int = MAX_CONTEXT_TOKENS
    ) -> List[Dict[str, str]]:
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
        trimmed = []
        
        # Process in reverse (most recent first)
        for msg in reversed(messages):
            msg_tokens = self._estimate_tokens(msg.get("content", ""))
            if total_tokens + msg_tokens > max_tokens:
                break
            trimmed.insert(0, msg)
            total_tokens += msg_tokens
        
        return trimmed

    async def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
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
        now = datetime.now(timezone.utc)
        
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
        
        # Trim to max messages
        if len(conv["messages"]) > self.max_messages:
            conv["messages"] = conv["messages"][-self.max_messages:]
        
        # Move to end of OrderedDict (LRU behavior)
        self._conversations.move_to_end(hashed_id)
        
        # Save to local storage for HF sync
        if self._hf_enabled:
            await self._save_to_local_storage(hashed_id, conv)
        
        logger.debug(f"💭 Added {role} message to {hashed_id[:8]}... ({len(conv['messages'])} total)")

    async def get_context_messages(
        self,
        chat_id: str,
        max_tokens: int = MAX_CONTEXT_TOKENS,
        include_system: bool = False,
    ) -> List[Dict[str, str]]:
        """
        Get conversation context for LLM prompt.
        
        Returns messages in OpenAI-compatible format, trimmed to fit
        within the token limit. Automatically summarizes old messages
        if enabled.
        
        Args:
            chat_id: Chat identifier
            max_tokens: Maximum tokens for context
            include_system: Whether to include system messages
            
        Returns:
            List of message dicts with "role" and "content" keys
        """
        hashed_id = self._hash_chat_id(chat_id)
        
        if hashed_id not in self._conversations:
            return []
        
        conv = self._conversations[hashed_id]
        messages = conv.get("messages", [])
        current_summary = conv.get("summary", None)
        
        # Apply summarization if enabled
        if self._summarizer and len(messages) > self._summarizer.keep_recent:
            try:
                new_summary, recent_messages = await self._summarizer.maybe_summarize(
                    messages, current_summary
                )
                
                # Update conversation with new summary and trimmed messages
                if new_summary:
                    conv["summary"] = new_summary
                    conv["messages"] = recent_messages
                    logger.debug(
                        f"📝 Updated conversation {hashed_id[:8]}... "
                        f"(summary + {len(recent_messages)} recent messages)"
                    )
                    
                    # Save updated conversation to HF
                    if self._hf_enabled:
                        await self._save_to_local_storage(hashed_id, conv)
                
                messages = recent_messages
                
            except Exception as e:
                logger.warning(f"📝 Summarization failed for {hashed_id[:8]}...: {e}")
        
        # Filter to just role and content (OpenAI format)
        formatted = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in messages
            if include_system or msg["role"] != "system"
        ]
        
        # If we have a summary, prepend it as a system message
        if current_summary or conv.get("summary"):
            summary_text = conv.get("summary") or current_summary
            formatted.insert(0, {
                "role": "system",
                "content": f"Previous conversation summary:\n{summary_text}"
            })
        
        # Trim to token limit
        return self._trim_to_token_limit(formatted, max_tokens)

    async def clear_conversation(self, chat_id: str) -> bool:
        """
        Clear conversation history for a chat.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            True if conversation was cleared, False if not found
        """
        hashed_id = self._hash_chat_id(chat_id)
        
        if hashed_id in self._conversations:
            del self._conversations[hashed_id]
            
            # Remove from local storage
            if self._hf_enabled and self._local_storage_path:
                file_path = self._local_storage_path / f"{hashed_id}.json"
                if file_path.exists():
                    file_path.unlink()
            
            logger.info(f"💭 Cleared conversation for {hashed_id[:8]}...")
            return True
        
        return False

    async def get_conversation_summary(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get summary information about a conversation.
        
        Args:
            chat_id: Chat identifier
            
        Returns:
            Dict with conversation metadata or None if not found
        """
        hashed_id = self._hash_chat_id(chat_id)
        
        if hashed_id not in self._conversations:
            return None
        
        conv = self._conversations[hashed_id]
        return {
            "message_count": len(conv.get("messages", [])),
            "last_activity": conv.get("last_activity"),
            "created_at": conv.get("metadata", {}).get("created_at"),
            "unique_users": len(conv.get("metadata", {}).get("user_ids", set())),
        }

    async def _maybe_cleanup(self) -> None:
        """Run cleanup if enough time has passed since last cleanup."""
        now = datetime.now(timezone.utc)
        if now - self._last_cleanup < timedelta(minutes=CLEANUP_INTERVAL_MINUTES):
            return
        
        self._last_cleanup = now
        await self._cleanup_expired_sessions()

    async def _cleanup_expired_sessions(self) -> None:
        """Remove expired conversation sessions."""
        now = datetime.now(timezone.utc)
        cutoff = now - self.session_ttl
        
        expired = []
        for hashed_id, conv in self._conversations.items():
            last_activity = conv.get("last_activity")
            if isinstance(last_activity, datetime):
                # Make timezone-aware if needed
                if last_activity.tzinfo is None:
                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                if last_activity < cutoff:
                    expired.append(hashed_id)
        
        for hashed_id in expired:
            del self._conversations[hashed_id]
            
            # Remove from local storage
            if self._hf_enabled and self._local_storage_path:
                file_path = self._local_storage_path / f"{hashed_id}.json"
                if file_path.exists():
                    file_path.unlink()
        
        if expired:
            logger.info(f"💭 Cleaned up {len(expired)} expired conversation(s)")

    async def _save_to_local_storage(self, hashed_id: str, conv: Dict[str, Any]) -> None:
        """Save conversation to local storage for HF Hub sync."""
        if not self._local_storage_path:
            return
        
        try:
            file_path = self._local_storage_path / f"{hashed_id}.json"
            
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

    async def _load_from_hub(self) -> None:
        """Load existing conversations from HF Hub on startup."""
        if not self._hf_enabled or not self._hf_api or not self._local_storage_path:
            return
        
        try:
            import importlib

            hf = importlib.import_module("huggingface_hub")
            hf_hub_download = getattr(hf, "hf_hub_download")
            list_repo_files = getattr(hf, "list_repo_files")

            if not self.hf_repo_id or not self.hf_token:
                return
            
            # List files in the repo
            try:
                files = list_repo_files(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    token=self.hf_token,
                )
            except Exception:
                # Repo might be empty
                logger.info("💭 No existing conversations found in HF Hub")
                return
            
            # Download and load each conversation file
            json_files = [f for f in files if f.endswith(".json")]
            loaded = 0
            
            for filename in json_files[:100]:  # Limit to 100 most recent
                try:
                    local_path = hf_hub_download(
                        repo_id=self.hf_repo_id,
                        filename=filename,
                        repo_type="dataset",
                        token=self.hf_token,
                        local_dir=str(self._local_storage_path),
                    )
                    
                    with open(local_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    
                    hashed_id = Path(filename).stem
                    
                    # Restore datetime objects
                    last_activity = data.get("last_activity")
                    if last_activity:
                        last_activity = datetime.fromisoformat(last_activity)
                    else:
                        last_activity = datetime.now(timezone.utc)
                    
                    self._conversations[hashed_id] = {
                        "messages": data.get("messages", []),
                        "last_activity": last_activity,
                        "metadata": {
                            "created_at": data.get("metadata", {}).get("created_at"),
                            "user_ids": set(data.get("metadata", {}).get("user_ids", [])),
                        },
                    }
                    loaded += 1
                    
                except Exception as e:
                    logger.warning(f"⚠️ Failed to load {filename}: {e}")
            
            if loaded > 0:
                logger.info(f"💭 Loaded {loaded} conversation(s) from HF Hub")

        except ModuleNotFoundError:
            logger.info("💭 huggingface_hub not installed; skipping HF Hub conversation preload")
                
        except Exception as e:
            logger.error(f"❌ Failed to load conversations from HF Hub: {e}")

    def stop(self) -> None:
        """Stop the commit scheduler (call during shutdown)."""
        if self._commit_scheduler:
            try:
                self._commit_scheduler.stop()
                logger.info("💭 Conversation memory scheduler stopped")
            except Exception as e:
                logger.warning(f"⚠️ Error stopping commit scheduler: {e}")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get service statistics.
        
        Returns:
            Dict with memory service stats
        """
        total_messages = sum(
            len(conv.get("messages", []))
            for conv in self._conversations.values()
        )
        
        return {
            "active_conversations": len(self._conversations),
            "total_messages": total_messages,
            "hf_enabled": self._hf_enabled,
            "hf_repo_id": self.hf_repo_id if self._hf_enabled else None,
            "max_messages_per_session": self.max_messages,
            "session_ttl_hours": self.session_ttl.total_seconds() / 3600,
        }


# Singleton instance (configured during app startup)
conversation_memory_service: Optional[ConversationMemoryService] = None


def get_conversation_memory() -> Optional[ConversationMemoryService]:
    """Get the conversation memory service instance."""
    return conversation_memory_service


def init_conversation_memory(
    hf_token: Optional[str] = None,
    hf_repo_id: Optional[str] = None,
) -> ConversationMemoryService:
    """
    Initialize the conversation memory service.
    
    Call this during app startup to configure the service.
    
    Args:
        hf_token: Hugging Face API token
        hf_repo_id: HF dataset repo ID for persistence
        
    Returns:
        Configured ConversationMemoryService instance
    """
    global conversation_memory_service
    
    conversation_memory_service = ConversationMemoryService(
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
    )
    
    return conversation_memory_service
