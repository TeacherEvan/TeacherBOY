"""Tests for session manager deduplication."""

import pytest
from datetime import datetime, timedelta
from src.services.session_manager import SessionManager


class TestSessionManagerDeduplication:
    """Test cases for SessionManager message deduplication."""

    @pytest.fixture
    def manager(self):
        """Create a SessionManager instance."""
        return SessionManager()

    def test_first_message_not_duplicate(self, manager):
        """Test that first message is not considered duplicate."""
        chat_id = "test_chat_1"
        text = "Hello, how are you?"
        
        assert manager.is_duplicate_message(chat_id, text) is False

    def test_immediate_duplicate_detected(self, manager):
        """Test that immediate duplicate is detected."""
        chat_id = "test_chat_2"
        text = "สวัสดีครับ"
        
        # First message
        assert manager.is_duplicate_message(chat_id, text) is False
        
        # Immediate repeat should be duplicate
        assert manager.is_duplicate_message(chat_id, text) is True

    def test_different_messages_not_duplicate(self, manager):
        """Test that different messages are not duplicates."""
        chat_id = "test_chat_3"
        
        assert manager.is_duplicate_message(chat_id, "Message 1") is False
        assert manager.is_duplicate_message(chat_id, "Message 2") is False
        assert manager.is_duplicate_message(chat_id, "Message 3") is False

    def test_duplicate_expires_after_window(self):
        """Test that duplicate detection expires after time window."""
        import time
        # Create manager with 1-second window for testing
        manager = SessionManager(dedup_window_seconds=1)
        chat_id = "test_chat_4"
        text = "Test message"
        
        # First message
        assert manager.is_duplicate_message(chat_id, text) is False
        
        # Wait for window to expire
        time.sleep(1.5)
        
        # Same message should not be duplicate anymore
        assert manager.is_duplicate_message(chat_id, text) is False

    def test_independent_chat_deduplication(self, manager):
        """Test that different chats have independent deduplication."""
        chat_id_1 = "test_chat_5"
        chat_id_2 = "test_chat_6"
        text = "Same message"
        
        # Same text in different chats should not interfere
        assert manager.is_duplicate_message(chat_id_1, text) is False
        assert manager.is_duplicate_message(chat_id_2, text) is False
        
        # Repeat in each chat should be detected independently
        assert manager.is_duplicate_message(chat_id_1, text) is True
        assert manager.is_duplicate_message(chat_id_2, text) is True

    def test_clear_message_history(self, manager):
        """Test clearing message history for a chat."""
        chat_id = "test_chat_7"
        text = "Test message"
        
        # Add message
        manager.is_duplicate_message(chat_id, text)
        
        # Clear history
        manager.clear_message_history(chat_id)
        
        # Same message should not be duplicate after clearing
        assert manager.is_duplicate_message(chat_id, text) is False

    def test_history_size_limit(self):
        """Test that history is limited to max size."""
        # Create manager with small history size for testing
        manager = SessionManager(max_history_size=5)
        chat_id = "test_chat_8"
        
        # Add more messages than max size
        for i in range(10):
            manager.is_duplicate_message(chat_id, f"Message {i}")
        
        # History should be limited
        assert len(manager._message_history[chat_id]) <= 5

    def test_hash_consistency(self, manager):
        """Test that same text produces same hash."""
        text = "Test message 日本語 ไทย"
        hash1 = manager._hash_message(text)
        hash2 = manager._hash_message(text)
        
        assert hash1 == hash2
        assert len(hash1) == 16  # First 16 chars of SHA256

    def test_session_functionality_preserved(self, manager):
        """Test that existing session functionality still works."""
        chat_id = "test_chat_9"
        user_id = "user123"
        
        # Test session start/end
        assert manager.is_session_active(chat_id) is False
        
        manager.start_session(chat_id, user_id)
        assert manager.is_session_active(chat_id) is True
        
        manager.end_session(chat_id)
        assert manager.is_session_active(chat_id) is False
