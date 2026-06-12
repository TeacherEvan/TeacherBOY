import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.convex_mod_repository import ConvexModRepository


@pytest.fixture
def mock_convex_client():
    return AsyncMock()


@pytest.fixture
def repo(mock_convex_client):
    return ConvexModRepository(mock_convex_client)


@pytest.mark.asyncio
async def test_get_mod_mode_state(repo, mock_convex_client):
    mock_convex_client.get.return_value = {"data": {"groupId": "C123", "mode": "all", "activatedBy": "U456", "isActive": True}}
    result = await repo.get_mod_mode_state("C123")
    assert result is not None
    assert result["mode"] == "all"
    mock_convex_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_set_mod_mode_state(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"data": {"groupId": "C123", "mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}}
    result = await repo.set_mod_mode_state("C123", "special", "U456", "U789")
    assert result["mode"] == "special"
    assert result["specialUserId"] == "U789"
    mock_convex_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_ban_user(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"data": {"groupId": "C123", "userId": "U999", "bannedBy": "U456", "reason": "spam"}}
    result = await repo.ban_user("C123", "U999", "U456", "spam")
    assert result["userId"] == "U999"
    mock_convex_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_is_user_banned(repo, mock_convex_client):
    mock_convex_client.get.return_value = {"data": {"groupId": "C123", "userId": "U999"}}
    result = await repo.is_user_banned("C123", "U999")
    assert result is True
    mock_convex_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_unban_user(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"success": True}
    result = await repo.unban_user("C123", "U999")
    assert result is True


@pytest.mark.asyncio
async def test_add_warning(repo, mock_convex_client):
    # Mock get_warning_count to return 0 (first warning)
    repo.get_warning_count = AsyncMock(return_value=0)
    mock_convex_client.post.return_value = {"data": {"groupId": "C123", "userId": "U999", "count": 1}}
    result = await repo.add_warning("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 1
    mock_convex_client.post.assert_called_once()


@pytest.mark.asyncio
async def test_get_warning_count(repo, mock_convex_client):
    mock_convex_client.get.return_value = {"data": {"count": 2}}
    result = await repo.get_warning_count("C123", "U999")
    assert result == 2


@pytest.mark.asyncio
async def test_mark_warning_read(repo, mock_convex_client):
    mock_convex_client.post.return_value = {"data": {"readByUser": True}}
    result = await repo.mark_warning_read("C123", "U999")
    assert result["readByUser"] is True