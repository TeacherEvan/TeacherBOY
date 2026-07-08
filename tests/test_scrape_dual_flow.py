"""
Tests for the dual-source scrape flow (Messages / Image).
Verifies that the initial trigger shows a source-choice prompt and
that source-selection buttons route correctly to the right handlers.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.calendar.scrape_flow import ScrapeFlow


@pytest.fixture
def flow() -> ScrapeFlow:
    return ScrapeFlow()


# ---------------------------------------------------------------------------
# _is_scrape_source_selection helper
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("scrape messages", True),
        ("scrape image", True),
        ("scan image", True),
        ("images", True),
        ("messages", True),
        # These should NOT match as source selections
        ("scrape", False),
        ("hello", False),
        ("yes", False),
        ("done", False),
    ],
)
def test_is_scrape_source_selection(flow: ScrapeFlow, text: str, expected: bool) -> None:
    assert flow._is_scrape_source_selection(text) is expected


# ---------------------------------------------------------------------------
# handle_scrape_initial_trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_initial_trigger_sends_quick_reply_with_two_options(flow: ScrapeFlow) -> None:
    """handle_scrape_initial_trigger should send a quick reply with two source buttons."""
    mock_event = MagicMock()
    mock_event.reply_token = "tok_123"
    mock_api = MagicMock()
    mock_api.reply_message = MagicMock()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)) as mock_thread:
        result = await flow.handle_scrape_initial_trigger(mock_event, "scrape", mock_api, "chat_1", "user_1")

    assert result is True
    # Check that reply_message was called via asyncio.to_thread
    assert mock_thread.called
    call_args = mock_thread.call_args
    # Second positional arg should be a ReplyMessageRequest
    request_arg = call_args[0][1]
    assert request_arg.reply_token == "tok_123"
    msg = request_arg.messages[0]
    # The quick reply should have exactly 2 items
    assert len(msg.quick_reply.items) == 2
    labels = {item.action.label for item in msg.quick_reply.items}
    # Both "Messages" and "Images" buttons must be present
    assert any("Message" in lbl for lbl in labels), f"No Messages button found in {labels}"
    assert any("Image" in lbl for lbl in labels), f"No Image button found in {labels}"
    # Verify the button texts use the full prefixed command so should_handle() picks them up
    texts = {item.action.text for item in msg.quick_reply.items}
    assert any(
        "Ms. Green" in t or "ms. green" in t.lower() for t in texts
    ), f"Button texts must contain bot prefix; got {texts}"


# ---------------------------------------------------------------------------
# handle_scrape_image_trigger
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_image_trigger_starts_image_scrape_session(flow: ScrapeFlow) -> None:
    """handle_scrape_image_trigger should start an image analyzer session in 'scrape' mode."""
    mock_event = MagicMock()
    mock_event.reply_token = "tok_456"
    mock_api = MagicMock()

    mock_session_manager = AsyncMock()
    mock_session_manager.start_session = AsyncMock()

    with patch("asyncio.to_thread", new=AsyncMock(return_value=None)):
        with patch(
            "src.services.image_analyzer_session_manager.image_analyzer_session_manager",
            mock_session_manager,
        ):
            result = await flow.handle_scrape_image_trigger(mock_event, mock_api, "chat_1", "user_1")

    assert result is True
    mock_session_manager.start_session.assert_awaited_once_with("chat_1", "user_1", analysis_mode="scrape")


# ---------------------------------------------------------------------------
# handle_scrape_trigger still works for messages path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_messages_path_falls_through_to_existing_handler(flow: ScrapeFlow) -> None:
    """When the user selects 'scrape messages', handle_scrape_trigger must still be callable."""
    mock_event = MagicMock()
    mock_event.reply_token = "tok_789"
    mock_event.source = None
    mock_api = MagicMock()

    with patch.object(flow, "handle_scrape_trigger", new=AsyncMock(return_value=True)) as mock_handle:
        # Simulate what calendar_agent now does when "scrape messages" is received
        normalized = flow._normalize_followup_text("scrape messages")
        is_messages = normalized in {"scrape messages", "messages"}

        if is_messages:
            result = await mock_handle(mock_event, "scrape messages", mock_api, "chat_1", "user_1")
        else:
            result = False

    assert result is True
    mock_handle.assert_awaited_once()
