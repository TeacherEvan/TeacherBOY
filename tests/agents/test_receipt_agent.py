"""Tests for ReceiptAgent — additive receipt scanning agent."""

from unittest.mock import MagicMock, patch

import pytest
from linebot.v3.webhooks import ImageMessageContent, MessageEvent, TextMessageContent

from src.agents.image_analyzer_agent import ImageAnalyzerAgent
from src.agents.profiler_agent import ProfilerAgent
from src.agents.receipt_agent import ReceiptAgent
from src.services.image_analyzer_session_manager import image_analyzer_session_manager
from src.services.profiler_session_manager import profiler_session_manager
from src.services.receipt_bridge import gemini_text_to_ocr_payload


@pytest.mark.asyncio
async def test_receipt_agent_priority():
    agent = ReceiptAgent()
    assert agent.get_priority() == 8


@pytest.mark.asyncio
async def test_receipt_agent_should_handle_bare_image_no_sessions():
    """Should handle bare image when no other agent is waiting."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    _chat_id = "test_group"
    _user_id = "test_user"

    # Mock no active sessions
    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_has_vision_provider", return_value=True):
                with patch.object(agent, "_is_user_linked", return_value=True):
                    with patch.object(agent, "_is_receipt_enabled", return_value=True):
                        result = await agent.should_handle(event, "")
                        assert result is True


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_when_image_analyzer_waiting():
    """Should NOT handle when image_analyzer is waiting for image (priority 7 wins)."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=True):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=True):
                    result = await agent.should_handle(event, "")
                    assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_when_profiler_waiting():
    """Should NOT handle when profiler is waiting for image (priority 7 wins)."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=True):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=True):
                    result = await agent.should_handle(event, "")
                    assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_text_only():
    """Should not handle text-only messages."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=TextMessageContent)
    event.message.type = "text"
    event.message.text = "hello"

    result = await agent.should_handle(event, "hello")
    assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_unlinked_user():
    """Should not handle if user not linked to Budget Boss."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=False):
                result = await agent.should_handle(event, "")
                assert result is False


@pytest.mark.asyncio
async def test_receipt_agent_should_not_handle_disabled():
    """Should not handle if receipt feature disabled."""
    agent = ReceiptAgent()

    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.source = MagicMock()
    event.source.user_id = "test_user"
    event.source.group_id = "test_group"

    with patch.object(image_analyzer_session_manager, "is_waiting_for_image", return_value=False):
        with patch.object(profiler_session_manager, "is_waiting_for_image", return_value=False):
            with patch.object(agent, "_is_user_linked", return_value=True):
                with patch.object(agent, "_is_receipt_enabled", return_value=False):
                    result = await agent.should_handle(event, "")
                    assert result is False


# ---------------------------------------------------------------------------
# Anti-cannibalisation: session-key contract with the priority-7 image agents.
#
# The tests above patch the session managers wholesale, so they prove only that
# `should_handle` reads the boolean it is handed. They cannot catch a *key*
# mismatch. The tests below drive the real session managers and therefore guard
# the regression where ReceiptAgent._get_chat_id returned a bare `group_id` /
# `user_id` while ImageAnalyzerAgent and ProfilerAgent store their sessions
# under `group_<id>` / `room_<id>` / `user_<id>`. Every gate lookup missed, and
# ReceiptAgent would claim a photo the analyzer was waiting for on the router's
# fallthrough path. Fixed by aligning _get_chat_id with the priority-7 agents.
# ---------------------------------------------------------------------------


class _Source:
    """Minimal LINE event source; MagicMock auto-creates group_id/room_id."""

    def __init__(self, user_id="U_alice", group_id=None, room_id=None):
        self.user_id = user_id
        self.group_id = group_id
        self.room_id = room_id


def _image_event(source):
    event = MagicMock(spec=MessageEvent)
    event.message = MagicMock(spec=ImageMessageContent)
    event.message.type = "image"
    event.message.id = "msg_1"
    event.source = source
    return event


@pytest.mark.parametrize(
    "source",
    [
        _Source(),
        _Source(group_id="C_group1"),
        _Source(room_id="R_room1"),
    ],
    ids=["direct", "group", "room"],
)
def test_receipt_chat_id_matches_priority_seven_agents(source):
    """The session key must be identical across all three image-claiming agents."""
    event = _image_event(source)

    receipt_key = ReceiptAgent()._get_chat_id(event)
    assert receipt_key == ImageAnalyzerAgent()._get_chat_id(event)
    assert receipt_key == ProfilerAgent()._get_chat_id(event)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "source",
    [_Source(), _Source(group_id="C_group1")],
    ids=["direct", "group"],
)
async def test_receipt_agent_yields_to_real_image_analyzer_session(source):
    """A real analyzer session — not a patched boolean — must block the receipt agent."""
    agent = ReceiptAgent()
    event = _image_event(source)
    analyzer_key = ImageAnalyzerAgent()._get_chat_id(event)

    await image_analyzer_session_manager.start_session(analyzer_key, user_id=source.user_id)
    try:
        # The gate ReceiptAgent actually performs, with its own key.
        assert await image_analyzer_session_manager.is_waiting_for_image(agent._get_chat_id(event), source.user_id)

        with patch.object(agent, "_has_vision_provider", return_value=True):
            assert await agent.should_handle(event, "") is False
    finally:
        await image_analyzer_session_manager.clear_session(analyzer_key)


@pytest.mark.asyncio
async def test_receipt_agent_yields_to_real_profiler_session():
    """A real profiler session must block the receipt agent."""
    agent = ReceiptAgent()
    source = _Source(group_id="C_group2")
    event = _image_event(source)
    profiler_key = ProfilerAgent()._get_chat_id(event)

    profiler_session_manager.request_profiling(profiler_key, source.user_id)
    try:
        assert profiler_session_manager.is_waiting_for_image(agent._get_chat_id(event), source.user_id)

        with patch.object(agent, "_has_vision_provider", return_value=True):
            assert await agent.should_handle(event, "") is False
    finally:
        profiler_session_manager.clear_session(profiler_key)


@pytest.mark.asyncio
async def test_receipt_agent_still_claims_image_with_no_live_session():
    """With no analyzer/profiler session open, the receipt agent keeps the photo."""
    agent = ReceiptAgent()
    event = _image_event(_Source(user_id="U_nobody_waiting"))

    with patch.object(agent, "_has_vision_provider", return_value=True):
        with patch.object(agent, "_is_receipt_enabled", return_value=True):
            assert await agent.should_handle(event, "") is True


def test_ocr_payload_declares_provenance_and_nullable_currency_hint():
    """The adapter's shape is the receiver's contract.

    `currencyHint` is emitted as Python None on every scan, so the Convex zod
    schema must accept null (`.nullish()`), not merely omission. Guards the
    regression where `.optional()` 400'd every bot receipt in production.
    """
    payload = gemini_text_to_ocr_payload("TOKO SEJAHTERA\nTOTAL 91000", "ID")

    assert payload["currencyHint"] is None
    assert payload["countryHint"] == "ID"
    assert payload["engine"] == "gemini-vision@1"
    assert len(payload["lines"]) == 2
    for line in payload["lines"]:
        assert set(line) == {"text", "conf", "y", "words"}
        assert isinstance(line["text"], str) and line["text"]
