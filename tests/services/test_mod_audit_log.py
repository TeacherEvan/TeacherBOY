# tests/services/test_mod_audit_log.py
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.services.mod_audit_log import ModAuditLog


def _make_async_mock(return_value):
    """Create an AsyncMock that returns the value directly (not a coroutine)."""
    mock = AsyncMock()
    mock.return_value = return_value
    return mock


@pytest.fixture
def mock_hf():
    with patch("src.services.mod_audit_log.HfApi") as mock:
        yield mock


@pytest.fixture
def audit_log(mock_hf):
    # Mock os.makedirs to avoid filesystem operations
    with patch("src.services.mod_audit_log.os.makedirs"):
        with patch("src.services.mod_audit_log.open", MagicMock()):
            log = ModAuditLog(token="test_token", repo_id="test/repo")
            yield log


@pytest.mark.asyncio
async def test_log_kick(audit_log):
    with patch("src.services.mod_audit_log.open", MagicMock()):
        await audit_log.log_kick("C123", "U999", "U456", "spam")


@pytest.mark.asyncio
async def test_log_warn(audit_log):
    with patch("src.services.mod_audit_log.open", MagicMock()):
        await audit_log.log_warn("C123", "U999", "U456", "inappropriate", 1)


@pytest.mark.asyncio
async def test_log_ban(audit_log):
    with patch("src.services.mod_audit_log.open", MagicMock()):
        await audit_log.log_ban("C123", "U999", "U456", "spam")


@pytest.mark.asyncio
async def test_log_mode_change(audit_log):
    with patch("src.services.mod_audit_log.open", MagicMock()):
        await audit_log.log_mode_change("C123", "U456", "all", True)
