from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path


@dataclass
class StaffMemoryItem:
    item_id: str
    title: str
    summary: str
    priority: str
    due_date: str | None
    source_chat_id: str
    created_by: str


class StaffMemoryService:
    def __init__(self, storage_path: Path):
        self._storage_path = Path(storage_path)
        self._items = self._load()

    def _load(self) -> list[StaffMemoryItem]:
        if not self._storage_path.exists():
            return []
        raw = json.loads(self._storage_path.read_text(encoding="utf-8"))
        return [StaffMemoryItem(**item) for item in raw]

    def _save(self) -> None:
        self._storage_path.parent.mkdir(parents=True, exist_ok=True)
        self._storage_path.write_text(
            json.dumps([asdict(item) for item in self._items], indent=2),
            encoding="utf-8",
        )

    def add_item(
        self,
        title: str,
        summary: str,
        priority: str,
        due_date: date | None,
        source_chat_id: str,
        created_by: str,
    ) -> StaffMemoryItem:
        item = StaffMemoryItem(
            item_id=str(uuid.uuid4()),
            title=title,
            summary=summary,
            priority=priority,
            due_date=due_date.isoformat() if due_date else None,
            source_chat_id=source_chat_id,
            created_by=created_by,
        )
        self._items.append(item)
        self._save()
        return item

    def get_items_for_week(self, week_start: date) -> list[StaffMemoryItem]:
        week_end = week_start + timedelta(days=6)
        ranked = []
        for item in self._items:
            if not item.due_date:
                ranked.append(item)
                continue

            due = date.fromisoformat(item.due_date)
            if week_start <= due <= week_end:
                ranked.append(item)

        return sorted(ranked, key=lambda item: (item.priority, item.due_date or "9999-12-31"))