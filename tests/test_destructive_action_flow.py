"""Focused tests for destructive admin action confirmation flow."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from linebot.v3.messaging import MessagingApi

from src.agents.admin.destructive_action_flow import DestructiveActionFlow
from src.services.admin_confirmation_service import AdminConfirmationService
from src.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_confirm_logs_failed_phase_when_destructive_action_returns_failure():
    confirmation_service = AdminConfirmationService()
    confirmation_service._generate_token = lambda: "tok-failed"  # type: ignore[method-assign]
    pending = confirmation_service.create(
        action="leave",
        requested_by_user_id="U-admin",
        requested_from_chat_id="group_C123",
        payload={"kind": "group", "target_id": "C999", "chat_id": "group_C999"},
    )

    history_log = Mock()
    history_log.log = AsyncMock()

    flow = DestructiveActionFlow(
        confirmation_service=confirmation_service,
        rate_limiter=RateLimiter(),
        parse_leave_target=lambda current_chat_id, arg: ("group", "C999", None),
        push_preview=lambda api, user_id, text: True,
        execute_action=AsyncMock(return_value="❌ Failed to leave group C999."),
        agent_name="AdminAgent",
    )

    with patch("src.agents.admin.destructive_action_flow.get_history_log", return_value=history_log):
        result = await flow.confirm(
            chat_id="user_U-admin",
            user_id="U-admin",
            token=pending.token,
            line_bot_api=Mock(spec=MessagingApi),
        )

    assert result == "❌ Failed to leave group C999."
    history_log.log.assert_awaited_once()
    logged_call = history_log.log.await_args.kwargs
    assert logged_call["metadata"]["phase"] == "failed"
    assert logged_call["message"] == "Admin destructive action failed: leave"


@pytest.mark.asyncio
async def test_confirm_logs_failed_phase_when_destructive_action_raises_exception():
    confirmation_service = AdminConfirmationService()
    confirmation_service._generate_token = lambda: "tok-error"  # type: ignore[method-assign]
    pending = confirmation_service.create(
        action="leave",
        requested_by_user_id="U-admin",
        requested_from_chat_id="group_C123",
        payload={"kind": "group", "target_id": "C999", "chat_id": "group_C999"},
    )

    history_log = Mock()
    history_log.log = AsyncMock()

    flow = DestructiveActionFlow(
        confirmation_service=confirmation_service,
        rate_limiter=RateLimiter(),
        parse_leave_target=lambda current_chat_id, arg: ("group", "C999", None),
        push_preview=lambda api, user_id, text: True,
        execute_action=AsyncMock(side_effect=RuntimeError("boom")),
        agent_name="AdminAgent",
    )

    with patch("src.agents.admin.destructive_action_flow.get_history_log", return_value=history_log):
        with pytest.raises(RuntimeError, match="boom"):
            await flow.confirm(
                chat_id="user_U-admin",
                user_id="U-admin",
                token=pending.token,
                line_bot_api=Mock(spec=MessagingApi),
            )

    history_log.log.assert_awaited_once()
    logged_call = history_log.log.await_args.kwargs
    assert logged_call["metadata"]["phase"] == "failed"
    assert logged_call["metadata"]["error"] == "boom"
    assert logged_call["message"] == "Admin destructive action failed: leave"