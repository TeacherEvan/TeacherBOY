from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from linebot.v3.webhooks import MessageEvent, TextMessageContent

from src.agents.document_memory_agent import DocumentMemoryAgent


@pytest.fixture
def text_event():
    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=TextMessageContent)
    event.source = MagicMock()
    event.source.user_id = "UUSER"
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "test_reply_token"
    return event


@pytest.mark.asyncio
async def test_document_memory_agent_accepts_ms_green_prefix(text_event):
    document_service = MagicMock()

    with patch("src.agents.document_memory_agent.settings") as mock_settings:
        mock_settings.document_memory_enabled = True
        agent = DocumentMemoryAgent(document_service=document_service)

        assert await agent.should_handle(text_event, "Ms. Green docs") is True


@pytest.mark.asyncio
async def test_document_memory_agent_rejects_legacy_zeus_prefix(text_event):
    document_service = MagicMock()

    with patch("src.agents.document_memory_agent.settings") as mock_settings:
        mock_settings.document_memory_enabled = True
        agent = DocumentMemoryAgent(document_service=document_service)

        assert await agent.should_handle(text_event, "Zeus docs") is False


@pytest.mark.asyncio
async def test_document_memory_agent_should_handle_analyze(text_event):
    document_service = MagicMock()
    document_service.find_by_name.return_value = []
    document_service.get_document = AsyncMock(return_value=None)

    with patch("src.agents.document_memory_agent.settings") as mock_settings:
        mock_settings.document_memory_enabled = True
        agent = DocumentMemoryAgent(document_service=document_service)

        # Direct doc analyze should be True immediately
        assert await agent.should_handle(text_event, "Ms. Green analyze doc test") is True
        assert await agent.should_handle(text_event, "Ms. Green doc summarize test") is True

        # Fuzzy match should query service
        document_service.find_by_name.return_value = [{"id": "123", "file_name": "test.pdf"}]
        assert await agent.should_handle(text_event, "Ms. Green analyze test") is True


@pytest.mark.asyncio
async def test_document_memory_agent_handle_command_analyze(text_event):
    document_service = MagicMock()
    document_service.get_document_text.return_value = "This is a document content."
    document_service.find_by_name.return_value = []

    agent = DocumentMemoryAgent(document_service=document_service)

    line_bot_api = MagicMock()

    with patch("src.utils.llm_fallback.chat_completion_with_fallback", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = "Summary of document."

        result = await agent.handle(text_event, "Ms. Green analyze doc 123", line_bot_api)

        assert result is True
        # Check if reply_message was called for confirmation
        line_bot_api.reply_message.assert_called_once()
        # Check if push_message was called for final summary
        line_bot_api.push_message.assert_called_once()
        args, kwargs = line_bot_api.push_message.call_args
        push_req = args[0]
        assert push_req.messages[0].text == "Summary of document."
