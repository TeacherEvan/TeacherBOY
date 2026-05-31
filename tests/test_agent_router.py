from unittest.mock import AsyncMock, MagicMock

import pytest
from linebot.v3.webhooks import TextMessageContent

from src.agents.agent_router import AgentRouter, RouteResult


@pytest.mark.asyncio
async def test_route_message_returns_selected_agent_metadata() -> None:
    router = AgentRouter()
    agent = MagicMock()
    agent.name = "HelpAgent"
    agent.enabled = True
    agent.get_priority.return_value = 5
    agent.should_handle = AsyncMock(return_value=True)
    agent.handle = AsyncMock(return_value=True)
    router.register_agent(agent)

    event = MagicMock()
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "help"
    event.source = MagicMock()
    event.source.type = "user"
    event.source.user_id = "U123"
    event.source.group_id = None
    event.source.room_id = None

    result = await router.route_message(event, MagicMock())

    assert isinstance(result, RouteResult)
    assert result.handled is True
    assert result.agent_name == "HelpAgent"
    assert result.message_type == "text"
    assert bool(result) is True


@pytest.mark.asyncio
async def test_route_message_returns_unhandled_result_for_unsupported_message() -> None:
    router = AgentRouter()
    event = MagicMock()
    event.message = object()

    result = await router.route_message(event, MagicMock())

    assert result == RouteResult(handled=False, agent_name=None, message_type=None)
    assert bool(result) is False


@pytest.mark.asyncio
async def test_route_message_returns_unhandled_result_for_supported_text_when_no_agent_matches() -> None:
    router = AgentRouter()
    agent = MagicMock()
    agent.name = "HelpAgent"
    agent.enabled = True
    agent.get_priority.return_value = 5
    agent.should_handle = AsyncMock(return_value=False)
    agent.handle = AsyncMock(return_value=True)
    router.register_agent(agent)

    event = MagicMock()
    event.message = MagicMock(spec=TextMessageContent)
    event.message.text = "help"
    event.source = MagicMock()
    event.source.type = "user"
    event.source.user_id = "U123"
    event.source.group_id = None
    event.source.room_id = None

    result = await router.route_message(event, MagicMock())

    assert result == RouteResult(
        handled=False,
        agent_name=None,
        message_type="text",
    )
    assert bool(result) is False
    agent.should_handle.assert_awaited_once_with(event, "help")
    agent.handle.assert_not_awaited()