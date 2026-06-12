import pytest
from unittest.mock import AsyncMock
from src.services.warning_service import WarningService


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return WarningService(mock_repo)


@pytest.mark.asyncio
async def test_warn_user_first_strike(service, mock_repo):
    mock_repo.add_warning.return_value = {"count": 1}
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 1
    assert result["should_ban"] is False
    mock_repo.add_warning.assert_called_once_with("C123", "U999", "U456", "inappropriate")


@pytest.mark.asyncio
async def test_warn_user_second_strike(service, mock_repo):
    mock_repo.add_warning.return_value = {"count": 2}
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 2
    assert result["should_ban"] is False


@pytest.mark.asyncio
async def test_warn_user_third_strike_bans(service, mock_repo):
    mock_repo.add_warning.return_value = {"count": 3}
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 3
    assert result["should_ban"] is True


@pytest.mark.asyncio
async def test_warn_user_fourth_strike(service, mock_repo):
    mock_repo.add_warning.return_value = {"count": 4}
    result = await service.warn_user("C123", "U999", "U456", "inappropriate")
    assert result["count"] == 4
    assert result["should_ban"] is True


@pytest.mark.asyncio
async def test_get_warning_count(service, mock_repo):
    mock_repo.get_warning_count.return_value = 2
    count = await service.get_warning_count("C123", "U999")
    assert count == 2
    mock_repo.get_warning_count.assert_called_once_with("C123", "U999")


@pytest.mark.asyncio
async def test_mark_warning_read(service, mock_repo):
    mock_repo.mark_warning_read.return_value = {"readByUser": True}
    result = await service.mark_warning_read("C123", "U999")
    assert result["readByUser"] is True
    mock_repo.mark_warning_read.assert_called_once_with("C123", "U999")


@pytest.mark.asyncio
async def test_get_warnings(service, mock_repo):
    mock_repo.get_warnings.return_value = [{"userId": "U1", "count": 2}, {"userId": "U2", "count": 1}]
    result = await service.get_warnings("C123")
    assert len(result) == 2
    mock_repo.get_warnings.assert_called_once_with("C123")