import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.special_news_agent import SpecialNewsAgent
from src.services.special_news_service import SpecialNewsService
from linebot.v3.messaging import FlexMessage


@pytest.fixture
def mock_http_client():
    return AsyncMock()


@pytest.fixture
def special_news_service(mock_http_client):
    return SpecialNewsService(http_client=mock_http_client)


@pytest.fixture
def special_news_agent(special_news_service):
    return SpecialNewsAgent(news_service=special_news_service)


@pytest.fixture
def mock_event_private():
    event = MagicMock()
    event.source = MagicMock()
    event.source.user_id = "U_test_private"
    # No group_id/room_id -> private chat
    event.reply_token = "reply_token_private"
    return event


@pytest.fixture
def mock_event_group():
    event = MagicMock()
    event.source = MagicMock()
    event.source.user_id = "U_test_group"
    event.source.group_id = "C_test_group"
    event.reply_token = "reply_token_group"
    return event


@pytest.mark.asyncio
async def test_should_handle_only_special_command(special_news_agent, mock_event_private):
    assert await special_news_agent.should_handle(mock_event_private, "/special news") is True
    assert await special_news_agent.should_handle(mock_event_private, "/special  news") is True
    assert await special_news_agent.should_handle(mock_event_private, "special news") is False


@pytest.mark.asyncio
async def test_group_chat_refused(special_news_agent, mock_event_group):
    mock_line_bot_api = MagicMock()
    mock_line_bot_api.reply_message = MagicMock()

    handled = await special_news_agent.handle(mock_event_group, "/special news", mock_line_bot_api)
    assert handled is True
    mock_line_bot_api.reply_message.assert_called_once()

    msg_text = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
    assert "DM" in msg_text or "dm" in msg_text.lower()


@pytest.mark.asyncio
async def test_private_non_friend_denied(special_news_agent, mock_event_private):
    mock_line_bot_api = MagicMock()
    mock_line_bot_api.reply_message = MagicMock()

    # Non-friend: get_profile raises
    mock_line_bot_api.get_profile = MagicMock(side_effect=Exception("not friend"))

    handled = await special_news_agent.handle(mock_event_private, "/special news", mock_line_bot_api)
    assert handled is True

    msg_text = mock_line_bot_api.reply_message.call_args[0][0].messages[0].text
    assert "denied" in msg_text.lower()


@pytest.mark.asyncio
async def test_private_friend_success_returns_flex_carousel(special_news_agent, mock_event_private):
    mock_line_bot_api = MagicMock()
    mock_line_bot_api.reply_message = MagicMock()
    mock_line_bot_api.get_profile = MagicMock(return_value={"userId": "U_test_private"})

    # Stub service methods to avoid network
    special_news_agent._service.fetch_rss_items = AsyncMock(side_effect=[
        [{"title": f"T{i}", "url": f"https://t/{i}"} for i in range(1, 6)],
        [{"title": f"S{i}", "url": f"https://s/{i}"} for i in range(1, 6)],
        [{"title": f"W{i}", "url": f"https://w/{i}"} for i in range(1, 6)],
    ])

    handled = await special_news_agent.handle(mock_event_private, "/special news", mock_line_bot_api)
    assert handled is True

    msg = mock_line_bot_api.reply_message.call_args[0][0].messages[0]
    assert isinstance(msg, FlexMessage)

    payload = msg.contents.to_dict()
    assert payload.get("type") == "carousel"
    bubbles = payload.get("contents", [])
    assert len(bubbles) == 3

    titles = [b["header"]["contents"][0]["text"] for b in bubbles]
    assert any("Tourism" in t for t in titles)
    assert any("Sports" in t for t in titles)
    assert any("International" in t for t in titles)

    # Each bubble should contain exactly 5 items (numbered 1-5).
    for bubble in bubbles:
        body_items = bubble["body"]["contents"]
        assert len(body_items) == 5
        
        for i, item in enumerate(body_items, start=1):
            title_text = item["contents"][0]["text"]
            assert title_text.startswith(f"{i}."), f"Expected item {i} to start with '{i}.', got '{title_text}'"
