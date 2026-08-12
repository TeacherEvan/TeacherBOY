from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings  # noqa: E402
from src.services.calendar_service import CalendarEvent  # noqa: E402
from src.services.convex_calendar_repository import ConvexCalendarRepository  # noqa: E402
from src.services.convex_client import ConvexClient  # noqa: E402
from src.services.convex_staff_memory_repository import ConvexStaffMemoryRepository  # noqa: E402
from src.services.staff_memory_service import StaffMemoryItem  # noqa: E402
from src.services.structured_records_service import StructuredRecordsService  # noqa: E402

DEFAULT_STAFF_MEMORY_PATH = PROJECT_ROOT / "data/staff_memory/staff_memory.json"
DEFAULT_CALENDAR_PATH = PROJECT_ROOT / "data/calendar/calendar_events.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill local staff memory and calendar data into Convex.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Preview backfill actions")
    mode.add_argument("--apply", action="store_true", help="Apply the backfill")
    parser.add_argument(
        "--staff-memory-path",
        type=Path,
        default=DEFAULT_STAFF_MEMORY_PATH,
        help=f"Path to local staff memory JSON (default: {DEFAULT_STAFF_MEMORY_PATH})",
    )
    parser.add_argument(
        "--calendar-path",
        type=Path,
        default=DEFAULT_CALENDAR_PATH,
        help=f"Path to local calendar JSON (default: {DEFAULT_CALENDAR_PATH})",
    )
    return parser.parse_args()


def load_staff_memory_items(path: Path) -> list[StaffMemoryItem]:
    if not path.exists():
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Expected a JSON array in {path}")

    return [StaffMemoryItem(**item) for item in raw]


def load_calendar_events(path: Path) -> list[CalendarEvent]:
    if not path.exists():
        return []

    raw = json.loads(path.read_text(encoding="utf-8"))
    events = raw.get("events", []) if isinstance(raw, dict) else []
    if not isinstance(events, list):
        raise ValueError(f"Expected an 'events' array in {path}")

    return [CalendarEvent.from_dict(item) for item in events]


def collect_user_ids(
    staff_items: list[StaffMemoryItem],
    calendar_events: list[CalendarEvent],
) -> list[str]:
    ordered_ids: list[str] = []
    seen: set[str] = set()

    def add(user_id: str | None) -> None:
        if not user_id:
            return
        normalized = str(user_id).strip()
        if not normalized or normalized in seen:
            return
        seen.add(normalized)
        ordered_ids.append(normalized)

    for item in staff_items:
        add(item.created_by)

    for event in calendar_events:
        add(event.user_id)
        add(event.notification_target_user_id)

    return ordered_ids


async def apply_backfill(
    staff_items: list[StaffMemoryItem],
    calendar_events: list[CalendarEvent],
) -> dict[str, int]:
    timeout_seconds = float(settings.convex_request_timeout_seconds)
    async with httpx.AsyncClient(follow_redirects=True) as http_client:
        convex_client = ConvexClient(
            base_url=str(settings.convex_deployment_url),
            sync_token=settings.convex_sync_token or "",
            http_client=http_client,
            timeout_seconds=timeout_seconds,
        )

        if not await convex_client.healthcheck():
            raise RuntimeError("Convex healthcheck failed; aborting backfill")

        records_service = StructuredRecordsService(convex_client=convex_client)
        staff_repository = ConvexStaffMemoryRepository(convex_client=convex_client)
        calendar_repository = ConvexCalendarRepository(convex_client=convex_client)

        upserted_users: set[str] = set()

        async def ensure_user(line_user_id: str | None) -> None:
            if not line_user_id:
                return
            normalized = str(line_user_id).strip()
            if not normalized or normalized in upserted_users:
                return
            await records_service.upsert_user(
                line_user_id=normalized,
                display_name=None,
                role=None,
            )
            upserted_users.add(normalized)

        for item in staff_items:
            await ensure_user(item.created_by)
            await staff_repository.upsert_item(item)

        for event in calendar_events:
            await ensure_user(event.user_id)
            await ensure_user(event.notification_target_user_id)
            await calendar_repository.upsert_event(event)

    return {
        "users": len(upserted_users),
        "staff_items": len(staff_items),
        "calendar_events": len(calendar_events),
    }


def print_plan(
    staff_path: Path,
    calendar_path: Path,
    staff_items: list[StaffMemoryItem],
    calendar_events: list[CalendarEvent],
) -> None:
    user_ids = collect_user_ids(staff_items, calendar_events)
    print("Convex backfill plan")
    print("mode: dry-run")
    print(f"staff memory path: {staff_path}")
    print(f"calendar path: {calendar_path}")
    print(f"users to upsert: {len(user_ids)}")
    print(f"staff memory items to write: {len(staff_items)}")
    print(f"calendar events to write: {len(calendar_events)}")

    if user_ids:
        print("sample user ids:", ", ".join(user_ids[:5]))

    if staff_items:
        sample_item = staff_items[0]
        print(
            "sample staff item:",
            json.dumps(
                {
                    "item_id": sample_item.item_id,
                    "created_by": sample_item.created_by,
                    "title": sample_item.title,
                },
                ensure_ascii=False,
            ),
        )

    if calendar_events:
        sample_event = calendar_events[0]
        print(
            "sample calendar event:",
            json.dumps(
                {
                    "event_id": sample_event.event_id,
                    "user_id": sample_event.user_id,
                    "notification_target_user_id": sample_event.notification_target_user_id,
                    "title": sample_event.title,
                },
                ensure_ascii=False,
            ),
        )


async def main() -> int:
    args = parse_args()

    staff_path = args.staff_memory_path.resolve()
    calendar_path = args.calendar_path.resolve()
    staff_items = load_staff_memory_items(staff_path)
    calendar_events = load_calendar_events(calendar_path)

    if args.dry_run:
        print_plan(staff_path, calendar_path, staff_items, calendar_events)
        print("No remote writes were performed.")
        return 0

    if not settings.is_convex_configured():
        raise RuntimeError("Convex is not configured. Set CONVEX_DEPLOYMENT_URL and CONVEX_SYNC_TOKEN first.")

    result = await apply_backfill(staff_items, calendar_events)
    print("Convex backfill applied")
    print(f"users upserted: {result['users']}")
    print(f"staff memory items written: {result['staff_items']}")
    print(f"calendar events written: {result['calendar_events']}")
    print("Local files were left unchanged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
