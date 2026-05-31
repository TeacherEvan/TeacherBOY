from __future__ import annotations

from datetime import date, datetime, timezone
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pytest


class _FakeConvexClient:
    def __init__(self):
        self.get_calls: list[tuple[str, dict[str, object]]] = []
        self.post_calls: list[tuple[str, dict[str, object]]] = []
        self.sync_get_calls: list[tuple[str, dict[str, object]]] = []
        self.sync_post_calls: list[tuple[str, dict[str, object]]] = []
        self._event: dict[str, object] | None = {
            "eventId": "convex-1",
            "legacyEventId": "legacy-1",
            "lineUserId": "U123",
            "sourceChatId": "group_C456",
            "title": "Repo Event",
            "description": "From Convex",
            "eventDate": "2030-01-05",
            "reminderDays": [3, 1, 0],
            "notificationTargetUserId": "U123",
            "notifiedDates": [],
            "createdAt": 1893456000000,
        }

    async def get(self, path: str, params: dict[str, object]) -> dict[str, object]:
        self.get_calls.append((path, params))
        return {"data": self._handle_get(path, params)}

    async def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.post_calls.append((path, payload))
        return {"data": self._handle_post(path, payload)}

    def get_sync(self, path: str, params: dict[str, object]) -> dict[str, object]:
        self.sync_get_calls.append((path, params))
        return {"data": self._handle_get(path, params)}

    def post_sync(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        self.sync_post_calls.append((path, payload))
        return {"data": self._handle_post(path, payload)}

    def _handle_get(self, path: str, params: dict[str, object]) -> object:
        if path == "/calendar/listChatEvents":
            if self._event and params.get("sourceChatId") == self._event["sourceChatId"]:
                return [dict(self._event)]
            return []

        if path == "/calendar/listUserEvents":
            if self._event and params.get("lineUserId") == self._event["lineUserId"]:
                return [dict(self._event)]
            return []

        if path == "/calendar/getDueReminders":
            if not self._event:
                return []

            line_user_id = params.get("lineUserId")
            source_chat_id = params.get("sourceChatId")
            if line_user_id and line_user_id != self._event["lineUserId"]:
                return []
            if source_chat_id and source_chat_id != self._event["sourceChatId"]:
                return []

            today = str(params["today"])
            days_until = (date.fromisoformat(str(self._event["eventDate"])) - date.fromisoformat(today)).days
            if days_until < 0 or days_until not in self._event["reminderDays"]:
                return []
            if today in self._event["notifiedDates"]:
                return []

            payload = dict(self._event)
            payload["days_until"] = days_until
            return [payload]

        raise AssertionError(f"Unexpected GET path: {path}")

    def _handle_post(self, path: str, payload: dict[str, object]) -> object:
        if path == "/calendar/upsertEvent":
            self._event = {
                "eventId": "convex-1",
                "legacyEventId": str(payload["legacyEventId"]),
                "lineUserId": str(payload["lineUserId"]),
                "sourceChatId": str(payload["sourceChatId"]),
                "title": str(payload["title"]),
                "description": str(payload.get("description") or ""),
                "eventDate": str(payload["eventDate"]),
                "reminderDays": list(payload.get("reminderDays") or [0]),
                "notificationTargetUserId": payload.get("notificationTargetUserId"),
                "notifiedDates": [],
                "createdAt": 1893456000000,
            }
            return dict(self._event)

        if path == "/calendar/markNotified":
            if not self._event:
                raise AssertionError("Cannot mark notification without a stored event")
            self._event = {
                **self._event,
                "notifiedDates": [str(payload["notifiedDate"])],
            }
            return dict(self._event)

        if path == "/calendar/deleteEvent":
            deleted = self._event is not None and str(payload["eventId"]) == self._event["eventId"]
            if deleted:
                self._event = None
            return {"deleted": deleted}

        raise AssertionError(f"Unexpected POST path: {path}")


class _FailingConvexClient(_FakeConvexClient):
    def __init__(
        self,
        *,
        fail_async_get: bool = False,
        fail_async_post: bool = False,
        fail_sync_get: bool = False,
        fail_sync_post: bool = False,
    ):
        super().__init__()
        self._fail_async_get = fail_async_get
        self._fail_async_post = fail_async_post
        self._fail_sync_get = fail_sync_get
        self._fail_sync_post = fail_sync_post

    async def get(self, path: str, params: dict[str, object]) -> dict[str, object]:
        if self._fail_async_get:
            raise RuntimeError(f"async get failed for {path}")
        return await super().get(path, params)

    async def post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        if self._fail_async_post:
            raise RuntimeError(f"async post failed for {path}")
        return await super().post(path, payload)

    def get_sync(self, path: str, params: dict[str, object]) -> dict[str, object]:
        if self._fail_sync_get:
            raise RuntimeError(f"sync get failed for {path}")
        return super().get_sync(path, params)

    def post_sync(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        if self._fail_sync_post:
            raise RuntimeError(f"sync post failed for {path}")
        return super().post_sync(path, payload)


@pytest.mark.asyncio
async def test_repository_due_reminders_map_convex_payload_to_calendar_shapes():
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    repository = ConvexCalendarRepository(_FakeConvexClient())

    reminders = await repository.get_due_reminders(
        today=date(2030, 1, 5),
        source_chat_id="group_C456",
    )

    assert len(reminders) == 1
    assert reminders[0]["days_until"] == 0
    assert reminders[0]["event"].event_id == "legacy-1"
    assert reminders[0]["event"].repository_event_id == "convex-1"


@pytest.mark.asyncio
async def test_get_chat_events_async_hydrates_local_cache_from_repository():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    repository = ConvexCalendarRepository(_FakeConvexClient())

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        events = await service.get_chat_events_async("group_C456")

        assert [event.event_id for event in events] == ["legacy-1"]
        assert events[0].repository_event_id == "convex-1"
        assert service.get_chat_events("group_C456")[0].event_id == "legacy-1"


@pytest.mark.asyncio
async def test_add_event_async_persists_and_marks_notified_through_repository_id():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    fake_client = _FakeConvexClient()
    fake_client._event = None
    repository = ConvexCalendarRepository(fake_client)

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        event = await service.add_event_async(
            user_id="U123",
            chat_id="group_C456",
            title="Repo Event",
            event_date=date(2030, 1, 5),
            description="From Convex",
            reminder_days=[0],
        )

        assert fake_client.post_calls[0][0] == "/calendar/upsertEvent"
        assert fake_client.post_calls[0][1]["legacyEventId"] == event.event_id
        assert event.repository_event_id == "convex-1"
        assert service.get_chat_events("group_C456")[0].repository_event_id == "convex-1"

        marked = await service.mark_event_notified_async(
            event.event_id,
            days_before=0,
            notified_date=date(2030, 1, 5),
        )

        assert marked is True
        assert fake_client.post_calls[1] == (
            "/calendar/markNotified",
            {
                "eventId": "convex-1",
                "reminderDay": 0,
                "notifiedDate": "2030-01-05",
            },
        )
        assert service.get_chat_events("group_C456")[0].notified_dates == ["2030-01-05"]


@pytest.mark.asyncio
async def test_add_event_async_does_not_leave_local_orphan_when_repository_upsert_fails():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    failing_client = _FailingConvexClient(fail_async_post=True)
    failing_client._event = None
    repository = ConvexCalendarRepository(failing_client)

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        with pytest.raises(RuntimeError, match="async post failed"):
            await service.add_event_async(
                user_id="U123",
                chat_id="group_C456",
                title="Repo Event",
                event_date=date(2030, 1, 5),
                description="From Convex",
                reminder_days=[0],
            )

        assert service.get_all_events(include_past=True) == []


def test_add_event_sync_rejects_duplicate_when_repository_has_matching_event_but_cache_is_cold():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    repository = ConvexCalendarRepository(_FakeConvexClient())

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        with pytest.raises(ValueError, match="Duplicate event"):
            service.add_event(
                user_id="U123",
                chat_id="group_C456",
                title="Repo Event",
                event_date=date(2030, 1, 5),
                description="From Convex",
                reminder_days=[0],
            )


@pytest.mark.asyncio
async def test_add_event_async_rejects_duplicate_when_repository_has_matching_event_but_cache_is_cold():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    repository = ConvexCalendarRepository(_FakeConvexClient())

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        with pytest.raises(ValueError, match="Duplicate event"):
            await service.add_event_async(
                user_id="U123",
                chat_id="group_C456",
                title="Repo Event",
                event_date=date(2030, 1, 5),
                description="From Convex",
                reminder_days=[0],
            )


def test_add_event_sync_does_not_leave_local_orphan_when_repository_upsert_fails():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    failing_client = _FailingConvexClient(fail_sync_post=True)
    failing_client._event = None
    repository = ConvexCalendarRepository(failing_client)

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        with pytest.raises(RuntimeError, match="sync post failed"):
            service.add_event(
                user_id="U123",
                chat_id="group_C456",
                title="Repo Event",
                event_date=date(2030, 1, 5),
                description="From Convex",
                reminder_days=[0],
            )

        assert service.get_all_events(include_past=True) == []


def test_sync_public_methods_route_reads_and_writes_through_repository():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    fake_client = _FakeConvexClient()
    fake_client._event = None
    repository = ConvexCalendarRepository(fake_client)

    class _FrozenDate(date):
        @classmethod
        def today(cls):
            return cls(2030, 1, 6)

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)

        with patch("src.services.calendar_service.date", _FrozenDate):
            created = service.add_event(
                user_id="U999",
                chat_id="group_Z999",
                title="Sync Repo Event",
                event_date=date(2030, 1, 6),
                description="Created via sync API",
                reminder_days=[0],
            )

            assert created.repository_event_id == "convex-1"
            assert fake_client.sync_post_calls[0][0] == "/calendar/upsertEvent"

            user_events = service.get_user_events("U999")
            chat_events = service.get_chat_events("group_Z999")
            due_events = service.get_events_needing_reminder(0)

            assert [event.event_id for event in user_events] == [created.event_id]
            assert [event.event_id for event in chat_events] == [created.event_id]
            assert [item.event_id for item in due_events] == [created.event_id]
            assert fake_client.sync_get_calls[:4] == [
                ("/calendar/listChatEvents", {"sourceChatId": "group_Z999", "includePast": "true"}),
                ("/calendar/listUserEvents", {"lineUserId": "U999", "includePast": "false"}),
                ("/calendar/listChatEvents", {"sourceChatId": "group_Z999", "includePast": "false"}),
                ("/calendar/getDueReminders", {"today": "2030-01-06", "lineUserId": None, "sourceChatId": None}),
            ]

            assert service.mark_event_notified(created.event_id, days_before=0) is True
            assert fake_client.sync_post_calls[1] == (
                "/calendar/markNotified",
                {
                    "eventId": "convex-1",
                    "reminderDay": 0,
                    "notifiedDate": "2030-01-06",
                },
            )


def test_remove_event_deletes_repository_record_when_repository_attached():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    fake_client = _FakeConvexClient()
    fake_client._event = None
    repository = ConvexCalendarRepository(fake_client)

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir, repository=repository)
        event = service.add_event(
            user_id="U123",
            chat_id="group_C456",
            title="Repo Event",
            event_date=date(2030, 1, 5),
            description="From Convex",
            reminder_days=[0],
        )

        assert service.remove_event(event.event_id, user_id="U123") is True
        assert fake_client.sync_post_calls[-1] == (
            "/calendar/deleteEvent",
            {"eventId": "convex-1"},
        )
        assert service.get_chat_events("group_C456") == []


