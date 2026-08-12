# tests/services/test_warning_service.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.warning_service import WarningService


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly (not a coroutine)."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_repo():
    return MagicMock(spec=["add_warning", "get_warning_count", "mark_warning_read", "get_warnings"])


@pytest.fixture
def service(mock_repo):
    return WarningService(mock_repo)


@pytest.mark.asyncio
async def test_warn_user_first_strike(service, mock_repo):
    mock_repo.add_warning = _make_async_mock({"count": 1})
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 1
    assert result["should_ban"] is False


@pytest.mark.asyncio
async def test_warn_user_third_strike_bans(service, mock_repo):
    mock_repo.add_warning = _make_async_mock({"count": 3})
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 3
    assert result["should_ban"] is True


@pytest.mark.asyncio
async def test_get_warning_count(service, mock_repo):
    mock_repo.get_warning_count = _make_async_mock(2)
    count = await service.get_warning_count("C123", "U999")
    assert count == 2


@pytest.mark.asyncio
async def test_mark_warning_read(service, mock_repo):
    mock_repo.mark_warning_read = _make_async_mock({"readByUser": True})
    result = await service.mark_warning_read("C123", "U999")
    assert result["readByUser"] is True
