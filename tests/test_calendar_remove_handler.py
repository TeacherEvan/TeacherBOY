from unittest.mock import AsyncMock, MagicMock
from datetime import datetime, timedelta

import pytest

from src.agents.calendar.handlers.remove_handler import RemoveHandler
from src.services.calendar_session_manager import calendar_session_manager


@pytest.fixture
def remove_handler():
    return RemoveHandler()


@pytest.fixture
def mock_event():
    event = MagicMock()
    event.source = MagicMock()
    event.source.user_id = "U_OWNER"
    event.source.group_id = "G123"
    event.source.room_id = None
    event.reply_token = "reply-token"
    return event


@pytest.fixture
def mock_line_api():
    return MagicMock()


@pytest.fixture(autouse=True)
def cleanup_sessions():
    calendar_session_manager.end_session("group_G123")
    yield
    calendar_session_manager.end_session("group_G123")


class TestRemoveHandler:
    @pytest.mark.asyncio
    async def test_non_owner_cannot_restart_active_remove_session(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_STARTER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        remove_handler._remove_flow.send_message = AsyncMock()
        mock_event.source.user_id = "U_OTHER"

        handled = await remove_handler.handle(
            mock_event,
            "Ms. Green remove event",
            mock_line_api,
            "group_G123",
            "U_OTHER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "only the person who started this removal flow" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_cancel_during_selection_ends_session(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        remove_handler._remove_flow.send_message = AsyncMock()

        handled = await remove_handler.handle(
            mock_event,
            "cancel",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None
        assert "no events were removed" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_non_owner_cannot_confirm_delete_preview(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_STARTER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        preview = calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()
        mock_event.source.user_id = "U_OTHER"

        assert preview is not None
        handled = await remove_handler.handle(
            mock_event,
            f"delete {preview['code']}",
            mock_line_api,
            "group_G123",
            "U_OTHER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "only the person who started this removal flow" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_registry_dispatches_hardened_remove_handler(
        self,
        mock_event,
        mock_line_api,
    ):
        from src.agents.calendar.handler_registry import HandlerRegistry

        registry = HandlerRegistry()
        handler = registry.get_handler("remove")

        assert handler is not None
        assert await handler.can_handle(mock_event, "Ms. Green remove event") is True

        calendar_service = MagicMock()
        service_event = MagicMock()
        service_event.event_id = "evt-1"
        service_event.title = "Math Quiz"
        service_event.user_id = "U_OWNER"
        service_event.event_date.strftime.return_value = "Jun 10"
        calendar_service.get_chat_events_async = AsyncMock(return_value=[service_event])

        handled = await handler.handle(
            mock_event,
            "Ms. Green remove event",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": calendar_service},
        )

        assert handled is True

    @pytest.mark.asyncio
    async def test_mixed_remove_selection_is_rejected_through_handler_routing(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )
        remove_handler._remove_flow.send_message = AsyncMock()

        can_handle = await remove_handler.can_handle(mock_event, "1,done")

        assert can_handle is True

        handled = await remove_handler.handle(
            mock_event,
            "1,done",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "invalid selection" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_unrelated_comma_text_is_not_hijacked_through_handler_routing(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )

        can_handle = await remove_handler.can_handle(mock_event, "1,000 students attended")

        assert can_handle is False

        handled = await remove_handler.handle(
            mock_event,
            "1,000 students attended",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is False

    @pytest.mark.asyncio
    async def test_keyword_prefixed_mixed_remove_input_is_rejected_through_handler_routing(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [
                {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
                {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
            ],
        )
        remove_handler._remove_flow.send_message = AsyncMock()

        can_handle = await remove_handler.can_handle(mock_event, "1, done please")

        assert can_handle is True

        handled = await remove_handler.handle(
            mock_event,
            "1, done please",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "invalid selection" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_stale_delete_code_is_rejected_without_live_session(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("group_G123") is None

        remove_handler._remove_flow.send_message = AsyncMock()

        can_handle = await remove_handler.can_handle(mock_event, "delete deadbeef")

        assert can_handle is True

        handled = await remove_handler.handle(
            mock_event,
            "delete deadbeef",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "stale or expired" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_delete_code_without_remove_context_falls_through_handler(self, remove_handler, mock_event):
        can_handle = await remove_handler.can_handle(mock_event, "delete deadbeef")

        assert can_handle is False

    @pytest.mark.asyncio
    async def test_stale_remove_selection_followup_is_rejected_without_live_session(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("group_G123") is None

        remove_handler._remove_flow.send_message = AsyncMock()

        can_handle = await remove_handler.can_handle(mock_event, "done")

        assert can_handle is True

        handled = await remove_handler.handle(
            mock_event,
            "done",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "stale or expired" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_done_without_remove_context_falls_through_handler(self, remove_handler, mock_event):
        can_handle = await remove_handler.can_handle(mock_event, "done")

        assert can_handle is False

    @pytest.mark.asyncio
    async def test_recent_remove_expiry_does_not_hijack_other_user_through_handler(
        self,
        remove_handler,
        mock_event,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("group_G123") is None

        mock_event.source.user_id = "U_OTHER"

        can_handle = await remove_handler.can_handle(mock_event, "done")

        assert can_handle is False

    @pytest.mark.asyncio
    async def test_cancel_does_not_get_hijacked_after_recent_remove_expiry_through_handler(
        self,
        remove_handler,
        mock_event,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("group_G123") is None

        can_handle = await remove_handler.can_handle(mock_event, "cancel")

        assert can_handle is False

    @pytest.mark.asyncio
    async def test_preview_done_gets_explicit_delete_or_cancel_guidance_through_handler(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()

        can_handle = await remove_handler.can_handle(mock_event, "done")

        assert can_handle is True

        handled = await remove_handler.handle(
            mock_event,
            "done",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        reply_text = remove_handler._remove_flow.send_message.await_args.args[2].lower()
        assert "delete <code>" in reply_text
        assert "cancel" in reply_text

    @pytest.mark.asyncio
    async def test_preview_cancel_alias_ends_remove_flow_through_handler(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()

        handled = await remove_handler.handle(
            mock_event,
            "quit",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "no events were removed" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_done_after_remove_cancel_gets_stale_response_through_handler(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()

        handled = await remove_handler.handle(
            mock_event,
            "quit",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None

        remove_handler._remove_flow.send_message.reset_mock()

        can_handle = await remove_handler.can_handle(mock_event, "done")

        assert can_handle is True

        handled = await remove_handler.handle(
            mock_event,
            "done",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        remove_handler._remove_flow.send_message.assert_awaited_once()
        assert "stale or expired" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_all_and_none_after_remove_cancel_get_stale_response_through_handler(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()

        handled = await remove_handler.handle(
            mock_event,
            "quit",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None

        for text in ("all", "none"):
            remove_handler._remove_flow.send_message.reset_mock()
            can_handle = await remove_handler.can_handle(mock_event, text)
            assert can_handle is True

            handled = await remove_handler.handle(
                mock_event,
                text,
                mock_line_api,
                "group_G123",
                "U_OWNER",
                {"calendar_service": MagicMock()},
            )

            assert handled is True
            remove_handler._remove_flow.send_message.assert_awaited_once()
            assert "stale or expired" in remove_handler._remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_plain_yes_after_remove_cancel_falls_through_handler(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()

        handled = await remove_handler.handle(
            mock_event,
            "quit",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None

        for text in ("yes", "no", "ใช่", "ไม่"):
            can_handle = await remove_handler.can_handle(mock_event, text)
            assert can_handle is False

    @pytest.mark.asyncio
    async def test_plain_numeric_reply_after_remove_cancel_falls_through_handler(
        self,
        remove_handler,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow(
            "group_G123",
            "U_OWNER",
            [{"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"}],
        )
        calendar_session_manager.apply_remove_selection("group_G123", "1")
        calendar_session_manager.finalize_remove_selection("group_G123")
        remove_handler._remove_flow.send_message = AsyncMock()

        handled = await remove_handler.handle(
            mock_event,
            "quit",
            mock_line_api,
            "group_G123",
            "U_OWNER",
            {"calendar_service": MagicMock()},
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None

        can_handle = await remove_handler.can_handle(mock_event, "1")

        assert can_handle is False