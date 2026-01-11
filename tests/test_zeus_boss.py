import pytest
from unittest.mock import AsyncMock, MagicMock

from linebot.v3.webhooks import MessageEvent, Source
from linebot.v3.messaging import MessagingApi


@pytest.mark.asyncio
async def test_zeus_boss_reply_is_exact():
    from src.agents.llm_agent import LLMAgent

    agent = LLMAgent()
    event = MagicMock(spec=MessageEvent)
    event.source = MagicMock(spec=Source)
    event.source.type = "user"
    event.source.user_id = "user123"
    event.reply_token = "reply_token"

    line_bot_api = MagicMock(spec=MessagingApi)
    line_bot_api.push_message = MagicMock()  # LLMAgent uses push_message, not reply_message

    ok = await agent.handle(event, "Zeus who is boss?", line_bot_api)
    assert ok is True

    # Ensure the push message text is exactly the expected boss reply
    line_bot_api.push_message.assert_called_once()
    request = line_bot_api.push_message.call_args[0][0]
    assert request.messages[0].text == "Evan's wife..... :'D ⛈️"
