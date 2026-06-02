from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.agents.llm_agent import LLMAgent
from src.services.bot_identity_service import BotIdentityService


def test_identity_service_loads_defaults_when_state_missing(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=[
            "ms. green",
            "ms green",
        ],
    )

    profile = service.get_profile()

    assert profile.display_name == "Ms. Green"
    assert "ms. green" in profile.aliases
    assert "ms green" in profile.aliases


def test_identity_service_preserves_old_name_as_alias_on_rename(
    tmp_path: Path,
):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green"],
    )

    updated = service.update_identity("Ms. Green", ["ms green"])

    assert updated.display_name == "Ms. Green"
    assert "ms. green" in updated.aliases
    assert "ms green" in updated.aliases


def test_split_command_prefix_supports_ms_green(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green", "ms green", "green"],
    )

    prefix, rest = service.split_command_prefix("Ms. Green search python")

    assert prefix == "ms. green"
    assert rest == "search python"


def test_split_command_prefix_rejects_legacy_zeus_after_cutover(tmp_path: Path):
    service = BotIdentityService(
        storage_path=tmp_path / "identity.json",
        default_name="Ms. Green",
        default_aliases=["ms. green", "ms green", "green"],
    )

    prefix, rest = service.split_command_prefix("Zeus search python")

    assert prefix is None
    assert rest == "Zeus search python"


def test_llm_agent_extracts_identity_queries_with_and_without_prefix() -> None:
    agent = LLMAgent()

    assert agent._extract_identity_query("Who are you?") == "Who are you?"
    assert (
        agent._extract_identity_query("Ms. Green what is your name?")
        == "what is your name?"
    )
    assert agent._extract_identity_query("Ms. Green search python") is None


@pytest.mark.asyncio
async def test_llm_agent_replies_with_deterministic_identity_response() -> None:
    agent = LLMAgent()
    event = MagicMock()
    event.source = MagicMock()
    event.source.type = "user"
    event.source.user_id = "U1"
    event.reply_token = "reply-token"
    line_bot_api = MagicMock()

    agent._send_reply = AsyncMock(return_value=None)

    handled = await agent.handle(event, "Who are you?", line_bot_api)

    assert handled is True
    agent._send_reply.assert_awaited_once_with(
        event,
        line_bot_api,
        "I am Ms. Green. I speak with calm judgment, gentle strength, and patient clarity. "
        "I am here to answer carefully and without needless ornament.",
    )
