"""
Tests for the history log service with Zeus-themed error messages.

Tests comprehensive logging, encryption, querying, and Zeus-style errors.
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import tempfile
import os

from src.services.history_log_service import (
    HistoryLogService,
    LogEntry,
    EventType,
    LogLevel,
    AccessLevel,
    ZeusErrorMessages,
    LogEncryption,
    init_history_log,
    get_history_log,
    log_action,
)


class TestZeusErrorMessages:
    """Tests for Zeus-themed error message generator."""
    
    def test_api_failure_message(self):
        """Test API failure message generation."""
        msg = ZeusErrorMessages.get_error_message(
            "api_failure",
            error="Connection timeout",
            service="OpenRouter"
        )
        
        assert "OLYMPUS" in msg.upper() or "ZEUS" in msg.upper() or "THUNDERBOLT" in msg.upper() or "BETRAYED" in msg.upper() or "COLLAPSED" in msg.upper()
        assert "Connection timeout" in msg or "OpenRouter" in msg
    
    def test_network_error_message(self):
        """Test network error message generation."""
        msg = ZeusErrorMessages.get_error_message(
            "network_error",
            error="DNS resolution failed"
        )
        
        # Should contain mythological references
        assert any(word in msg.upper() for word in ["POSEIDON", "TYPHON", "BLOCKED", "SEVERED", "WAVES"])
    
    def test_auth_failure_message(self):
        """Test authentication failure message generation."""
        msg = ZeusErrorMessages.get_error_message(
            "auth_failure",
            error="Invalid API key"
        )
        
        assert any(word in msg.upper() for word in ["HALT", "MORTAL", "REJECTED", "UNAUTHORIZED", "CREDENTIALS"])
    
    def test_rate_limit_message(self):
        """Test rate limit message generation."""
        msg = ZeusErrorMessages.get_error_message(
            "rate_limit",
            error="429 Too Many Requests",
            wait="60 seconds"
        )
        
        assert any(word in msg.upper() for word in ["PATIENCE", "FATES", "TIME", "REST", "BOUNDS"])
    
    def test_format_exception(self):
        """Test exception formatting."""
        try:
            raise ConnectionError("Network unreachable")
        except Exception as e:
            msg = ZeusErrorMessages.format_exception(e)
        
        assert "ConnectionError" in msg
        assert "Network unreachable" in msg
    
    def test_format_exception_auto_category(self):
        """Test automatic category detection for exceptions."""
        # Test timeout detection
        try:
            raise TimeoutError("Request timed out")
        except Exception as e:
            msg = ZeusErrorMessages.format_exception(e)
        
        # Should use network_error category (contains mythological network references)
        assert "TimeoutError" in msg
    
    def test_success_message(self):
        """Test success message generation."""
        msg = ZeusErrorMessages.get_error_message("success")
        
        assert any(word in msg.upper() for word in ["OLYMPUS", "VICTORY", "SUCCESS", "REJOICES"])


class TestLogEntry:
    """Tests for LogEntry class."""
    
    def test_create_log_entry(self):
        """Test basic log entry creation."""
        entry = LogEntry(
            event_type=EventType.USER_MESSAGE,
            message="Test message",
            level=LogLevel.INFO,
            chat_id="chat_123",
            user_id="user_456",
        )
        
        assert entry.event_type == EventType.USER_MESSAGE
        assert entry.message == "Test message"
        assert entry.level == LogLevel.INFO
        assert entry.chat_id == "chat_123"
        assert entry.user_id == "user_456"
        assert entry.id.startswith("log_")
        assert entry.hash is not None
    
    def test_log_entry_to_dict(self):
        """Test serialization to dictionary."""
        entry = LogEntry(
            event_type=EventType.LLM_REQUEST,
            message="LLM call",
            chat_id="chat_123",
            user_id="user_456",
            metadata={"model": "gpt-4"},
        )
        
        # Without sensitive data
        data = entry.to_dict(include_sensitive=False)
        assert data["event_type"] == "llm_request"
        assert data["message"] == "LLM call"
        assert data["chat_id"] != "chat_123"  # Should be anonymized
        assert data["user_id"] != "user_456"  # Should be anonymized
        assert len(data["chat_id"]) == 12  # Hash length
        
        # With sensitive data
        data_sensitive = entry.to_dict(include_sensitive=True)
        assert data_sensitive["chat_id"] == "chat_123"
        assert data_sensitive["user_id"] == "user_456"
    
    def test_log_entry_from_dict(self):
        """Test deserialization from dictionary."""
        original = LogEntry(
            event_type=EventType.BOT_RESPONSE,
            message="Response message",
            level=LogLevel.INFO,
            agent_name="TestAgent",
        )
        
        data = original.to_dict(include_sensitive=True)
        restored = LogEntry.from_dict(data)
        
        assert restored.id == original.id
        assert restored.event_type == original.event_type
        assert restored.message == original.message
        assert restored.agent_name == original.agent_name
    
    def test_log_entry_hash_integrity(self):
        """Test that hash changes with content."""
        entry1 = LogEntry(
            event_type=EventType.ERROR,
            message="Error 1",
        )
        
        entry2 = LogEntry(
            event_type=EventType.ERROR,
            message="Error 2",
        )
        
        # Different messages should have different hashes
        assert entry1.hash != entry2.hash


class TestLogEncryption:
    """Tests for log encryption."""
    
    def test_encryption_disabled_by_default(self):
        """Test that encryption is disabled without key."""
        enc = LogEncryption()
        assert enc.enabled is False
        
        # Should pass through unchanged
        data = "test data"
        assert enc.encrypt(data) == data
        assert enc.decrypt(data) == data
    
    def test_encryption_with_key(self):
        """Test encryption with a key (if cryptography is available)."""
        try:
            import cryptography
            has_crypto = True
        except ImportError:
            has_crypto = False
        
        enc = LogEncryption(encryption_key="my-secret-key-123")
        
        if has_crypto:
            assert enc.enabled is True
            
            data = "sensitive log data"
            encrypted = enc.encrypt(data)
            
            assert encrypted != data  # Should be different
            
            decrypted = enc.decrypt(encrypted)
            assert decrypted == data
        else:
            # Without cryptography, should be disabled
            assert enc.enabled is False


class TestHistoryLogService:
    """Tests for the main history log service."""
    
    @pytest.fixture
    def temp_log_dir(self):
        """Create a temporary directory for logs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir
    
    @pytest.fixture
    def log_service(self, temp_log_dir):
        """Create a history log service with temp storage."""
        return HistoryLogService(
            storage_path=temp_log_dir,
            enable_file_storage=True,
        )
    
    @pytest.mark.asyncio
    async def test_basic_logging(self, log_service):
        """Test basic log entry creation."""
        entry = await log_service.log(
            event_type=EventType.USER_MESSAGE,
            message="Test user message",
            level=LogLevel.INFO,
            chat_id="chat_123",
        )
        
        assert entry is not None
        assert entry.event_type == EventType.USER_MESSAGE
        assert entry.message == "Test user message"
        
        # Check stats
        stats = log_service.get_stats()
        assert stats["total_logged"] == 1
    
    @pytest.mark.asyncio
    async def test_error_logging_with_zeus_style(self, log_service):
        """Test error logging with Zeus-themed messages."""
        entry = await log_service.log(
            event_type=EventType.LLM_ERROR,
            message="API call failed",
            level=LogLevel.ERROR,
            zeus_style=True,
        )
        
        # Should contain Zeus-style messaging
        assert any(word in entry.message.upper() for word in 
                   ["OLYMPUS", "THUNDERBOLT", "MORTAL", "ZEUS", "FAILED", "COLLAPSED", "BETRAYED", "DIVINE"])
        
        # Check stats
        stats = log_service.get_stats()
        assert stats["errors_logged"] == 1
    
    @pytest.mark.asyncio
    async def test_exception_logging(self, log_service):
        """Test logging exceptions."""
        try:
            raise ValueError("Invalid input provided")
        except Exception as e:
            entry = await log_service.log_error(
                error=e,
                agent_name="TestAgent",
                context="Testing error logging",
                zeus_style=True,
            )
        
        assert entry is not None
        assert entry.event_type == EventType.ERROR
        assert entry.agent_name == "TestAgent"
        assert entry.error_details is not None
        assert entry.error_details["type"] == "ValueError"
    
    @pytest.mark.asyncio
    async def test_user_interaction_logging(self, log_service):
        """Test logging user interactions."""
        user_entry, response_entry = await log_service.log_user_interaction(
            chat_id="chat_123",
            user_id="user_456",
            message_text="Hello Zeus!",
            agent_name="TranslationAgent",
            response_text="สวัสดี mortal!",
        )
        
        assert user_entry.event_type == EventType.USER_MESSAGE
        assert response_entry.event_type == EventType.BOT_RESPONSE
        assert user_entry.chat_id == "chat_123"
    
    @pytest.mark.asyncio
    async def test_query_logs(self, log_service):
        """Test querying logs with filters."""
        # Create multiple log entries
        await log_service.log(
            event_type=EventType.USER_MESSAGE,
            message="Message 1",
            agent_name="Agent1",
        )
        await log_service.log(
            event_type=EventType.ERROR,
            message="Error 1",
            level=LogLevel.ERROR,
            agent_name="Agent2",
        )
        await log_service.log(
            event_type=EventType.USER_MESSAGE,
            message="Message 2",
            agent_name="Agent1",
        )
        
        # Query by event type
        user_messages = await log_service.query_logs(
            event_types=[EventType.USER_MESSAGE]
        )
        assert len(user_messages) == 2
        
        # Query by level
        errors = await log_service.query_logs(
            levels=[LogLevel.ERROR]
        )
        assert len(errors) == 1
        
        # Query by agent
        agent1_logs = await log_service.query_logs(
            agent_name="Agent1"
        )
        assert len(agent1_logs) == 2
    
    @pytest.mark.asyncio
    async def test_recent_errors(self, log_service):
        """Test getting recent errors."""
        # Create some errors
        await log_service.log(
            event_type=EventType.ERROR,
            message="Error 1",
            level=LogLevel.ERROR,
        )
        await log_service.log(
            event_type=EventType.ERROR,
            message="Error 2",
            level=LogLevel.ERROR,
        )
        await log_service.log(
            event_type=EventType.USER_MESSAGE,
            message="Not an error",
            level=LogLevel.INFO,
        )
        
        recent = await log_service.get_recent_errors(limit=5)
        assert len(recent) == 2
    
    @pytest.mark.asyncio
    async def test_file_persistence(self, log_service, temp_log_dir):
        """Test that logs are persisted to file."""
        await log_service.log(
            event_type=EventType.STARTUP,
            message="System starting",
            level=LogLevel.INFO,
        )
        
        # Check that log file was created
        log_files = list(Path(temp_log_dir).glob("zeus_log_*.jsonl"))
        assert len(log_files) == 1
        
        # Check file content
        with open(log_files[0], "r") as f:
            content = f.read()
            assert "System starting" in content
    
    @pytest.mark.asyncio
    async def test_memory_limit(self, log_service):
        """Test that memory is bounded."""
        # Set a low limit for testing
        log_service.MAX_MEMORY_LOGS = 10
        
        # Create more logs than the limit
        for i in range(15):
            await log_service.log(
                event_type=EventType.USER_MESSAGE,
                message=f"Message {i}",
            )
        
        # Should only have MAX_MEMORY_LOGS in memory
        assert len(log_service._logs) == 10
        
        # Should have the most recent logs
        messages = [entry.message for entry in log_service._logs.values()]
        assert "Message 14" in messages
        assert "Message 0" not in messages  # Oldest should be evicted
    
    @pytest.mark.asyncio
    async def test_access_level_filtering(self, log_service):
        """Test access level filtering in queries."""
        await log_service.log(
            event_type=EventType.USER_MESSAGE,
            message="Public message",
            access_level=AccessLevel.PUBLIC,
        )
        await log_service.log(
            event_type=EventType.ADMIN_ACTION,
            message="Admin action",
            access_level=AccessLevel.ADMIN,
        )
        await log_service.log(
            event_type=EventType.ERROR,
            message="System error",
            access_level=AccessLevel.SYSTEM,
        )
        
        # Admin can see admin and below
        admin_view = await log_service.query_logs(access_level=AccessLevel.ADMIN)
        assert len(admin_view) == 2  # Public and Admin
        
        # Internal can see internal and below
        internal_view = await log_service.query_logs(access_level=AccessLevel.INTERNAL)
        assert len(internal_view) == 1  # Only Public
    
    def test_stats(self, log_service):
        """Test statistics tracking."""
        stats = log_service.get_stats()
        
        assert "total_logged" in stats
        assert "errors_logged" in stats
        assert "warnings_logged" in stats
        assert "logs_in_memory" in stats
        assert "file_storage_enabled" in stats
        assert "encryption_enabled" in stats


