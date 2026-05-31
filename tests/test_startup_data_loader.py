from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.history_log_service import HistoryLogService
from src.services.startup_data_loader import StartupDataLoader


class _FakeCalendarService:
    def __init__(self, hf_enabled: bool = True):
        self._hf_enabled = hf_enabled
        self._events = {}

    def _load_from_hub_sync(self):
        self._events = {"evt-1": object()}


class _DisabledService:
    def __init__(self):
        self._hf_enabled = False


class _FakeAsyncHubService:
    def __init__(self, *, load_succeeds: bool = True):
        self._hf_enabled = True
        self._load_succeeds = load_succeeds

    async def _load_from_hub(self):
        if not self._load_succeeds:
            raise RuntimeError("load failed")


class _FakeMemoryService(_FakeAsyncHubService):
    def __init__(self, *, load_succeeds: bool = True):
        super().__init__(load_succeeds=load_succeeds)
        self._conversations = {}

    async def _load_from_hub(self):
        await super()._load_from_hub()
        self._conversations = {"conv-1": {"messages": []}}


class _FakeDocumentService(_FakeAsyncHubService):
    pass


def _make_history_log_service(
    tmp_path,
    *,
    with_scheduler: bool = True,
    with_hf_sync_dir: bool = True,
):
    history_log = HistoryLogService(
        storage_path=str(tmp_path),
        enable_file_storage=True,
    )
    history_log._hf_enabled = True
    history_log._commit_scheduler = object() if with_scheduler else None

    hf_sync_dir = tmp_path / "hf_sync"
    if with_hf_sync_dir:
        hf_sync_dir.mkdir(exist_ok=True)

    return history_log


def test_is_ready_true_when_no_services_are_required():
    loader = StartupDataLoader()

    assert loader.is_ready() is True


def test_is_ready_false_when_calendar_is_required_but_not_loaded():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._calendar_loaded = False

    assert loader.is_ready() is False


def test_is_ready_true_when_all_required_services_are_loaded():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._calendar_loaded = True
    loader._memory_required = True
    loader._memory_loaded = True
    loader._documents_required = True
    loader._documents_loaded = True
    loader._logs_required = True
    loader._logs_loaded = True

    assert loader.is_ready() is True


def test_backup_creation_does_not_make_loader_ready_by_itself():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._calendar_loaded = False
    loader._backup_created = True

    assert loader.is_ready() is False


@pytest.mark.asyncio
async def test_ensure_data_loaded_marks_calendar_ready_when_enabled_and_loaded():
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=True)

    results = await loader.ensure_data_loaded(calendar_service=_FakeCalendarService())

    assert results["calendar"] is True
    assert loader.is_ready() is True


@pytest.mark.asyncio
async def test_ensure_data_loaded_treats_disabled_services_as_ready():
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=False)

    results = await loader.ensure_data_loaded(
        calendar_service=_DisabledService(),
        memory_service=_DisabledService(),
        document_service=_DisabledService(),
        history_log=_DisabledService(),
    )

    assert results == {
        "calendar": True,
        "staff_memory": True,
        "memory": True,
        "documents": True,
        "logs": True,
        "backup_created": False,
    }
    assert loader.is_ready() is True


@pytest.mark.asyncio
async def test_ensure_data_loaded_keeps_logs_not_ready_when_history_log_sync_is_not_usable(tmp_path):
    loader = StartupDataLoader()
    history_log = _make_history_log_service(tmp_path, with_scheduler=False)

    results = await loader.ensure_data_loaded(
        history_log=history_log
    )

    assert results["logs"] is False
    assert loader.is_ready() is False


@pytest.mark.asyncio
async def test_ensure_data_loaded_marks_ready_when_all_enabled_services_load(tmp_path):
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=True)
    history_log = _make_history_log_service(tmp_path)

    results = await loader.ensure_data_loaded(
        calendar_service=_FakeCalendarService(),
        memory_service=_FakeMemoryService(),
        document_service=_FakeDocumentService(),
        history_log=history_log,
    )

    assert results == {
        "calendar": True,
        "staff_memory": True,
        "memory": True,
        "documents": True,
        "logs": True,
        "backup_created": True,
    }
    assert loader.is_ready() is True


@pytest.mark.asyncio
async def test_ensure_data_loaded_keeps_ready_false_when_required_service_fails(tmp_path):
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=True)
    history_log = _make_history_log_service(tmp_path)

    results = await loader.ensure_data_loaded(
        calendar_service=_FakeCalendarService(),
        memory_service=_FakeMemoryService(load_succeeds=False),
        document_service=_FakeDocumentService(),
        history_log=history_log,
    )

    assert results == {
        "calendar": True,
        "staff_memory": True,
        "memory": False,
        "documents": True,
        "logs": True,
        "backup_created": True,
    }
    assert loader.is_ready() is False


@pytest.mark.asyncio
async def test_ensure_data_loaded_skips_calendar_backup_for_convex_backend():
    loader = StartupDataLoader()
    loader._create_llm_backup = AsyncMock(return_value=True)
    loader._clear_llm_backup = MagicMock()

    results = await loader.ensure_data_loaded(
        calendar_service=_FakeCalendarService(),
        calendar_backend="convex",
        convex_client=AsyncMock(healthcheck=AsyncMock(return_value=True)),
    )

    assert results["calendar"] is True
    assert results["backup_created"] is False
    loader._clear_llm_backup.assert_called_once_with()
    loader._create_llm_backup.assert_not_awaited()