@pytest.mark.asyncio
async def test_reminder_service_uses_repository_due_reminders_when_cache_is_cold():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository
    from src.services.reminder_service import ReminderService

    fake_client = _FakeConvexClient()
    repository = ConvexCalendarRepository(fake_client)

    class _FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 5, 8, 0, tzinfo=tz)

    with TemporaryDirectory() as tmpdir:
        calendar_service = CalendarService(local_storage_path=tmpdir, repository=repository)
        reminder_service = ReminderService()
        reminder_service.configure(calendar_service=calendar_service)

        with patch("src.services.reminder_service.datetime", _FrozenDateTime):
            result = await reminder_service.check_reminders_manually()

    assert result["reminders_due"] == 1
    assert result["events"][0]["event_id"] == "legacy-1"
    assert fake_client.get_calls[-1] == (
        "/calendar/getDueReminders",
        {"today": "2030-01-05", "lineUserId": None, "sourceChatId": None},
    )


@pytest.mark.asyncio
async def test_async_repository_reads_fall_back_to_cached_local_events_and_reminders():
    from src.services.calendar_service import CalendarService
    from src.services.convex_calendar_repository import ConvexCalendarRepository

    today = date(2030, 1, 5)
    repository = ConvexCalendarRepository(
        _FailingConvexClient(fail_async_get=True)
    )

    with TemporaryDirectory() as tmpdir:
        service = CalendarService(local_storage_path=tmpdir)
        cached_event = service.add_event(
            user_id="U123",
            chat_id="group_C456",
            title="Cached Event",
            event_date=today,
            description="Local fallback",
            reminder_days=[0],
        )
        service.configure(repository=repository)

        user_events = await service.get_user_events_async("U123")
        chat_events = await service.get_chat_events_async("group_C456")
        reminders = await service.get_events_needing_reminder_async(today)

        assert [event.event_id for event in user_events] == [cached_event.event_id]
        assert [event.event_id for event in chat_events] == [cached_event.event_id]
        assert [(item["event"].event_id, item["days_until"]) for item in reminders] == [
            (cached_event.event_id, 0)
        ]