class TestLogActionDecorator:
    """Tests for the @log_action decorator."""
    
    @pytest.mark.asyncio
    async def test_decorator_logs_success(self):
        """Test that decorator logs successful execution."""
        # Initialize service
        with tempfile.TemporaryDirectory() as tmpdir:
            init_history_log(storage_path=tmpdir)
            service = get_history_log()
            
            @log_action(agent_name="TestAgent")
            async def successful_function():
                return "success"
            
            result = await successful_function()
            
            assert result == "success"
            
            # Check that completion was logged
            logs = await service.query_logs(agent_name="TestAgent")
            assert len(logs) >= 1
    
    @pytest.mark.asyncio
    async def test_decorator_logs_errors(self):
        """Test that decorator logs errors with Zeus style."""
        with tempfile.TemporaryDirectory() as tmpdir:
            init_history_log(storage_path=tmpdir)
            service = get_history_log()
            
            @log_action(agent_name="FailingAgent", zeus_errors=True)
            async def failing_function():
                raise RuntimeError("Something went wrong")
            
            with pytest.raises(RuntimeError):
                await failing_function()
            
            # Check that error was logged
            errors = await service.get_recent_errors(limit=5)
            assert len(errors) >= 1


class TestInitialization:
    """Tests for service initialization."""
    
    def test_init_and_get(self):
        """Test initialization and retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = init_history_log(storage_path=tmpdir)
            
            assert service is not None
            assert get_history_log() is service
    
    def test_init_with_encryption(self):
        """Test initialization with encryption key."""
        with tempfile.TemporaryDirectory() as tmpdir:
            service = init_history_log(
                storage_path=tmpdir,
                encryption_key="test-encryption-key",
            )
            
            stats = service.get_stats()
            # Encryption enabled depends on cryptography package
            assert "encryption_enabled" in stats


class TestEventTypes:
    """Tests for event type coverage."""
    
    def test_all_event_types_defined(self):
        """Verify all expected event types exist."""
        expected_types = [
            "user_message", "bot_response", "command_executed",
            "agent_activated", "agent_completed", "agent_failed",
            "startup", "shutdown", "config_change",
            "translation_request", "translation_success", "translation_failed",
            "llm_request", "llm_response", "llm_error", "memory_cleared",
            "news_request", "news_delivered",
            "admin_action", "rate_limited",
            "auth_success", "auth_failure", "access_denied",
            "error", "warning",
        ]
        
        actual_types = [e.value for e in EventType]
        
        for expected in expected_types:
            assert expected in actual_types, f"Missing event type: {expected}"
