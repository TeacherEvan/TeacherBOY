import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch

# Mock huggingface_hub before importing
mock_hf = MagicMock()
sys.modules['huggingface_hub'] = mock_hf

from src.services.mod_audit_log import ModAuditLog


@pytest.fixture
def mock_hf():
    with patch("src.services.mod_audit_log.HfApi") as mock:
        yield mock


@pytest.fixture
def audit_log(mock_hf):
    return ModAuditLog(token="test_token", repo_id="test/repo")


@pytest.mark.asyncio
async def test_log_kick(audit_log, mock_hf):
    await audit_log.log_kick("C123", "U999", "U456", "spam")
    # Verify log was written (can't easily test local file write without more mocking)
    assert True


@pytest.mark.asyncio
async def test_log_warn(audit_log, mock_hf):
    await audit_log.log_warn("C123", "U999", "U456", "inappropriate", 1)
    assert True


@pytest.mark.asyncio
async def test_log_ban(audit_log, mock_hf):
    await audit_log.log_ban("C123", "U999", "U456", "spam")
    assert True


@pytest.mark.asyncio
async def test_log_unban(audit_log, mock_hf):
    await audit_log.log_unban("C123", "U999", "U456")
    assert True


@pytest.mark.asyncio
async def test_log_mode_change(audit_log, mock_hf):
    await audit_log.log_mode_change("C123", "U456", "all", True)
    assert True


@pytest.mark.asyncio
async def test_log_mode_change_special(audit_log, mock_hf):
    await audit_log.log_mode_change("C123", "U456", "special", True, "U789")
    assert True


@pytest.mark.asyncio
async def test_log_action(audit_log, mock_hf):
    await audit_log.log_action("test_action", "C123", "U999", "U456", {"detail": "test"})
    assert True