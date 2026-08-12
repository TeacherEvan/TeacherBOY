from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.translation_agent import TranslationAgent


@pytest.mark.asyncio
async def test_translate_message_uses_ai_translation_service():
    service = Mock()
    translation_result = Mock()
    translation_result.text = "สวัสดี"
    translation_result.provider = "mock"
    service.translate = AsyncMock(return_value=translation_result)

    agent = TranslationAgent(ai_translation_service=service)

    translated = await agent._translate_message(
        "this is a long text message that definitely exceeds thirty characters", "user_123"
    )

    assert translated == "สวัสดี"
    service.translate.assert_awaited_with(
        "this is a long text message that definitely exceeds thirty characters",
        source_lang="en",
        target_lang="th",
    )
