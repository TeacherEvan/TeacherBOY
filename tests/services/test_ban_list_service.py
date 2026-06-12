# tests/services/test_ban_list_service.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.ban_list_service import BanListService


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly (not a coroutine)."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_repo():
    return MagicMock(spec=["ban_user", "is_user_banned", "unban_user", "get_ban_list"])


@pytest.fixture
def service(mock_repo):
    return BanListService(mock_repo)


@pytest.mark.asyncio
async def test_ban_user(service, mock_repo):
    mock_repo.ban_user = _make_async_mock({"userId": "U999", "reason": "spam"})
    result = await service.ban_user("C123", "U999", "U456", "spam")
    assert result["userId"] == "U999"
    mock_repo.ban_user.assert_called_once()


@pytest.mark.asyncio
async def test_is_banned(service, mock_repo):
    mock_repo.is_user_banned = _make_async_mock(True)
    result = await service.is_banned("C123", "U999")
    assert result is True


@pytest.mark.asyncio
async def test_unban_user(service, mock_repo):
    mock_repo.unban_user = _make_async_mock(True)
    result = await service.unban_user("C123", "U999")
    assert result is True


@pytest.mark.asyncio
async def test_get_ban_list(service, mock_repo):
    mock_repo.get_ban_list = _make_async_mock([{"userId": "U1"}, {"userId": "U2"}])
    result = await service.get_ban_list("C123")
    assert len(result) == 2
