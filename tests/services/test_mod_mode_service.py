import pytest
from unittest.mock import AsyncMock, MagicMock
from src.services.mod_mode_service import ModModeService


@pytest.fixture
def mock_repo():
    return AsyncMock()


@pytest.fixture
def service(mock_repo):
    return ModModeService(mock_repo)


@pytest.mark.asyncio
async def test_activate_mod_mode_all(service, mock_repo):
    mock_repo.set_mod_mode_state.return_value = {"mode": "all", "activatedBy": "U456", "isActive": True}
    result = await service.activate_mod_mode("C123", "U456", "all")
    assert result["mode"] == "all"
    assert result["activatedBy"] == "U456"
    mock_repo.set_mod_mode_state.assert_called_once_with(group_id="C123", mode="all", activated_by="U456", special_user_id=None)


@pytest.mark.asyncio
async def test_activate_mod_mode_special(service, mock_repo):
    mock_repo.set_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    result = await service.activate_mod_mode("C123", "U456", "special", "U789")
    assert result["mode"] == "special"
    assert result["specialUserId"] == "U789"
    mock_repo.set_mod_mode_state.assert_called_once_with(group_id="C123", mode="special", activated_by="U456", special_user_id="U789")


@pytest.mark.asyncio
async def test_activate_mod_mode_invalid_mode(service):
    with pytest.raises(ValueError, match="Invalid mode"):
        await service.activate_mod_mode("C123", "U456", "invalid")


@pytest.mark.asyncio
async def test_activate_mod_mode_special_requires_user(service):
    with pytest.raises(ValueError, match="special_user_id required"):
        await service.activate_mod_mode("C123", "U456", "special")


@pytest.mark.asyncio
async def test_is_mod_mode_active(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"isActive": True, "mode": "all"}
    result = await service.is_mod_mode_active("C123")
    assert result is True


@pytest.mark.asyncio
async def test_is_mod_mode_not_active(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = None
    result = await service.is_mod_mode_active("C123")
    assert result is False


@pytest.mark.asyncio
async def test_get_mod_mode_info(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    info = await service.get_mod_mode_info("C123")
    assert info["mode"] == "special"
    assert info["special_user_id"] == "U789"


@pytest.mark.asyncio
async def test_get_mod_mode_info_none(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = None
    info = await service.get_mod_mode_info("C123")
    assert info is None


@pytest.mark.asyncio
async def test_is_user_allowed_in_special_mode(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    assert await service.is_user_allowed("C123", "U456") is True
    assert await service.is_user_allowed("C123", "U789") is True
    assert await service.is_user_allowed("C123", "U999") is False


@pytest.mark.asyncio
async def test_is_user_allowed_in_all_mode(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "all", "activatedBy": "U456", "isActive": True}
    assert await service.is_user_allowed("C123", "U999") is True


@pytest.mark.asyncio
async def test_is_user_allowed_no_mod_mode(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = None
    assert await service.is_user_allowed("C123", "U999") is True


@pytest.mark.asyncio
async def test_deactivate_mod_mode(service, mock_repo):
    mock_repo.deactivate_mod_mode.return_value = True
    result = await service.deactivate_mod_mode("C123")
    assert result is True


@pytest.mark.asyncio
async def test_set_special_user(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "special", "activatedBy": "U456", "specialUserId": "U789", "isActive": True}
    mock_repo.set_mod_mode_state.return_value = {"mode": "special", "specialUserId": "U888"}
    result = await service.set_special_user("C123", "U888")
    assert result["specialUserId"] == "U888"


@pytest.mark.asyncio
async def test_set_special_user_not_in_special_mode(service, mock_repo):
    mock_repo.get_mod_mode_state.return_value = {"mode": "all", "activatedBy": "U456", "isActive": True}
    with pytest.raises(ValueError, match="not in 'special' mode"):
        await service.set_special_user("C123", "U888")