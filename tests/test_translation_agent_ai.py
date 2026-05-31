import pytest
from unittest.mock import AsyncMock, Mock

from src.agents.translation_agent import TranslationAgent
from src.services.ai_translation_service import AITranslationResult


@pytest.mark.asyncio
async def test_translate_message_uses_ai_translation_service():
    service = Mock()
    service.translate = AsyncMock(
        return_value=AITranslationResult(
            text="สวัสดี",
            provider="github_models",
        )
    )

    agent = TranslationAgent(ai_translation_service=service)

    translated = await agent._translate_message("Hello", "user_123")

    assert translated == "สวัสดี"
    service.translate.assert_awaited_once_with(
        "Hello",
        source_lang="en",
        target_lang="th",
    )