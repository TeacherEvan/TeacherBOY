from unittest.mock import Mock

import pytest

from src.agents.translation_agent import TranslationAgent


@pytest.mark.asyncio
async def test_translation_agent_auto_starts_session_on_thai_text():
    """Thai text should auto-start a translation session (behavior restored Jun 2)."""
    agent = TranslationAgent()
    event = Mock()
    event.source = Mock()
    event.source.user_id = "U1"
    event.source.type = "group"

    assert await agent.should_handle(event, "สวัสดีครับ") is True
