"""Tests for conversation memory service."""

import sys
from unittest.mock import MagicMock

import pytest

from src.services.conversation_memory_service import (
    ConversationMemoryService,
    get_conversation_memory,
    init_conversation_memory,
)


class TestConversationMemoryService:
    """Tests for ConversationMemoryService class."""

    @pytest.fixture
    def memory_service(self):
        """Create a memory service with in-memory storage only."""
        service = ConversationMemoryService(
            max_messages=10,
            session_ttl_hours=24,
        )
        return service

    @pytest.mark.asyncio
    async def test_add_and_get_messages(self, memory_service):
        """Test adding and retrieving messages."""
        chat_id = "test_chat_123"

        # Add user message
        await memory_service.add_message(chat_id, "user", "Hello Zeus!")

        # Add assistant response
        await memory_service.add_message(chat_id, "assistant", "Greetings, mortal!")

        # Get context
        context = await memory_service.get_context_messages(chat_id)

        assert len(context) == 2
        assert context[0]["role"] == "user"
        assert context[0]["content"] == "Hello Zeus!"
        assert context[1]["role"] == "assistant"
        assert context[1]["content"] == "Greetings, mortal!"

    @pytest.mark.asyncio
    async def test_clear_conversation(self, memory_service):
        """Test clearing conversation memory."""
        chat_id = "test_chat_456"

        # Add messages
        await memory_service.add_message(chat_id, "user", "Test message")
        await memory_service.add_message(chat_id, "assistant", "Response")

        # Clear
        await memory_service.clear_conversation(chat_id)

        # Verify empty
        context = await memory_service.get_context_messages(chat_id)
        assert len(context) == 0

    @pytest.mark.asyncio
    async def test_max_messages_limit(self, memory_service):
        """Test that old messages are trimmed when max is reached."""
        chat_id = "test_chat_789"

        # Add more than max_messages (10)
        for i in range(15):
            await memory_service.add_message(chat_id, "user", f"Message {i}")

        # Get context - should have at most max_messages
        context = await memory_service.get_context_messages(chat_id)
        assert len(context) <= 10
        # Most recent messages should be kept
        assert "Message 14" in context[-1]["content"]

    @pytest.mark.asyncio
    async def test_empty_chat_returns_empty_list(self, memory_service):
        """Test that non-existent chat returns empty context."""
        context = await memory_service.get_context_messages("nonexistent_chat")
        assert context == []

    @pytest.mark.asyncio
    async def test_conversation_summary(self, memory_service):
        """Test getting conversation summary."""
        chat_id = "test_chat_summary"

        # Add messages
        await memory_service.add_message(chat_id, "user", "Hello", "user_123")
        await memory_service.add_message(chat_id, "assistant", "Hi there!")

        summary = await memory_service.get_conversation_summary(chat_id)

        assert summary["message_count"] == 2
        assert summary["unique_users"] >= 1  # At least one user
        assert summary["last_activity"] is not None

    @pytest.mark.asyncio
    async def test_hash_chat_id_consistency(self, memory_service):
        """Test that chat ID hashing is consistent."""
        chat_id = "user_U1234567890abcdef"

        hash1 = memory_service._hash_chat_id(chat_id)
        hash2 = memory_service._hash_chat_id(chat_id)

        assert hash1 == hash2
        assert len(hash1) == 16  # Truncated SHA256

    @pytest.mark.asyncio
    async def test_different_chat_ids_different_hashes(self, memory_service):
        """Test that different chat IDs get different hashes."""
        hash1 = memory_service._hash_chat_id("user_123")
        hash2 = memory_service._hash_chat_id("user_456")

        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_token_estimation(self, memory_service):
        """Test token estimation for messages."""
        # Simple text should estimate ~1 token per 4 chars
        short_text = "Hello"  # 5 chars
        long_text = "A" * 400  # 400 chars

        short_estimate = memory_service._estimate_tokens(short_text)
        long_estimate = memory_service._estimate_tokens(long_text)

        assert short_estimate < long_estimate
        assert short_estimate >= 1  # At least 1 token
        assert long_estimate >= 100  # ~100 tokens for 400 chars


