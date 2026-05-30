import pytest
from unittest.mock import Mock

from src.agents.translation_agent import TranslationAgent


@pytest.mark.asyncio
async def test_translation_agent_does_not_auto_handle_plain_thai_after_rework():
    agent = TranslationAgent()
    event = Mock()
    event.source = Mock()
    event.source.user_id = "U1"
    event.source.type = "group"

    assert await agent.should_handle(event, "สวัสดีครับ") is False