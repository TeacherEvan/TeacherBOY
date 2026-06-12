from unittest.mock import Mock, patch

import pytest
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhooks import MessageEvent

from src.agents.help_agent import HelpAgent


@pytest.fixture
def line_bot_api():
    api = Mock(spec=MessagingApi)
    api.reply_message = Mock()
    return api


def _make_private_event(user_id: str = "UUSER"):
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.type = "user"
    event.source.user_id = user_id
    event.source.group_id = None
    event.source.room_id = None
    event.reply_token = "reply_token"
    return event


def _make_group_event(user_id: str = "UUSER", group_id: str = "G123"):
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.type = "group"
    event.source.user_id = user_id
    event.source.group_id = group_id
    event.source.room_id = None
    event.reply_token = "reply_token"
    return event


def _make_room_event(user_id: str = "UUSER", room_id: str = "R123"):
    event = Mock(spec=MessageEvent)
    event.source = Mock()
    event.source.type = "room"
    event.source.user_id = user_id
    event.source.group_id = None
    event.source.room_id = room_id
    event.reply_token = "reply_token"
    return event


def test_command_categories_use_ms_green_examples():
    agent = HelpAgent()

    categories = agent._get_command_categories(
        is_admin=False,
        chat_type="private chat",
        zeus_available=True,
        search_available=True,
    )

    joined = " ".join(
        f"{command['command']} {' '.join(command['examples'])} {command['description']}"
        for commands in categories.values()
        for command in commands
        if command["available"]
    )

    assert "Ms. Green" in joined
    assert "Zeus" not in joined


def test_help_command_accepts_topic_variants():
    agent = HelpAgent()

    assert agent._is_help_command("help calendar") is True
    assert agent._is_help_command("/help admin") is True
    assert agent._is_help_command("help") is True
    assert agent._is_help_command("not help") is False


def test_help_menu_splits_into_three_cards():
    agent = HelpAgent()
    with patch("src.agents.help_agent.settings") as mock_settings:
        mock_settings.is_calendar_configured.return_value = True
        mock_settings.is_profiler_configured.return_value = True
        mock_settings.is_github_models_configured.return_value = True
        mock_settings.is_brave_search_configured.return_value = True

        categories = agent._get_command_categories(
            is_admin=False,
            chat_type="private chat",
            zeus_available=True,
            search_available=True,
        )
        tips = agent._get_adaptive_tips(is_admin=False, chat_type="private chat")

        cards = agent._create_help_cards(categories, tips, "private chat")

    assert len(cards) == 3
    assert cards[0].quick_reply is not None
    assert cards[1].quick_reply is None
    assert cards[2].quick_reply is None

    payloads = [card.dict(by_alias=True) for card in cards]
    headers = [item["text"] for payload in payloads for item in _walk_text_items(payload)]
    assert any("Part 1/3" in text for text in headers)
    assert any("Part 2/3" in text for text in headers)
    assert any("Part 3/3" in text for text in headers)
    assert any("CORE COMMANDS" in text for text in headers)
    assert any("CALENDAR & REMINDERS" in text for text in headers)
    assert any("IMAGE ANALYSIS" in text for text in headers)


def test_topic_help_uses_one_card():
    agent = HelpAgent()
    categories = agent._get_command_categories(
        is_admin=False,
        chat_type="private chat",
        zeus_available=True,
        search_available=True,
    )
    tips = agent._get_adaptive_tips(is_admin=False, chat_type="private chat")

    cards = agent._create_help_cards(categories, tips, "private chat", topic="Calendar & Reminders")

    assert len(cards) == 1
    payload = cards[0].dict(by_alias=True)
    texts = [item["text"] for item in _walk_text_items(payload)]
    assert any("Focused help: Calendar & Reminders" in text for text in texts)
    assert any("CALENDAR & REMINDERS" in text for text in texts)
    assert not any("IMAGE ANALYSIS" in text for text in texts)


def _walk_text_items(node):
    if isinstance(node, dict):
        if node.get("type") == "text" and "text" in node:
            yield node
        for value in node.values():
            yield from _walk_text_items(value)
    elif isinstance(node, list):
        for item in node:
            yield from _walk_text_items(item)


