from datetime import datetime, timedelta

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.agents.calendar.remove_flow import RemoveFlow
from src.services.calendar_session_manager import CalendarState, calendar_session_manager


@pytest.fixture
def remove_flow():
    return RemoveFlow(calendar_service=MagicMock())


@pytest.fixture
def mock_event():
    event = MagicMock()
    event.reply_token = "reply-token"
    event.source = MagicMock()
    event.source.user_id = "U_REMOVE"
    event.source.group_id = None
    event.source.room_id = None
    return event


@pytest.fixture
def mock_line_api():
    return MagicMock()


@pytest.fixture(autouse=True)
def cleanup_remove_chat():
    for chat_id in ("remove_chat", "remove_group_chat", "group_G123"):
        calendar_session_manager.end_session(chat_id)
    yield
    for chat_id in ("remove_chat", "remove_group_chat", "group_G123"):
        calendar_session_manager.end_session(chat_id)


def _events():
    return [
        {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
        {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
        {"event_id": "evt-3", "title": "Science Fair", "date": "Jun 20"},
    ]


def _service_event(event_id, title, date_text, user_id):
    event = MagicMock()
    event.event_id = event_id
    event.title = title
    event.user_id = user_id
    event.event_date = __import__("datetime").datetime.strptime(date_text, "%Y-%m-%d")
    return event


class TestCalendarRemoveSessionManager:
    def test_start_removal_flow_sets_initial_revision_and_no_selection(self):
        session = calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())

        assert session.state == CalendarState.AWAITING_REMOVAL_SELECTION
        assert session.events_for_removal == _events()
        assert session.selected_event_ids == []
        assert session.removal_revision >= 1

    def test_apply_remove_selection_supports_all_none_and_number_lists(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())

        session = calendar_session_manager.apply_remove_selection("remove_chat", "all")
        assert session is not None
        assert session.selected_event_ids == ["evt-1", "evt-2", "evt-3"]
        assert session.state == CalendarState.AWAITING_REMOVAL_SELECTION

        session = calendar_session_manager.apply_remove_selection("remove_chat", "none")
        assert session is not None
        assert session.selected_event_ids == []

        session = calendar_session_manager.apply_remove_selection("remove_chat", "1,3")
        assert session is not None
        assert session.selected_event_ids == ["evt-1", "evt-3"]

    def test_apply_remove_selection_rejects_mixed_text_and_numbers(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())

        result = calendar_session_manager.apply_remove_selection("remove_chat", "1,done")

        assert result is None
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        assert session.selected_event_ids == []
        assert session.state == CalendarState.AWAITING_REMOVAL_SELECTION

    def test_finalize_remove_selection_returns_preview_and_revision(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        calendar_session_manager.apply_remove_selection("remove_chat", "1,2")

        preview = calendar_session_manager.finalize_remove_selection("remove_chat")

        assert preview is not None
        assert preview["revision"] == calendar_session_manager.get_session("remove_chat").removal_revision
        assert preview["code"] == calendar_session_manager.get_session("remove_chat").removal_confirmation_code
        assert preview["event_ids"] == ["evt-1", "evt-2"]
        assert preview["items"] == [
            {"event_id": "evt-1", "title": "Math Quiz", "date": "Jun 10"},
            {"event_id": "evt-2", "title": "Parent Meeting", "date": "Jun 12"},
        ]
        assert calendar_session_manager.get_session("remove_chat").state == CalendarState.CONFIRMING_REMOVAL

    def test_confirm_remove_rejects_stale_revision_and_wrong_owner(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        calendar_session_manager.apply_remove_selection("remove_chat", "1")
        preview = calendar_session_manager.finalize_remove_selection("remove_chat")

        assert preview is not None
        assert calendar_session_manager.confirm_remove_selection("remove_chat", "U_OTHER", preview["code"]) is None
        assert calendar_session_manager.confirm_remove_selection("remove_chat", "U_REMOVE", "deadbeef") is None

        confirmed = calendar_session_manager.confirm_remove_selection("remove_chat", "U_REMOVE", preview["code"])

        assert confirmed is not None
        assert confirmed["event_ids"] == ["evt-1"]

    def test_legacy_set_removal_selection_generates_confirmation_code(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())

        session = calendar_session_manager.set_removal_selection("remove_chat", ["evt-1"])

        assert session is not None
        assert session.state == CalendarState.CONFIRMING_REMOVAL
        assert session.removal_confirmation_code
        confirmed = calendar_session_manager.confirm_remove_selection(
            "remove_chat",
            "U_REMOVE",
            session.removal_confirmation_code,
        )
        assert confirmed is not None
        assert confirmed["event_ids"] == ["evt-1"]

    def test_confirmation_code_does_not_replay_across_new_remove_sessions(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        calendar_session_manager.apply_remove_selection("remove_chat", "1")
        first_preview = calendar_session_manager.finalize_remove_selection("remove_chat")

        assert first_preview is not None

        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        calendar_session_manager.apply_remove_selection("remove_chat", "1")
        second_preview = calendar_session_manager.finalize_remove_selection("remove_chat")

        assert second_preview is not None
        assert second_preview["code"] != first_preview["code"]
        assert calendar_session_manager.confirm_remove_selection(
            "remove_chat",
            "U_REMOVE",
            first_preview["code"],
        ) is None

    def test_cleanup_tracks_recent_remove_expiry_for_same_owner_only(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)

        calendar_session_manager._cleanup_expired_sessions()

        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_REMOVE") is True
        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_OTHER") is False

    def test_new_flow_creation_clears_recent_remove_expiry_marker(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("remove_chat") is None
        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_REMOVE") is True

        calendar_session_manager.start_add_flow("remove_chat", "U_REMOVE")

        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_REMOVE") is False

    def test_new_flow_by_other_user_does_not_clear_expired_owner_marker(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        session.updated_at = datetime.now() - timedelta(seconds=121)
        assert calendar_session_manager.get_session("remove_chat") is None

        calendar_session_manager.start_add_flow("remove_chat", "U_OTHER")

        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_REMOVE") is True
        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_OTHER") is False

    def test_end_session_keeps_recent_marker_for_completed_remove_flow(self):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        calendar_session_manager.apply_remove_selection("remove_chat", "1")
        calendar_session_manager.finalize_remove_selection("remove_chat")

        calendar_session_manager.end_session("remove_chat")

        assert calendar_session_manager.had_recent_remove_flow("remove_chat", "U_REMOVE") is True


class TestCalendarRemoveFlow:
    @pytest.mark.asyncio
    async def test_start_remove_flow_lists_only_events_owned_by_requesting_user(
        self,
        remove_flow,
        mock_event,
        mock_line_api,
    ):
        mock_event.source.group_id = "G123"
        remove_flow.send_message = AsyncMock()
        remove_flow._calendar_service.get_chat_events_async = AsyncMock(
            return_value=[
                _service_event("evt-1", "Math Quiz", "2026-06-10", "U_REMOVE"),
                _service_event("evt-2", "Other Person Event", "2026-06-12", "U_OTHER"),
                _service_event("evt-3", "Science Fair", "2026-06-20", "U_REMOVE"),
            ]
        )

        handled = await remove_flow.start_remove_flow(
            mock_event,
            mock_line_api,
            "group_G123",
            "U_REMOVE",
        )

        assert handled is True
        session = calendar_session_manager.get_session("group_G123")
        assert session is not None
        assert [item["event_id"] for item in session.events_for_removal] == ["evt-1", "evt-3"]
        sent_text = remove_flow.send_message.await_args.args[2]
        assert "Other Person Event" not in sent_text

    @pytest.mark.asyncio
    async def test_start_remove_flow_rejects_group_when_user_has_no_removable_events(
        self,
        remove_flow,
        mock_event,
        mock_line_api,
    ):
        mock_event.source.group_id = "G123"
        remove_flow.send_message = AsyncMock()
        remove_flow._calendar_service.get_chat_events_async = AsyncMock(
            return_value=[
                _service_event("evt-2", "Other Person Event", "2026-06-12", "U_OTHER"),
            ]
        )

        handled = await remove_flow.start_remove_flow(
            mock_event,
            mock_line_api,
            "group_G123",
            "U_REMOVE",
        )

        assert handled is True
        assert calendar_session_manager.get_session("group_G123") is None
        assert "no events you can remove in this group" in remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_selection_done_shows_preview_before_delete(self, remove_flow, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        remove_flow.send_message = AsyncMock()
        remove_flow.send_message_with_quick_reply = AsyncMock()

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "1,3",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True
        first_feedback = remove_flow.send_message.await_args.args[2]
        assert "Selected 2 events" in first_feedback

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "done",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        assert session.state == CalendarState.CONFIRMING_REMOVAL
        preview_text = remove_flow.send_message_with_quick_reply.await_args.args[2]
        assert "2 events selected for deletion" in preview_text.lower()
        assert "Math Quiz (Jun 10)" in preview_text
        assert "Science Fair (Jun 20)" in preview_text
        assert "delete" in preview_text.lower()
        assert "cancel" in preview_text.lower()

    @pytest.mark.asyncio
    async def test_selection_done_requires_non_empty_selection(self, remove_flow, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        remove_flow.send_message = AsyncMock()

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "done",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True
        assert "select at least one event" in remove_flow.send_message.await_args.args[2].lower()
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        assert session.state == CalendarState.AWAITING_REMOVAL_SELECTION

    @pytest.mark.asyncio
    async def test_selection_rejects_mixed_text_and_numbers(self, remove_flow, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        remove_flow.send_message = AsyncMock()

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "1,done",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True
        assert "invalid" in remove_flow.send_message.await_args.args[2].lower()
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        assert session.state == CalendarState.AWAITING_REMOVAL_SELECTION

    @pytest.mark.asyncio
    async def test_selection_none_clears_existing_selection(self, remove_flow, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        remove_flow.send_message = AsyncMock()

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "1,3",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "none",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        assert session.selected_event_ids == []
        assert "selected 0 events" in remove_flow.send_message.await_args.args[2].lower()

    @pytest.mark.asyncio
    async def test_confirmation_requires_delete_or_cancel_and_rejects_stale_revision(
        self,
        remove_flow,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        calendar_session_manager.apply_remove_selection("remove_chat", "2")
        preview = calendar_session_manager.finalize_remove_selection("remove_chat")
        remove_flow.send_message = AsyncMock()
        remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        assert preview is not None
        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        session.removal_confirmation_code = "feedbeef"

        handled = await remove_flow.handle_removal_confirmation(
            mock_event,
            f"delete {preview['code']}",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )

        assert handled is True
        assert "expired" in remove_flow.send_message.await_args.args[2].lower() or "stale" in remove_flow.send_message.await_args.args[2].lower()
        remove_flow._calendar_service.remove_events_by_ids_async.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_reselection_after_preview_invalidates_old_revision_and_uses_new_selection(
        self,
        remove_flow,
        mock_event,
        mock_line_api,
    ):
        calendar_session_manager.start_removal_flow("remove_chat", "U_REMOVE", _events())
        remove_flow.send_message = AsyncMock()
        remove_flow.send_message_with_quick_reply = AsyncMock()
        remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "1",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )
        assert handled is True

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "done",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )
        assert handled is True

        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        first_revision = session.removal_revision
        first_code = session.removal_confirmation_code

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "2",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )
        assert handled is True

        handled = await remove_flow.handle_removal_selection(
            mock_event,
            "done",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )
        assert handled is True

        session = calendar_session_manager.get_session("remove_chat")
        assert session is not None
        second_revision = session.removal_revision
        second_code = session.removal_confirmation_code
        assert second_revision == first_revision + 1
        assert second_code != first_code

        handled = await remove_flow.handle_removal_confirmation(
            mock_event,
            f"delete {first_code}",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )
        assert handled is True
        assert "stale" in remove_flow.send_message.await_args.args[2].lower() or "expired" in remove_flow.send_message.await_args.args[2].lower()
        remove_flow._calendar_service.remove_events_by_ids_async.assert_not_awaited()

        handled = await remove_flow.handle_removal_confirmation(
            mock_event,
            f"delete {second_code}",
            mock_line_api,
            "remove_chat",
            "U_REMOVE",
        )
        assert handled is True
        remove_flow._calendar_service.remove_events_by_ids_async.assert_awaited_once_with(["evt-2"], "U_REMOVE")

    @pytest.mark.asyncio
    async def test_confirmation_rejects_non_owner(self, remove_flow, mock_event, mock_line_api):
        calendar_session_manager.start_removal_flow("remove_group_chat", "U_OWNER", _events())
        calendar_session_manager.apply_remove_selection("remove_group_chat", "1")
        preview = calendar_session_manager.finalize_remove_selection("remove_group_chat")
        remove_flow.send_message = AsyncMock()
        remove_flow._calendar_service.remove_events_by_ids_async = AsyncMock(return_value=(1, 0))

        assert preview is not None
        handled = await remove_flow.handle_removal_confirmation(
            mock_event,
            f"delete {preview['code']}",
            mock_line_api,
            "remove_group_chat",
            "U_OTHER",
        )

        assert handled is True
        assert "owner" in remove_flow.send_message.await_args.args[2].lower() or "started" in remove_flow.send_message.await_args.args[2].lower()
        remove_flow._calendar_service.remove_events_by_ids_async.assert_not_awaited()