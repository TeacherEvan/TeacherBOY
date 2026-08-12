from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from scripts import convex_backfill
from src.services.staff_memory_service import StaffMemoryItem


@pytest.mark.asyncio
async def test_apply_backfill_uses_idempotent_staff_memory_upsert() -> None:
    staff_item = StaffMemoryItem(
        item_id="item-1",
        title="Weekly note",
        summary="Summary",
        priority="P1",
        due_date=date(2026, 6, 2).isoformat(),
        source_chat_id="group_G1",
        created_by="U123",
    )

    convex_client = MagicMock()
    convex_client.healthcheck = AsyncMock(return_value=True)
    records_service = MagicMock()
    records_service.upsert_user = AsyncMock()
    staff_repository = MagicMock()
    staff_repository.upsert_item = AsyncMock(return_value=staff_item)
    calendar_repository = MagicMock()
    calendar_repository.upsert_event = AsyncMock()

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.__aexit__.return_value = False

    with (
        patch.object(convex_backfill.httpx, "AsyncClient", return_value=async_client),
        patch.object(convex_backfill, "ConvexClient", return_value=convex_client),
        patch.object(convex_backfill, "StructuredRecordsService", return_value=records_service),
        patch.object(convex_backfill, "ConvexStaffMemoryRepository", return_value=staff_repository),
        patch.object(convex_backfill, "ConvexCalendarRepository", return_value=calendar_repository),
    ):
        result = await convex_backfill.apply_backfill([staff_item], [])

    assert result == {
        "users": 1,
        "staff_items": 1,
        "calendar_events": 0,
    }
    records_service.upsert_user.assert_awaited_once_with(
        line_user_id="U123",
        display_name=None,
        role=None,
    )
    staff_repository.upsert_item.assert_awaited_once_with(staff_item)
    staff_repository.save_item.assert_not_called()
