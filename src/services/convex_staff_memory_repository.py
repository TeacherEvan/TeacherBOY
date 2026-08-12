from __future__ import annotations

from datetime import date
from typing import Any, TypeVar

from src.services.staff_memory_service import StaffMemoryItem

T = TypeVar("T")


class ConvexStaffMemoryRepository:
    def __init__(self, convex_client: Any):
        self._convex_client = convex_client

    async def save_item(self, item: StaffMemoryItem) -> StaffMemoryItem:
        response = await self._convex_client.post(
            "/records/createStaffMemoryItem",
            self._serialize_item(item),
        )
        return self._deserialize_item(self._unwrap_data(response))

    async def upsert_item(self, item: StaffMemoryItem) -> StaffMemoryItem:
        response = await self._convex_client.post(
            "/records/upsertStaffMemoryItem",
            self._serialize_item(item),
        )
        return self._deserialize_item(self._unwrap_data(response))

    async def get_items_for_week(self, week_start: date, week_end: date) -> list[StaffMemoryItem]:
        response = await self._convex_client.post(
            "/records/listStaffMemoryItemsForWeek",
            {
                "weekStart": week_start.isoformat(),
                "weekEnd": week_end.isoformat(),
            },
        )
        data = self._unwrap_data(response)
        if not isinstance(data, list):
            return []
        return [self._deserialize_item(item) for item in data if isinstance(item, dict)]

    def _unwrap_data(self, response: Any) -> Any:
        if isinstance(response, dict) and "data" in response:
            return response["data"]
        return response

    def _deserialize_item(self, payload: dict[str, Any]) -> StaffMemoryItem:
        return StaffMemoryItem(
            item_id=str(payload.get("itemId", "")),
            title=str(payload.get("title", "")),
            summary=str(payload.get("summary", "")),
            priority=str(payload.get("priority", "")),
            due_date=self._normalize_due_date(payload.get("dueDate")),
            source_chat_id=str(payload.get("sourceChatId", "")),
            created_by=str(payload.get("createdBy", "")),
        )

    def _normalize_due_date(self, value: Any) -> str | None:
        if value in {None, ""}:
            return None
        return str(value)

    def _serialize_item(self, item: StaffMemoryItem) -> dict[str, Any]:
        return {
            "itemId": item.item_id,
            "title": item.title,
            "summary": item.summary,
            "priority": item.priority,
            "dueDate": item.due_date,
            "sourceChatId": item.source_chat_id,
            "createdBy": item.created_by,
        }