class TestConversationMemorySingleton:
    """Tests for singleton pattern."""

    def test_service_uses_explicit_storage_path(self, tmp_path):
        """Test that the service stores an explicit local storage path."""
        storage_path = tmp_path / "conversations"

        service = ConversationMemoryService(
            storage_path=str(storage_path),
            max_messages=10,
            session_ttl_hours=24,
        )

        assert service.local_storage_path == storage_path

    def test_init_conversation_memory_accepts_storage_path(self, tmp_path):
        """Test that the singleton initializer forwards an explicit storage path."""
        storage_path = tmp_path / "conversation-cache"

        service = init_conversation_memory(storage_path=str(storage_path))

        assert service.local_storage_path == storage_path

    def test_init_conversation_memory_uses_configured_default_storage_path(self, tmp_path, monkeypatch):
        """Test that initialization uses settings.conversation_storage_path by default."""
        storage_path = tmp_path / "configured-conversations"

        monkeypatch.setattr(
            "src.services.conversation_memory_service.settings.conversation_storage_path",
            str(storage_path),
        )

        service = init_conversation_memory()

        assert service.local_storage_path == storage_path

    def test_init_conversation_memory_hf_uses_configured_storage_path(self, tmp_path, monkeypatch):
        """Test HF initialization uses the configured storage path for local sync cache."""

        class FakeHfApi:
            def __init__(self, token):
                self.token = token

            def create_repo(self, **kwargs):
                return None

        class FakeCommitScheduler:
            def __init__(self, **kwargs):
                self.kwargs = kwargs

            def stop(self):
                return None

        fake_module = MagicMock()
        fake_module.HfApi = FakeHfApi
        fake_module.CommitScheduler = FakeCommitScheduler

        storage_path = tmp_path / "hf-conversations"
        created_tasks = []

        def fake_create_task(coro):
            created_tasks.append(coro)
            coro.close()
            return MagicMock()

        monkeypatch.setattr(
            "src.services.conversation_memory_service.settings.conversation_storage_path",
            str(storage_path),
        )
        monkeypatch.setattr(
            "src.services.conversation_memory_service.asyncio.create_task",
            fake_create_task,
        )
        monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)

        service = init_conversation_memory(
            hf_token="hf_token_1234567890",
            hf_repo_id="user/test-conversations",
        )

        assert service._hf_enabled is True
        assert service._local_storage_path == storage_path
        assert service._commit_scheduler.kwargs["folder_path"] == str(storage_path)
        assert created_tasks

    def test_init_without_hf_creates_inmemory(self):
        """Test initialization without HF credentials uses in-memory storage."""
        service = init_conversation_memory()

        assert service is not None
        assert service._hf_enabled is False

    def test_get_conversation_memory_returns_singleton(self):
        """Test that get_conversation_memory returns the initialized service."""
        # Initialize first
        init_service = init_conversation_memory()

        # Get should return same instance
        get_service = get_conversation_memory()

        assert get_service is init_service


class TestLLMAgentMemoryIntegration:
    """Tests for LLM agent memory integration."""

    @pytest.mark.asyncio
    async def test_ms_green_clear_command_recognized(self):
        """Test that Ms. Green clear command is recognized."""
        from src.agents.llm_agent import LLMAgent

        agent = LLMAgent()

        # These should be recognized as clear commands
        assert agent._parse_command("Ms. Green clear") == "clear"
        assert agent._parse_command("Ms. Green forget") == "forget"
        assert agent._parse_command("Ms. Green reset") == "reset"

    @pytest.mark.asyncio
    async def test_get_chat_id_formats(self):
        """Test chat ID extraction from various event sources."""
        from unittest.mock import MagicMock

        from src.agents.llm_agent import LLMAgent

        agent = LLMAgent()

        # Test user chat
        event = MagicMock()
        event.source = MagicMock()
        event.source.user_id = "U123"
        event.source.group_id = None
        event.source.room_id = None

        chat_id = agent._get_chat_id(event)
        assert chat_id == "user_U123"

        # Test group chat
        event.source.group_id = "G456"
        chat_id = agent._get_chat_id(event)
        assert chat_id == "group_G456"

        # Test room chat
        event.source.group_id = None
        event.source.room_id = "R789"
        chat_id = agent._get_chat_id(event)
        assert chat_id == "room_R789"
