# tests/services/test_convex_mod_repository.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.convex_mod_repository import ConvexModRepository


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly (not a coroutine)."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_convex_client():
    return MagicMock(spec=["get", "post"])


@pytest.fixture
def repo(mock_convex_client):
    return ConvexModRepository(mock_convex_client)


@pytest.mark.asyncio
async def test_get_mod_mode_state(repo, mock_convex_client):
    mock_convex_client.get = _make_async_mock(
        {"data": {"groupId": "C123", "mode": "all", "activatedBy": "U456", "isActive": True}}
    )
    result = await repo.get_mod_mode_state("C123")
    assert result is not None
    assert result["mode"] == "all"
    mock_convex_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_set_mod_mode_state(repo, mock_convex_client):
    mock_convex_client.post = _make_async_mock(
        {"data": {"groupId": "C123", "mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}}
    )
    result = await repo.set_mod_mode_state("C123", "special", "U456", "U789")
    assert result["mode"] == "special"
    assert result["specialUserId"] == "U789"
    mock_convex_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_ban_user(repo, mock_convex_client):
    mock_convex_client.post = _make_async_mock(
        {"data": {"groupId": "C123", "userId": "U999", "bannedBy": "U456", "reason": "spam"}}
    )
    result = await repo.ban_user("C123", "U999", "U456", "spam")
    assert result["userId"] == "U999"
    mock_convex_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_is_user_banned(repo, mock_convex_client):
    mock_convex_client.get = _make_async_mock({"data": {"groupId": "C123", "userId": "U999"}})
    result = await repo.is_user_banned("C123", "U999")
    assert result is True
    mock_convex_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_unban_user(repo, mock_convex_client):
    mock_convex_client.post = _make_async_mock({"success": True})
    result = await repo.unban_user("C123", "U999")
    assert result is True


@pytest.mark.asyncio
async def test_add_warning(repo, mock_convex_client):
    # First call: get_warning_count returns 0, second call: add_warning returns count=1
    mock_convex_client.get = _make_async_mock({"data": None})
    mock_convex_client.post = _make_async_mock({"data": {"groupId": "C123", "userId": "U999", "count": 1}})
    result = await repo.add_warning("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 1


@pytest.mark.asyncio
async def test_get_warning_count(repo, mock_convex_client):
    mock_convex_client.get = _make_async_mock({"data": {"count": 2}})
    result = await repo.get_warning_count("C123", "U999")
    assert result == 2


@pytest.mark.asyncio
async def test_mark_warning_read(repo, mock_convex_client):
    mock_convex_client.post = _make_async_mock({"data": {"readByUser": True}})
    result = await repo.mark_warning_read("C123", "U999")
    assert result["readByUser"] is True
