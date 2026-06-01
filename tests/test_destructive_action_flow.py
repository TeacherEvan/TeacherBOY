"""Focused tests for destructive admin action confirmation flow."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from linebot.v3.messaging import MessagingApi

from src.agents.admin.destructive_action_flow import DestructiveActionFlow
from src.services.admin_confirmation_service import AdminConfirmationService
from src.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_request_push_failure_does_not_arm_pending_confirmation():
    confirmation_service = AdminConfirmationService()
    confirmation_service._generate_token = lambda: "tok-push-fail"  # type: ignore[method-assign]
    rate_limiter = RateLimiter()

    flow = DestructiveActionFlow(
        confirmation_service=confirmation_service,
        rate_limiter=rate_limiter,
        parse_leave_target=lambda current_chat_id, arg: ("group", "C999", None),
        push_preview=lambda api, user_id, text: False,
        execute_action=AsyncMock(),
        agent_name="AdminAgent",
    )

    result = await flow.request(
        action="purge",
        current_chat_id="group_C123",
        user_id="U-admin",
        arg=None,
        line_bot_api=Mock(spec=MessagingApi),
    )

    assert "private preview" in result.lower()
    assert confirmation_service.count_pending() == 0
    assert rate_limiter._admin_destructive_targets == {}


@pytest.mark.asyncio
async def test_request_rejects_invalid_explicit_reset_target():
    confirmation_service = AdminConfirmationService()

    flow = DestructiveActionFlow(
        confirmation_service=confirmation_service,
        rate_limiter=RateLimiter(),
        parse_leave_target=lambda current_chat_id, arg: (None, None, "invalid"),
        push_preview=lambda api, user_id, text: True,
        execute_action=AsyncMock(),
        agent_name="AdminAgent",
    )

    result = await flow.request(
        action="reset",
        current_chat_id="group_C123",
        user_id="U-admin",
        arg="C999",
        line_bot_api=Mock(spec=MessagingApi),
    )

    assert result == "❌ Invalid target. Use user_<id>, group_<id>, or room_<id>."
    assert confirmation_service.count_pending() == 0


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