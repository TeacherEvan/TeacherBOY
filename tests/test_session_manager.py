"""Tests for session manager deduplication."""

import pytest

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


class TestSessionManagerSleepWake:
    """Test cases for SessionManager sleep/wake functionality."""

    @pytest.fixture
    def manager(self):
        """Create a SessionManager instance."""
        return SessionManager(default_sleep_hours=24)

    def test_initial_not_sleeping(self, manager):
        """Test that chat is not sleeping initially."""
        chat_id = "test_sleep_1"
        assert manager.is_sleeping(chat_id) is False

    def test_sleep_chat(self, manager):
        """Test putting a chat to sleep."""
        chat_id = "test_sleep_2"

        manager.sleep_chat(chat_id)
        assert manager.is_sleeping(chat_id) is True

    def test_sleep_with_custom_hours(self, manager):
        """Test sleeping for custom duration."""
        chat_id = "test_sleep_3"

        manager.sleep_chat(chat_id, hours=12)
        assert manager.is_sleeping(chat_id) is True
        # Should have around 12 hours remaining
        remaining = manager.get_sleep_remaining(chat_id)
        assert 11 <= remaining <= 13

    def test_wake_chat(self, manager):
        """Test waking a sleeping chat."""
        chat_id = "test_sleep_4"

        manager.sleep_chat(chat_id)
        assert manager.is_sleeping(chat_id) is True

        result = manager.wake_chat(chat_id)
        assert result is True
        assert manager.is_sleeping(chat_id) is False

    def test_wake_non_sleeping_chat(self, manager):
        """Test waking a chat that's not sleeping."""
        chat_id = "test_sleep_5"

        result = manager.wake_chat(chat_id)
        assert result is False

    def test_session_not_active_while_sleeping(self, manager):
        """Test that session is not active while sleeping."""
        chat_id = "test_sleep_6"
        user_id = "user456"

        # Start a session
        manager.start_session(chat_id, user_id)
        assert manager.is_session_active(chat_id) is True

        # Sleep the chat
        manager.sleep_chat(chat_id)
        # Session should not be active while sleeping
        assert manager.is_session_active(chat_id) is False

    def test_sleep_ends_active_session(self, manager):
        """Test that sleeping ends any active session."""
        chat_id = "test_sleep_7"
        user_id = "user789"

        # Start a session
        manager.start_session(chat_id, user_id)
        assert chat_id in manager._active_sessions

        # Sleep the chat
        manager.sleep_chat(chat_id)
        # Active session should be cleared
        assert chat_id not in manager._active_sessions

    def test_get_sleep_remaining_not_sleeping(self, manager):
        """Test sleep remaining returns 0 when not sleeping."""
        chat_id = "test_sleep_8"
        assert manager.get_sleep_remaining(chat_id) == 0

    def test_get_sleep_remaining_while_sleeping(self, manager):
        """Test sleep remaining returns correct hours."""
        chat_id = "test_sleep_9"

        manager.sleep_chat(chat_id, hours=24)
        remaining = manager.get_sleep_remaining(chat_id)
        # Should be around 24 hours (allowing for small time differences)
        assert 23 <= remaining <= 25

    def test_independent_chat_sleep_states(self, manager):
        """Test that different chats have independent sleep states."""
        chat_id_1 = "test_sleep_10"
        chat_id_2 = "test_sleep_11"

        # Sleep one chat
        manager.sleep_chat(chat_id_1)

        # Check states
        assert manager.is_sleeping(chat_id_1) is True
        assert manager.is_sleeping(chat_id_2) is False


def test_marks_second_cross_language_message_within_two_seconds_as_echo():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "สวัสดี", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=1) is True


def test_keeps_first_message_when_order_is_reversed():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "สวัสดี", now_offset_seconds=1) is True


def test_does_not_ignore_after_two_second_window():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "สวัสดี", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=3) is False


def test_does_not_ignore_same_language_messages():
    manager = SessionManager()

    assert manager.should_ignore_cross_language_echo("group_123", "hello", now_offset_seconds=0) is False
    assert manager.should_ignore_cross_language_echo("group_123", "how are you", now_offset_seconds=1) is False
