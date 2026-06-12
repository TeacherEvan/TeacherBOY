import pytest
from unittest.mock import AsyncMock
from src.services.ban_list_service import BanListService


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return BanListService(mock_repo)


@pytest.mark.asyncio
async def test_ban_user(service, mock_repo):
    mock_repo.ban_user.return_value = {"userId": "U999", "reason": "spam"}
    result = await service.ban_user("C123", "U999", "U456", "spam")
    assert result["userId"] == "U999"
    mock_repo.ban_user.assert_called_once_with("C123", "U999", "U456", "spam")


@pytest.mark.asyncio
async def test_is_banned(service, mock_repo):
    mock_repo.is_user_banned.return_value = True
    result = await service.is_banned("C123", "U999")
    assert result is True
    mock_repo.is_user_banned.assert_called_once_with("C123", "U999")


@pytest.mark.asyncio
async def test_is_not_banned(service, mock_repo):
    mock_repo.is_user_banned.return_value = False
    result = await service.is_banned("C123", "U999")
    assert result is False


@pytest.mark.asyncio
async def test_unban_user(service, mock_repo):
    mock_repo.unban_user.return_value = True
    result = await service.unban_user("C123", "U999")
    assert result is True
    mock_repo.unban_user.assert_called_once_with("C123", "U999")


@pytest.mark.asyncio
async def test_get_ban_list(service, mock_repo):
    mock_repo.get_ban_list.return_value = [{"userId": "U1", "reason": "spam"}, {"userId": "U2", "reason": "harassment"}]
    result = await service.get_ban_list("C123")
    assert len(result) == 2
    assert result[0]["userId"] == "U1"
    mock_repo.get_ban_list.assert_called_once_with("C123")


@pytest.mark.asyncio
async def test_get_ban_list_empty(service, mock_repo):
    mock_repo.get_ban_list.return_value = []
    result = await service.get_ban_list("C123")
    assert result == []