from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any

from src.services.calendar_service import CalendarEvent


class ConvexCalendarRepository:
    def __init__(self, convex_client: Any):
        self._convex_client = convex_client

    def upsert_event_sync(self, event: CalendarEvent) -> CalendarEvent:
        response = self._convex_client.post_sync(
            "/calendar/upsertEvent",
            {
                "eventId": event.repository_event_id,
                "legacyEventId": event.event_id,
                "lineUserId": event.user_id,
                "sourceChatId": event.chat_id,
                "title": event.title,
                "description": event.description or None,
                "eventDate": event.event_date.isoformat(),
                "reminderDays": list(event.reminder_days),
                "notificationTargetUserId": event.notification_target_user_id,
            },
        )
        return self._deserialize_event(self._unwrap_data(response))

    async def upsert_event(self, event: CalendarEvent) -> CalendarEvent:
        response = await self._convex_client.post(
            "/calendar/upsertEvent",
            {
                "eventId": event.repository_event_id,
                "legacyEventId": event.event_id,
                "lineUserId": event.user_id,
                "sourceChatId": event.chat_id,
                "title": event.title,
                "description": event.description or None,
                "eventDate": event.event_date.isoformat(),
                "reminderDays": list(event.reminder_days),
                "notificationTargetUserId": event.notification_target_user_id,
            },
        )
        return self._deserialize_event(self._unwrap_data(response))

    def list_user_events_sync(
        self,
        line_user_id: str,
        include_past: bool = False,
    ) -> list[CalendarEvent]:
        response = self._convex_client.get_sync(
            "/calendar/listUserEvents",
            {
                "lineUserId": line_user_id,
                "includePast": str(include_past).lower(),
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []
        return [self._deserialize_event(item) for item in data if isinstance(item, dict)]

    async def list_user_events(
        self,
        line_user_id: str,
        include_past: bool = False,
    ) -> list[CalendarEvent]:
        response = await self._convex_client.get(
            "/calendar/listUserEvents",
            {
                "lineUserId": line_user_id,
                "includePast": str(include_past).lower(),
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []
        return [self._deserialize_event(item) for item in data if isinstance(item, dict)]

    def list_chat_events_sync(
        self,
        source_chat_id: str,
        include_past: bool = False,
    ) -> list[CalendarEvent]:
        response = self._convex_client.get_sync(
            "/calendar/listChatEvents",
            {
                "sourceChatId": source_chat_id,
                "includePast": str(include_past).lower(),
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []
        return [self._deserialize_event(item) for item in data if isinstance(item, dict)]

    async def list_chat_events(
        self,
        source_chat_id: str,
        include_past: bool = False,
    ) -> list[CalendarEvent]:
        response = await self._convex_client.get(
            "/calendar/listChatEvents",
            {
                "sourceChatId": source_chat_id,
                "includePast": str(include_past).lower(),
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []
        return [self._deserialize_event(item) for item in data if isinstance(item, dict)]

    def get_due_reminders_sync(
        self,
        today: date,
        *,
        line_user_id: str | None = None,
        source_chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        response = self._convex_client.get_sync(
            "/calendar/getDueReminders",
            {
                "today": today.isoformat(),
                "lineUserId": line_user_id,
                "sourceChatId": source_chat_id,
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []

        reminders: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            reminders.append(
                {
                    "event": self._deserialize_event(item),
                    "days_until": int(item.get("days_until", 0)),
                }
            )
        return reminders

    async def get_due_reminders(
        self,
        today: date,
        *,
        line_user_id: str | None = None,
        source_chat_id: str | None = None,
    ) -> list[dict[str, Any]]:
        response = await self._convex_client.get(
            "/calendar/getDueReminders",
            {
                "today": today.isoformat(),
                "lineUserId": line_user_id,
                "sourceChatId": source_chat_id,
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []

        reminders: list[dict[str, Any]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            reminders.append(
                {
                    "event": self._deserialize_event(item),
                    "days_until": int(item.get("days_until", 0)),
                }
            )
        return reminders

    def mark_event_notified_sync(
        self,
        repository_event_id: str,
        reminder_day: int,
        notified_date: date,
    ) -> CalendarEvent:
        response = self._convex_client.post_sync(
            "/calendar/markNotified",
            {
                "eventId": repository_event_id,
                "reminderDay": reminder_day,
                "notifiedDate": notified_date.isoformat(),
            },
        )
        return self._deserialize_event(self._unwrap_data(response))

    async def mark_event_notified(
        self,
        repository_event_id: str,
        reminder_day: int,
        notified_date: date,
    ) -> CalendarEvent:
        response = await self._convex_client.post(
            "/calendar/markNotified",
            {
                "eventId": repository_event_id,
                "reminderDay": reminder_day,
                "notifiedDate": notified_date.isoformat(),
            },
        )
        return self._deserialize_event(self._unwrap_data(response))

    def delete_event_sync(self, repository_event_id: str) -> bool:
        response = self._convex_client.post_sync(
            "/calendar/deleteEvent",
            {
                "eventId": repository_event_id,
            },
        )
        data = self._unwrap_data(response)
        return bool(isinstance(data, dict) and data.get("deleted"))

    async def delete_event(self, repository_event_id: str) -> bool:
        response = await self._convex_client.post(
            "/calendar/deleteEvent",
            {
                "eventId": repository_event_id,
            },
        )
        data = self._unwrap_data(response)
        return bool(isinstance(data, dict) and data.get("deleted"))

    def _unwrap_data(self, response: Any) -> Any:
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response

    def _deserialize_event(self, payload: dict[str, Any]) -> CalendarEvent:
        legacy_event_id = payload.get("legacyEventId") or payload.get("eventId") or ""
        created_at = self._deserialize_created_at(payload.get("createdAt"))

        return CalendarEvent(
            event_id=str(legacy_event_id),
            user_id=str(payload.get("lineUserId", "")),
            chat_id=str(payload.get("sourceChatId", "")),
            title=str(payload.get("title", "")),
            event_date=date.fromisoformat(str(payload.get("eventDate"))),
            description=str(payload.get("description") or ""),
            reminder_days=[int(value) for value in payload.get("reminderDays", [0])],
            notification_target_user_id=self._optional_string(payload.get("notificationTargetUserId")),
            notified_dates=[str(value) for value in payload.get("notifiedDates", [])],
            created_at=created_at,
            repository_event_id=self._optional_string(payload.get("eventId")),
        )

    def _deserialize_created_at(self, value: Any) -> datetime | None:
        if value in {None, ""}:
            return None
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(float(value) / 1000, tz=UTC)
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        return None

    def _optional_string(self, value: Any) -> str | None:
        if value in {None, ""}:
            return None
        return str(value)
