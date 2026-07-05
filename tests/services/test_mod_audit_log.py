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
    with patch("huggingface_hub.HfApi") as mock_api, patch("huggingface_hub.CommitScheduler") as mock_sched:
        yield mock_api, mock_sched


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


def test_mod_audit_log_hf_integration(mock_hf):
    from pathlib import Path
    mock_api_cls, mock_sched_cls = mock_hf

    with patch("src.services.mod_audit_log.os.makedirs"):
        log = ModAuditLog(token="test_token", repo_id="test/repo", local_path="./test_mod_audit")

        assert log.hf_token == "test_token"
        assert log.hf_repo_id == "test/repo"
        assert log.storage_path == Path("./test_mod_audit")
        assert log.hf_sync_interval == 5
        assert log.hf_squash_history is False
        assert log.hf_path_in_repo == "mod_audit"
        assert log._hf_enabled is True

        mock_api_cls.assert_called_once_with(token="test_token")
        mock_api_cls.return_value.create_repo.assert_called_once_with(
            repo_id="test/repo",
            repo_type="dataset",
            private=True,
            exist_ok=True,
        )
        mock_sched_cls.assert_called_once()

        log.close()
        mock_sched_cls.return_value.stop.assert_called_once()

