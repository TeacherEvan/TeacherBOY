# tests/services/test_mod_mode_service.py
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.services.mod_mode_service import ModModeService


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly (not a coroutine)."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_repo():
    return MagicMock(spec=["get_mod_mode_state", "set_mod_mode_state", "deactivate_mod_mode"])


@pytest.fixture
def service(mock_repo):
    return ModModeService(mock_repo)


@pytest.mark.asyncio
async def test_activate_mod_mode_all(service, mock_repo):
    mock_repo.set_mod_mode_state = _make_async_mock({"mode": "all", "activatedBy": "U456", "isActive": True})
    result = await service.activate_mod_mode("C123", "U456", "all")
    assert result["mode"] == "all"
    assert result["activatedBy"] == "U456"
    mock_repo.set_mod_mode_state.assert_called_once_with(
        group_id="C123", mode="all", activated_by="U456", special_user_id=None
    )


@pytest.mark.asyncio
async def test_activate_mod_mode_special(service, mock_repo):
    mock_repo.set_mod_mode_state = _make_async_mock(
        {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    )
    result = await service.activate_mod_mode("C123", "U456", "special", "U789")
    assert result["mode"] == "special"
    assert result["specialUserId"] == "U789"
    mock_repo.set_mod_mode_state.assert_called_once_with(
        group_id="C123", mode="special", activated_by="U456", special_user_id="U789"
    )


@pytest.mark.asyncio
async def test_is_mod_mode_active(service, mock_repo):
    mock_repo.get_mod_mode_state = _make_async_mock({"isActive": True, "mode": "all"})
    result = await service.is_mod_mode_active("C123")
    assert result is True


@pytest.mark.asyncio
async def test_get_mod_mode_info(service, mock_repo):
    mock_repo.get_mod_mode_state = _make_async_mock(
        {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    )
    info = await service.get_mod_mode_info("C123")
    assert info["mode"] == "special"
    assert info["special_user_id"] == "U789"


@pytest.mark.asyncio
async def test_is_user_allowed_in_special_mode(service, mock_repo):
    mock_repo.get_mod_mode_state = _make_async_mock(
        {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    )
    # Admin allowed
    assert await service.is_user_allowed("C123", "U456") is True
    # Special user allowed
    assert await service.is_user_allowed("C123", "U789") is True
    # Other user NOT allowed
    assert await service.is_user_allowed("C123", "U999") is False


@pytest.mark.asyncio
async def test_is_user_allowed_in_all_mode(service, mock_repo):
    mock_repo.get_mod_mode_state = _make_async_mock({"mode": "all", "activatedBy": "U456", "isActive": True})
    # Everyone allowed in 'all' mode (banning handled separately)
    assert await service.is_user_allowed("C123", "U999") is True


@pytest.mark.asyncio
async def test_deactivate_mod_mode(service, mock_repo):
    mock_repo.deactivate_mod_mode = _make_async_mock(True)
    result = await service.deactivate_mod_mode("C123")
    assert result is True


@pytest.mark.asyncio
async def test_activate_mod_mode_invalid_mode(service):
    with pytest.raises(ValueError, match="Invalid mode: invalid"):
        await service.activate_mod_mode("C123", "U456", "invalid")


@pytest.mark.asyncio
async def test_activate_mod_mode_special_missing_user(service):
    with pytest.raises(ValueError, match="special_user_id required"):
        await service.activate_mod_mode("C123", "U456", "special")
