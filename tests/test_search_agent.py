import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from linebot.v3.webhooks import MessageEvent, TextMessageContent, Source
from linebot.v3.messaging import MessagingApi

from src.agents.search_agent import SearchAgent
from src.services.brave_search_service import BraveSearchService
from src.services.privilege_service import privilege_service

@pytest.fixture
def mock_brave_service():
    service = MagicMock(spec=BraveSearchService)
    service.is_configured.return_value = True
    service.search = AsyncMock(return_value=[
        {"title": "Python Tutorial", "url": "https://python.org", "description": "Learn Python"}
    ])
    return service

@pytest.fixture
def search_agent(mock_brave_service):
    with patch('src.agents.search_agent.brave_search_service', mock_brave_service):
        # Instantiate inside the patch context so SearchAgent.__init__ assigns
        # the patched brave_search_service to self.search_service.
        agent = SearchAgent()
        assert agent.search_service is mock_brave_service
        return agent

@pytest.fixture
def mock_line_bot_api():
    return MagicMock(spec=MessagingApi)

@pytest.fixture
def message_event():
    event = MagicMock(spec=MessageEvent)
    event.source = MagicMock(spec=Source)
    event.source.type = "user"
    event.source.user_id = "user123"
    event.reply_token = "reply_token"
    event.message = MagicMock(spec=TextMessageContent)
    return event


@pytest.fixture
def group_message_event():
    event = MagicMock(spec=MessageEvent)
    event.source = MagicMock(spec=Source)
    event.source.type = "group"
    event.source.group_id = "group123"
    event.source.user_id = "user123"
    event.reply_token = "reply_token"
    event.message = MagicMock(spec=TextMessageContent)
    return event

@pytest.mark.asyncio
async def test_should_handle_search_triggers(search_agent, message_event):
    triggers = [
        "Zeus search python",
        "zeus search python",
        "Zeus   search   python tutorial",
        "KPS search python",
    ]

    for text in triggers:
        assert await search_agent.should_handle(message_event, text) is True


@pytest.mark.asyncio
async def test_search_agent_handles_runtime_alias_prefix(search_agent, group_message_event):
    assert await search_agent.should_handle(group_message_event, "KPS search python") is True


@pytest.mark.asyncio
async def test_should_not_handle_search_in_group_for_non_admin(
    search_agent, group_message_event
):
    assert await search_agent.should_handle(group_message_event, "Zeus search python") is True


@pytest.mark.asyncio
async def test_should_handle_search_in_group_for_admin(search_agent, group_message_event):
    # Reset and configure privilege_service to treat user123 as admin
    privilege_service._reset_for_testing()
    
    with patch("src.config.settings") as mock_settings:
        mock_settings.get_admin_user_ids.return_value = ["user123"]
        mock_settings.get_moderator_user_ids.return_value = []
        
        assert (
            await search_agent.should_handle(group_message_event, "Zeus search python")
            is True
        )
    
    # Reset after test
    privilege_service._reset_for_testing()


@pytest.mark.asyncio
async def test_should_not_handle_search_in_group_when_allowlist_denies(
    search_agent, group_message_event, monkeypatch
):
    # Switch to allowlist mode and do not include this group.
    from src.agents import search_agent as search_agent_module

    monkeypatch.setattr(
        search_agent_module.settings, "zeus_group_access_mode", "allowlist", raising=False
    )
    monkeypatch.setattr(
        search_agent_module.settings,
        "zeus_allowed_group_ids",
        "some_other_group",
        raising=False,
    )
    assert await search_agent.should_handle(group_message_event, "Zeus search python") is False

@pytest.mark.asyncio
async def test_should_not_handle_other_text(search_agent, message_event):
    non_triggers = ["hello", "translate this", "what is python"]
    
    for text in non_triggers:
        assert await search_agent.should_handle(message_event, text) is False

@pytest.mark.asyncio
async def test_handle_search_command(search_agent, mock_brave_service, mock_line_bot_api, message_event):
    text = "Zeus search python tutorial"
    
    result = await search_agent.handle(message_event, text, mock_line_bot_api)
    
    assert result is True
    mock_brave_service.search.assert_called_once_with("python tutorial", count=5)
    mock_line_bot_api.reply_message.assert_called_once()

    call_args = mock_line_bot_api.reply_message.call_args
    request = call_args[0][0]
    assert "Python Tutorial" in request.messages[0].text
    assert "https://python.org" in request.messages[0].text

@pytest.mark.asyncio
async def test_handle_search_error(search_agent, mock_brave_service, mock_line_bot_api, message_event):
    text = "Zeus search error"
    mock_brave_service.search.side_effect = Exception("API Error")
    
    result = await search_agent.handle(message_event, text, mock_line_bot_api)
    
    assert result is True
    mock_line_bot_api.reply_message.assert_called_once() # Should send error message

    call_args = mock_line_bot_api.reply_message.call_args
    request = call_args[0][0]
    assert "❌ Search error" in request.messages[0].text