def test_help_topic_is_extracted():
    agent = HelpAgent()

    assert agent._extract_help_topic("help calendar") == "calendar"
    assert agent._extract_help_topic("/help admin") == "admin"
    assert agent._extract_help_topic("help") is None


def test_adaptive_tips_use_ai_translation_and_ms_green():
    agent = HelpAgent()

    tips = agent._get_adaptive_tips(is_admin=False, chat_type="private chat")
    joined = " ".join(tips)

    assert "Ms. Green" in joined
    assert "Google Translate" not in joined
    assert "LibreTranslate" not in joined
    assert "Zeus" not in joined


@pytest.mark.asyncio
async def test_help_should_not_handle_non_privileged_group_user():
    agent = HelpAgent()
    event = _make_group_event()

    with patch("src.agents.help_agent.privilege_service.is_privileged", return_value=False):
        assert await agent.should_handle(event, "help") is False


@pytest.mark.asyncio
async def test_help_should_not_handle_non_privileged_room_user():
    agent = HelpAgent()
    event = _make_room_event()

    with patch("src.agents.help_agent.privilege_service.is_privileged", return_value=False):
        assert await agent.should_handle(event, "help") is False


@pytest.mark.asyncio
async def test_help_handle_sends_all_cards(line_bot_api):
    agent = HelpAgent()
    event = _make_private_event()

    with patch("src.config.settings") as mock_settings:
        mock_settings.is_calendar_configured.return_value = True
        mock_settings.is_profiler_configured.return_value = True
        mock_settings.is_github_models_configured.return_value = True
        mock_settings.is_brave_search_configured.return_value = True
        mock_settings.is_zeus_allowed_in_group.return_value = True

        handled = await agent.handle(event, "help", line_bot_api)

    assert handled is True
    assert line_bot_api.reply_message.called
    msg = line_bot_api.reply_message.call_args[0][0].messages[0]
    payload = msg.contents.to_dict()
    assert payload["type"] == "carousel"
    assert len(payload["contents"]) == 3


def test_help_flex_message_adds_quick_reply_shortcuts():
    agent = HelpAgent()
    categories = agent._get_command_categories(
        is_admin=False,
        chat_type="private chat",
        zeus_available=True,
        search_available=True,
    )
    tips = agent._get_adaptive_tips(is_admin=False, chat_type="private chat")

    message = agent._create_help_flex_message(categories, tips, "private chat")

    assert message.quick_reply is not None
    labels = [item.action.label for item in message.quick_reply.items]
    assert any("Calendar" in label for label in labels)
    assert any("Admin" in label for label in labels)
    assert any("Search" in label for label in labels)
    assert any("News" in label for label in labels)
    assert any("Image" in label for label in labels)


def test_help_includes_document_memory_category():
    agent = HelpAgent()
    with patch("src.agents.help_agent.settings") as mock_settings:
        mock_settings.is_calendar_configured.return_value = True
        mock_settings.is_profiler_configured.return_value = True
        mock_settings.is_github_models_configured.return_value = True
        mock_settings.is_brave_search_configured.return_value = True
        mock_settings.document_memory_enabled = True

        categories = agent._get_command_categories(
            is_admin=False,
            chat_type="private chat",
            zeus_available=True,
            search_available=True,
        )

    # Should have Document Memory category
    assert "Document Memory" in categories
    doc_commands = categories["Document Memory"]
    assert any(cmd["command"] == "Ms. Green doc" for cmd in doc_commands)
    assert any(cmd["command"] == "Ms. Green docs" for cmd in doc_commands)


def test_help_document_memory_topic_alias():
    agent = HelpAgent()
    categories = {"Document Memory": [{"command": "Ms. Green doc", "available": True}]}
    assert agent._resolve_help_topic("doc", categories) == "Document Memory"
    assert agent._resolve_help_topic("docs", categories) == "Document Memory"
    assert agent._resolve_help_topic("document", categories) == "Document Memory"
