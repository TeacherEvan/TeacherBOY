"""Tests for ReceiptAgent — additive receipt scanning agent."""

from unittest.mock import MagicMock, patch

import pytest
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from src.agents.receipt_agent import ReceiptAgent
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.profiler_session_manager import profiler_session_manager


@pytest.mark.asyncio
async def test_receipt_agent_priority():
    agent = ReceiptAgent()
    assert agent.get_priority() == 8


@pytest.mark.asyncio
async def test_receipt_agent_should_handle_bare_image_no_sessions():
    """Should handle bare image when no other agent is waiting."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    _chat_id = "test_group"
    _user_id = "test_user"

    # Mock no active sessions
    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=True):
                    result = await agent.should_handle(event, "")
                    assert result is True


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_when_image_analyzer_waiting():
    """Should NOT handle when image_analyzer is waiting for image (priority 7 wins)."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=True):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=True):
                    result = await agent.should_handle(event, "")
                    assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_when_profiler_waiting():
    """Should NOT handle when profiler is waiting for image (priority 7 wins)."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=True):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=True):
                    result = await agent.should_handle(event, "")
                    assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_text_only():
    """Should not handle text-only messages."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=TextMessageContent)
    event.message.type = "text"
    event.message.text = "hello"

    result = await agent.should_handle(event, "hello")
    assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_unlinked_user():
    """Should not handle if user not linked to Budget Boss."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=False):
                result = await agent.should_handle(event, "")
                assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_disabled():
    """Should not handle if receipt feature disabled."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=False):
                    result = await agent.should_handle(event, "")
                    assert result is False
