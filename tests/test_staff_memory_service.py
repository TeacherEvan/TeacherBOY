from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.services.convex_staff_memory_repository import (
    ConvexStaffMemoryRepository,
)
from src.services.staff_memory_service import StaffMemoryItem, StaffMemoryService


def test_staff_memory_saves_and_ranks_week_items(tmp_path):
    service = StaffMemoryService(tmp_path / "staff_memory.json")
    service.add_item(
        title="Flag ceremony practice",
        summary="Flag ceremony practice this week",
        priority="P1",
        due_date=date(2026, 6, 2),
        source_chat_id="group_G1",
        created_by="U1",
    )

    items = service.get_items_for_week(date(2026, 6, 1))
    assert len(items) == 1
    assert items[0].priority == "P1"


def test_staff_memory_excludes_undated_items_from_week_view(tmp_path):
    service = StaffMemoryService(tmp_path / "staff_memory.json")
    service.add_item(
        title="Undated reminder",
        summary="No due date assigned",
        priority="P3",
        due_date=None,
        source_chat_id="group_G1",
        created_by="U1",
    )

    items = service.get_items_for_week(date(2026, 6, 1))

    assert items == []


@pytest.mark.asyncio
async def test_staff_memory_can_use_convex_repository_without_json_file(tmp_path):
    convex_client = AsyncMock()

    created_payload = {}

    def post_side_effect(path, payload):
        if path == "/records/createStaffMemoryItem":
            created_payload.clear()
            created_payload.update(payload)
            return {"data": dict(payload)}

        return {"data": [dict(created_payload)]}

    convex_client.post.side_effect = post_side_effect
    service = StaffMemoryService(
        tmp_path / "staff_memory.json",
        repository=ConvexStaffMemoryRepository(convex_client=convex_client),
    )

    item = await service.add_item_async(
        title="Flag ceremony practice",
        summary="Flag ceremony practice this week",
        priority="P1",
        due_date=date(2026, 6, 2),
        source_chat_id="group_G1",
        created_by="U1",
    )

    items = await service.get_items_for_week_async(date(2026, 6, 1))

    assert item.item_id == created_payload["itemId"]
    assert [weekly_item.item_id for weekly_item in items] == [item.item_id]
    assert (tmp_path / "staff_memory.json").exists() is False
    assert convex_client.post.await_count == 2
    assert created_payload["title"] == "Flag ceremony practice"
    assert created_payload["summary"] == "Flag ceremony practice this week"
    assert created_payload["priority"] == "P1"
    assert created_payload["dueDate"] == "2026-06-02"
    assert created_payload["sourceChatId"] == "group_G1"
    assert created_payload["createdBy"] == "U1"
    convex_client.post.assert_any_await(
        "/records/listStaffMemoryItemsForWeek",
        {
            "weekStart": "2026-06-01",
            "weekEnd": "2026-06-07",
        },
    )


@pytest.mark.asyncio
async def test_convex_staff_memory_repository_can_upsert_existing_item() -> None:
    convex_client = AsyncMock()
    repository = ConvexStaffMemoryRepository(convex_client=convex_client)
    convex_client.post.return_value = {
        "data": {
            "itemId": "item-1",
            "title": "Weekly note",
            "summary": "Summary",
            "priority": "P1",
            "dueDate": "2026-06-02",
            "sourceChatId": "group_G1",
            "createdBy": "U1",
        }
    }

    item = await repository.upsert_item(
        StaffMemoryItem(
            item_id="item-1",
            title="Weekly note",
            summary="Summary",
            priority="P1",
            due_date="2026-06-02",
            source_chat_id="group_G1",
            created_by="U1",
        )
    )

    convex_client.post.assert_awaited_once()
    called_path, called_payload = convex_client.post.await_args.args
    assert called_path == "/records/upsertStaffMemoryItem"
    assert called_payload["itemId"] == item.item_id


@pytest.mark.asyncio
async def test_staff_memory_keeps_existing_local_items_visible_during_cutover(
    tmp_path,
):
    local_service = StaffMemoryService(tmp_path / "staff_memory.json")
    local_item = local_service.add_item(
        title="Existing local note",
        summary="Created before Convex cutover",
        priority="P2",
        due_date=date(2026, 6, 3),
        source_chat_id="group_G1",
        created_by="U1",
    )

    convex_client = AsyncMock()
    convex_client.post.return_value = {"data": []}

    service = StaffMemoryService(
        tmp_path / "staff_memory.json",
        repository=ConvexStaffMemoryRepository(convex_client=convex_client),
    )

    items = await service.get_items_for_week_async(date(2026, 6, 1))

    assert [item.item_id for item in items] == [local_item.item_id]


@pytest.mark.asyncio
async def test_repository_backed_sync_methods_raise_clear_error_inside_event_loop(
    tmp_path,
):
    convex_client = AsyncMock()
    service = StaffMemoryService(
        tmp_path / "staff_memory.json",
        repository=ConvexStaffMemoryRepository(convex_client=convex_client),
    )

    with pytest.raises(RuntimeError, match="add_item_async"):
        service.add_item(
            title="Flag ceremony practice",
            summary="Flag ceremony practice this week",
            priority="P1",
            due_date=date(2026, 6, 2),
            source_chat_id="group_G1",
            created_by="U1",
        )

    with pytest.raises(RuntimeError, match="get_items_for_week_async"):
        service.get_items_for_week(date(2026, 6, 1))