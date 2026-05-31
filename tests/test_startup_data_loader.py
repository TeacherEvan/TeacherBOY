from unittest.mock import AsyncMock

import pytest

from src.services.startup_data_loader import StartupDataLoader


class FakeCalendarService:
    def __init__(self, hf_enabled: bool = True, has_load_method: bool = True):
        self._hf_enabled = hf_enabled
        self._events = {}
        if has_load_method:
            self._load_from_hub_sync = lambda: None


class FakeMemoryService:
    def __init__(self, hf_enabled: bool = True):
        self._hf_enabled = hf_enabled
        self._conversations = {}

    async def _load_from_hub(self):
        return None


class FakeDocumentService:
    def __init__(self, hf_enabled: bool = True):
        self._hf_enabled = hf_enabled

    async def _load_from_hub(self):
        return None


class FakeHistoryLog:
    def __init__(self, hf_enabled: bool = True):
        self._hf_enabled = hf_enabled


def test_is_ready_false_before_any_load_attempt_runs():
    loader = StartupDataLoader()

    assert loader.is_ready() is False


@pytest.mark.asyncio
async def test_is_ready_true_when_no_services_are_required():
    loader = StartupDataLoader()

    results = await loader.ensure_data_loaded(max_retries=1, retry_delay_seconds=0)

    assert results["calendar"] is True
    assert results["memory"] is True
    assert results["documents"] is True
    assert results["logs"] is True
    assert loader.is_ready() is True


@pytest.mark.asyncio
async def test_is_ready_false_when_calendar_is_required_but_not_loaded():
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=True)

    results = await loader.ensure_data_loaded(
        calendar_service=FakeCalendarService(has_load_method=False),
        max_retries=1,
        retry_delay_seconds=0,
    )

    assert results["calendar"] is False
    assert results["backup_created"] is True
    assert loader.is_ready() is False


@pytest.mark.asyncio
async def test_is_ready_true_when_all_required_services_are_loaded():
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=False)

    await loader.ensure_data_loaded(
        calendar_service=FakeCalendarService(),
        memory_service=FakeMemoryService(),
        document_service=FakeDocumentService(),
        history_log=FakeHistoryLog(),
        max_retries=1,
        retry_delay_seconds=0,
    )

    assert loader.is_ready() is True


def test_backup_creation_does_not_make_loader_ready_by_itself():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._backup_created = True

    assert loader.is_ready() is False