from __future__ import annotations

import json
import asyncio
import uuid
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Protocol


@dataclass
class StaffMemoryItem:
    item_id: str
    title: str
    summary: str
    priority: str
    due_date: str | None
    source_chat_id: str
    created_by: str


class StaffMemoryRepository(Protocol):
    async def save_item(self, item: StaffMemoryItem) -> StaffMemoryItem: ...

    async def get_items_for_week(
        self, week_start: date, week_end: date
    ) -> list[StaffMemoryItem]: ...


class StaffMemoryService:
    def __init__(
        self,
        storage_path: Path,
        repository: StaffMemoryRepository | None = None,
    ):
        self._storage_path = Path(storage_path)
        self._repository = repository
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
        if self._repository is not None:
            return self._run_repository_sync(
                "add_item",
                self.add_item_async(
                    title=title,
                    summary=summary,
                    priority=priority,
                    due_date=due_date,
                    source_chat_id=source_chat_id,
                    created_by=created_by,
                )
            )

        item = self._build_item(
            title=title,
            summary=summary,
            priority=priority,
            due_date=due_date,
            source_chat_id=source_chat_id,
            created_by=created_by,
        )
        self._items.append(item)
        self._save()
        return item

    async def add_item_async(
        self,
        title: str,
        summary: str,
        priority: str,
        due_date: date | None,
        source_chat_id: str,
        created_by: str,
    ) -> StaffMemoryItem:
        item = self._build_item(
            title=title,
            summary=summary,
            priority=priority,
            due_date=due_date,
            source_chat_id=source_chat_id,
            created_by=created_by,
        )
        if self._repository is not None:
            return await self._repository.save_item(item)

        self._items.append(item)
        self._save()
        return item

    def _build_item(
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
        return item

    def get_items_for_week(self, week_start: date) -> list[StaffMemoryItem]:
        if self._repository is not None:
            return self._run_repository_sync(
                "get_items_for_week",
                self.get_items_for_week_async(week_start),
            )

        week_end = week_start + timedelta(days=6)
        return self._sort_items(self._merge_items(self._get_local_items_for_week(week_start, week_end), []))

    async def get_items_for_week_async(
        self, week_start: date
    ) -> list[StaffMemoryItem]:
        week_end = week_start + timedelta(days=6)
        remote_items: list[StaffMemoryItem] = []
        if self._repository is not None:
            remote_items = await self._repository.get_items_for_week(
                week_start, week_end
            )

        return self._sort_items(
            self._merge_items(
                self._get_local_items_for_week(week_start, week_end),
                remote_items,
            )
        )

    def _get_local_items_for_week(
        self, week_start: date, week_end: date
    ) -> list[StaffMemoryItem]:
        ranked: list[StaffMemoryItem] = []
        for item in self._items:
            if not item.due_date:
                continue

            due = date.fromisoformat(item.due_date)
            if week_start <= due <= week_end:
                ranked.append(item)

        return ranked

    def _merge_items(
        self,
        local_items: list[StaffMemoryItem],
        remote_items: list[StaffMemoryItem],
    ) -> list[StaffMemoryItem]:
        merged: dict[str, StaffMemoryItem] = {
            item.item_id: item for item in local_items
        }
        for item in remote_items:
            merged[item.item_id] = item
        return list(merged.values())

    def _sort_items(self, items: list[StaffMemoryItem]) -> list[StaffMemoryItem]:
        return sorted(
            items,
            key=lambda item: (
                item.priority,
                item.due_date or "9999-12-31",
                item.title,
            ),
        )

    def _run_repository_sync(self, method_name: str, coroutine):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coroutine)

        raise RuntimeError(
            "StaffMemoryService."
            f"{method_name}() cannot be used with a repository inside an active "
            f"event loop; use {method_name}_async() instead"
        )