from datetime import date

from src.services.staff_memory_service import StaffMemoryService


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