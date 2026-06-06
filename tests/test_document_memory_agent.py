from unittest.mock import MagicMock, patch

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
