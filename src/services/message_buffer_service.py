"""
Message Buffer Service - Stores recent messages for retrospective scraping.

This service addresses a LINE API limitation: the LINE Messaging API does NOT
support retrieving past message history from groups. Messages are only received
via real-time webhooks.

Solution: Store incoming messages in a per-chat circular buffer so that
features like "Zeus Scrape" can retrieve recent messages for AI-powered
date extraction.

Architecture:
- In-memory storage (no persistence needed for scraping use case)
- Per-chat circular buffer with configurable max size
- Thread-safe operations using asyncio locks
- Automatic cleanup of old messages (TTL-based)
- Session owner tracking to support multi-user groups

Usage:
1. Hook into main.py webhook handler to store all incoming text messages
2. Call get_recent_messages(chat_id) to retrieve buffered messages
3. Messages auto-expire after TTL (default: 2 hours)
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, List, Optional
from threading import RLock

logger = logging.getLogger(__name__)

# Configuration defaults
DEFAULT_MAX_MESSAGES = 20  # Max messages per chat
DEFAULT_TTL_SECONDS = 7200  # 2 hours - messages expire after this
DEFAULT_CLEANUP_INTERVAL = 300  # 5 minutes


@dataclass
class BufferedMessage:
    """Represents a single buffered message."""
    
    text: str
    user_id: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    message_id: Optional[str] = None
    
    def is_expired(self, ttl_seconds: int) -> bool:
        """Check if message has expired based on TTL."""
        age = (datetime.now(timezone.utc) - self.timestamp).total_seconds()
        return age > ttl_seconds


@dataclass
class ChatBuffer:
    """Buffer for a single chat/group."""
    
    messages: Deque[BufferedMessage] = field(
        default_factory=lambda: deque(maxlen=DEFAULT_MAX_MESSAGES)
    )
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def add_message(self, message: BufferedMessage) -> None:
        """Add message to buffer (oldest auto-removed if at capacity)."""
        self.messages.append(message)
        self.last_activity = datetime.now(timezone.utc)
    
    def get_messages(
        self, 
        limit: int = 10, 
        ttl_seconds: int = DEFAULT_TTL_SECONDS
    ) -> List[BufferedMessage]:
        """
        Get recent non-expired messages.
        
        Args:
            limit: Maximum number of messages to return
            ttl_seconds: Exclude messages older than this
            
        Returns:
            List of recent messages (newest last)
        """
        # Filter out expired messages
        valid_messages = [
            msg for msg in self.messages 
            if not msg.is_expired(ttl_seconds)
        ]
        
        # Return most recent up to limit
        return valid_messages[-limit:] if valid_messages else []
    
    def clear_expired(self, ttl_seconds: int) -> int:
        """
        Remove expired messages from buffer.
        
        Returns:
            Number of messages removed
        """
        original_count = len(self.messages)
        
        # Keep only non-expired messages
        valid_messages = [
            msg for msg in self.messages 
            if not msg.is_expired(ttl_seconds)
        ]
        
        # Recreate deque with valid messages
        self.messages = deque(valid_messages, maxlen=DEFAULT_MAX_MESSAGES)
        
        removed = original_count - len(self.messages)
        return removed


class MessageBufferService:
    """
    Service for buffering recent messages per chat.
    
    Thread-safe and async-compatible. Designed for in-memory only storage
    to support features like "Zeus Scrape" that need recent message history.
    """
    
    def __init__(
        self,
        max_messages_per_chat: int = DEFAULT_MAX_MESSAGES,
        message_ttl_seconds: int = DEFAULT_TTL_SECONDS,
        cleanup_interval_seconds: int = DEFAULT_CLEANUP_INTERVAL,
    ):
        """
        Initialize message buffer service.
        
        Args:
            max_messages_per_chat: Maximum messages to store per chat
            message_ttl_seconds: Messages expire after this many seconds
            cleanup_interval_seconds: How often to run cleanup task
        """
        self._buffers: Dict[str, ChatBuffer] = {}
        self._lock = RLock()
        self._max_messages = max_messages_per_chat
        self._ttl_seconds = message_ttl_seconds
        self._cleanup_interval = cleanup_interval_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            f"📝 MessageBufferService initialized "
            f"(max={max_messages_per_chat}, ttl={message_ttl_seconds}s)"
        )
    
    def store_message(
        self,
        chat_id: str,
        text: str,
        user_id: str,
        message_id: Optional[str] = None,
    ) -> None:
        """
        Store an incoming message in the buffer.
        
        Call this from the webhook handler for every incoming text message.
        
        Args:
            chat_id: Normalized chat ID (user_xxx, group_xxx, room_xxx)
            text: Message text content
            user_id: LINE user ID of sender
            message_id: Optional LINE message ID
        """
        if not chat_id or not text:
            return
        
        with self._lock:
            if chat_id not in self._buffers:
                self._buffers[chat_id] = ChatBuffer(
                    messages=deque(maxlen=self._max_messages)
                )
            
            message = BufferedMessage(
                text=text,
                user_id=user_id,
                message_id=message_id,
            )
            
            self._buffers[chat_id].add_message(message)
            
        logger.debug(
            f"📝 Buffered message in {chat_id}: "
            f"'{text[:30]}...' from {user_id}"
        )
    
    def get_recent_messages(
        self,
        chat_id: str,
        limit: int = 10,
        exclude_user_id: Optional[str] = None,
    ) -> List[BufferedMessage]:
        """
        Retrieve recent messages from a chat's buffer.
        
        Args:
            chat_id: Normalized chat ID
            limit: Maximum number of messages to return
            exclude_user_id: Optional user ID to exclude (e.g., bot's own messages)
            
        Returns:
            List of recent messages (newest last)
        """
        with self._lock:
            buffer = self._buffers.get(chat_id)
            if not buffer:
                logger.debug(f"📝 No buffer found for chat {chat_id}")
                return []
            
            messages = buffer.get_messages(
                limit=limit * 2 if exclude_user_id else limit,  # Get more to filter
                ttl_seconds=self._ttl_seconds
            )
            
            # Filter out excluded user's messages if specified
            if exclude_user_id:
                messages = [
                    msg for msg in messages 
                    if msg.user_id != exclude_user_id
                ][:limit]
            
            return messages
    
    def get_message_texts(
        self,
        chat_id: str,
        limit: int = 10,
        exclude_user_id: Optional[str] = None,
    ) -> List[str]:
        """
        Get just the text content of recent messages.
        
        Convenience method for passing to AI extraction services.
        
        Args:
            chat_id: Normalized chat ID
            limit: Maximum number of messages to return
            exclude_user_id: Optional user ID to exclude
            
        Returns:
            List of message text strings (newest last)
        """
        messages = self.get_recent_messages(
            chat_id, limit, exclude_user_id
        )
        return [msg.text for msg in messages]
    
    def get_buffer_stats(self, chat_id: str) -> Dict[str, int]:
        """
        Get statistics about a chat's buffer.
        
        Returns:
            Dict with 'total_messages' and 'valid_messages' counts
        """
        with self._lock:
            buffer = self._buffers.get(chat_id)
            if not buffer:
                return {"total_messages": 0, "valid_messages": 0}
            
            total = len(buffer.messages)
            valid = len(buffer.get_messages(
                limit=total, ttl_seconds=self._ttl_seconds
            ))
            
            return {
                "total_messages": total,
                "valid_messages": valid
            }
    
    def clear_chat_buffer(self, chat_id: str) -> int:
        """
        Clear all messages from a specific chat's buffer.
        
        Args:
            chat_id: Normalized chat ID
            
        Returns:
            Number of messages cleared
        """
        with self._lock:
            buffer = self._buffers.get(chat_id)
            if not buffer:
                return 0
            
            count = len(buffer.messages)
            buffer.messages.clear()
            
            logger.info(f"📝 Cleared {count} messages from buffer {chat_id}")
            return count
    
    def clear_all_buffers(self) -> int:
        """
        Clear all message buffers.
        
        Returns:
            Total number of messages cleared
        """
        with self._lock:
            total = sum(len(b.messages) for b in self._buffers.values())
            self._buffers.clear()
            
            logger.info(f"📝 Cleared all buffers ({total} messages total)")
            return total
    
    # =========================================================================
    # Background Cleanup
    # =========================================================================
    
    def start_cleanup(self) -> None:
        """Start background cleanup task."""
        if self._running:
            return
        
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("📝 Message buffer cleanup task started")
    
    def stop_cleanup(self) -> None:
        """Stop background cleanup task."""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            self._cleanup_task = None
        logger.info("📝 Message buffer cleanup task stopped")
    
    async def _cleanup_loop(self) -> None:
        """Background task to clean up expired messages."""
        while self._running:
            try:
                await asyncio.sleep(self._cleanup_interval)
                
                if not self._running:
                    break
                
                removed = self._run_cleanup()
                if removed > 0:
                    logger.debug(f"📝 Cleanup removed {removed} expired messages")
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"📝 Cleanup error: {e}", exc_info=True)
    
    def _run_cleanup(self) -> int:
        """
        Run cleanup on all buffers.
        
        Returns:
            Total number of messages removed
        """
        total_removed = 0
        
        with self._lock:
            # Clean up expired messages in each buffer
            for chat_id, buffer in list(self._buffers.items()):
                removed = buffer.clear_expired(self._ttl_seconds)
                total_removed += removed
                
                # Remove empty buffers to save memory
                if len(buffer.messages) == 0:
                    del self._buffers[chat_id]
        
        return total_removed
    
    def get_service_stats(self) -> Dict[str, int]:
        """
        Get overall service statistics.
        
        Returns:
            Dict with service-wide stats
        """
        with self._lock:
            total_chats = len(self._buffers)
            total_messages = sum(len(b.messages) for b in self._buffers.values())
            
            return {
                "active_chat_buffers": total_chats,
                "total_buffered_messages": total_messages,
                "max_messages_per_chat": self._max_messages,
                "message_ttl_seconds": self._ttl_seconds,
            }


# Singleton instance
message_buffer_service = MessageBufferService()
