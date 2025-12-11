"""Unit tests for message deduplication service."""

import pytest
from datetime import timedelta
import time
from src.services.message_dedup import MessageDeduplicator


class TestMessageDeduplicator:
    """Test cases for MessageDeduplicator class."""

    def test_init_default_values(self):
        """Test deduplicator initialization with default values."""
        dedup = MessageDeduplicator()
        assert dedup.ttl == timedelta(seconds=60)

    def test_init_custom_values(self):
        """Test deduplicator initialization with custom values."""
        dedup = MessageDeduplicator(ttl_seconds=30)
        assert dedup.ttl == timedelta(seconds=30)

    def test_is_duplicate_first_message(self):
        """Test that first occurrence of a message is not a duplicate."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_1"
        message = "Hello, world!"

        assert dedup.is_duplicate(chat_id, message) is False

    def test_is_duplicate_repeated_message(self):
        """Test that repeated message is detected as duplicate."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_2"
        message = "Hello, world!"

        # First occurrence
        assert dedup.is_duplicate(chat_id, message) is False

        # Second occurrence should be duplicate
        assert dedup.is_duplicate(chat_id, message) is True

        # Third occurrence should still be duplicate
        assert dedup.is_duplicate(chat_id, message) is True

    def test_different_messages_not_duplicate(self):
        """Test that different messages are not considered duplicates."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_3"

        assert dedup.is_duplicate(chat_id, "Message 1") is False
        assert dedup.is_duplicate(chat_id, "Message 2") is False
        assert dedup.is_duplicate(chat_id, "Message 3") is False

    def test_different_chats_independent(self):
        """Test that different chats have independent deduplication."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        message = "Same message"

        # Same message in different chats should not be duplicates
        assert dedup.is_duplicate("chat_1", message) is False
        assert dedup.is_duplicate("chat_2", message) is False
        assert dedup.is_duplicate("chat_3", message) is False

        # But should be duplicates within same chat
        assert dedup.is_duplicate("chat_1", message) is True

    def test_ttl_expiration(self):
        """Test that messages expire after TTL."""
        dedup = MessageDeduplicator(ttl_seconds=1)  # 1 second TTL
        chat_id = "test_chat_4"
        message = "Will expire soon"

        # First occurrence
        assert dedup.is_duplicate(chat_id, message) is False

        # Immediately should be duplicate
        assert dedup.is_duplicate(chat_id, message) is True

        # Wait for TTL to expire
        time.sleep(1.1)

        # Should not be duplicate anymore
        assert dedup.is_duplicate(chat_id, message) is False

    def test_clear_chat_history(self):
        """Test clearing deduplication history for a specific chat."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_5"
        message = "Test message"

        # Create duplicate
        dedup.is_duplicate(chat_id, message)
        assert dedup.is_duplicate(chat_id, message) is True

        # Clear history
        dedup.clear_chat_history(chat_id)

        # Should not be duplicate anymore
        assert dedup.is_duplicate(chat_id, message) is False

    def test_cleanup_all(self):
        """Test cleanup of all expired messages."""
        dedup = MessageDeduplicator(ttl_seconds=1)

        # Add messages to multiple chats
        dedup.is_duplicate("chat_1", "msg1")
        dedup.is_duplicate("chat_2", "msg2")
        dedup.is_duplicate("chat_3", "msg3")

        assert len(dedup.seen) == 3

        # Wait for expiration
        time.sleep(1.1)

        # Cleanup
        dedup.cleanup_all()

        # All should be cleared
        assert len(dedup.seen) == 0

    def test_thai_unicode_messages(self):
        """Test deduplication with Thai Unicode characters."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_6"
        thai_message = "สวัสดีครับ"

        assert dedup.is_duplicate(chat_id, thai_message) is False
        assert dedup.is_duplicate(chat_id, thai_message) is True

    def test_emoji_messages(self):
        """Test deduplication with emoji characters."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_7"
        emoji_message = "Hello! 👋🌟✨"

        assert dedup.is_duplicate(chat_id, emoji_message) is False
        assert dedup.is_duplicate(chat_id, emoji_message) is True

    def test_long_messages(self):
        """Test deduplication with very long messages."""
        dedup = MessageDeduplicator(ttl_seconds=60)
        chat_id = "test_chat_8"
        long_message = "A" * 10000  # 10k character message

        assert dedup.is_duplicate(chat_id, long_message) is False
        assert dedup.is_duplicate(chat_id, long_message) is True

    def test_singleton_import(self):
        """Test that singleton instance can be imported."""
        from src.services.message_dedup import message_dedup

        assert message_dedup is not None
        assert isinstance(message_dedup, MessageDeduplicator)
        assert message_dedup.ttl == timedelta(seconds=60)
