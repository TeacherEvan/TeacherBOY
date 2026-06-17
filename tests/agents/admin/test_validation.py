"""Tests for admin command validation."""

import pytest

from src.agents.admin.validation import (
    VALID_NOUS_MODELS,
    AdminGroupsArgs,
    AdminLeaveArgs,
    AdminMemoryArgs,
    AdminModelSetArgs,
    AdminPurgeArgs,
    AdminResetArgs,
    AdminSessionsArgs,
    AdminStatsArgs,
    validate_chat_id,
    validate_nous_model,
    validate_user_id,
)


class TestAdminModelArgs:
    """Tests for model-related admin command arguments."""

    def test_model_set_valid_id(self):
        """Test valid model ID passes validation."""
        args = AdminModelSetArgs(model_id="Hermes-3-Llama-3.1-70B")
        assert args.model_id == "Hermes-3-Llama-3.1-70B"

    def test_model_set_empty_id_rejected(self):
        """Test empty model ID is rejected."""
        with pytest.raises(ValueError, match="String should have at least 1 character"):
            AdminModelSetArgs(model_id="")

    def test_model_set_whitespace_only_rejected(self):
        """Test whitespace-only model ID is rejected."""
        with pytest.raises(ValueError, match="Model ID cannot be empty"):
            AdminModelSetArgs(model_id="   ")

    def test_model_set_whitespace_stripped(self):
        """Test model ID with surrounding whitespace is trimmed."""
        args = AdminModelSetArgs(model_id="  Hermes-3-Llama-3.1-70B  ")
        assert args.model_id == "Hermes-3-Llama-3.1-70B"


class TestValidateNousModel:
    """Tests for NOUS model validation."""

    def test_valid_models(self):
        """Test all known valid models pass validation."""
        for model_id in VALID_NOUS_MODELS:
            is_valid, error = validate_nous_model(model_id)
            assert is_valid, f"Model {model_id} should be valid: {error}"
            assert error == ""

    def test_invalid_model_rejected(self):
        """Test unknown model ID is rejected."""
        is_valid, error = validate_nous_model("invalid-model")
        assert not is_valid
        assert "Unknown model" in error

    def test_case_sensitivity(self):
        """Test model ID validation is case-sensitive."""
        is_valid, error = validate_nous_model("hermes-3-llama-3.1-70b")
        assert not is_valid


class TestValidateChatId:
    """Tests for chat ID validation."""

    def test_valid_user_chat_id(self):
        """Test valid user chat ID passes."""
        is_valid, error = validate_chat_id("user_U1234567890abcdef")
        assert is_valid
        assert error == ""

    def test_valid_group_chat_id(self):
        """Test valid group chat ID passes."""
        is_valid, error = validate_chat_id("group_C1234567890abcdef")
        assert is_valid
        assert error == ""

    def test_valid_room_chat_id(self):
        """Test valid room chat ID passes."""
        is_valid, error = validate_chat_id("room_R1234567890abcdef")
        assert is_valid
        assert error == ""

    def test_empty_chat_id_rejected(self):
        """Test empty chat ID is rejected."""
        is_valid, error = validate_chat_id("")
        assert not is_valid
        assert "cannot be empty" in error

    def test_invalid_prefix_rejected(self):
        """Test chat ID with invalid prefix is rejected."""
        is_valid, error = validate_chat_id("invalid_123")
        assert not is_valid
        assert "must start with user_, group_, or room_" in error


class TestValidateUserId:
    """Tests for LINE user ID validation."""

    def test_valid_user_id(self):
        """Test valid LINE user ID passes."""
        # LINE user IDs are typically 'U' + 32 hex chars = 33 chars
        user_id = "U" + "a" * 32
        is_valid, error = validate_user_id(user_id)
        assert is_valid
        assert error == ""

    def test_empty_user_id_rejected(self):
        """Test empty user ID is rejected."""
        is_valid, error = validate_user_id("")
        assert not is_valid
        assert "cannot be empty" in error

    def test_wrong_prefix_rejected(self):
        """Test user ID without 'U' prefix is rejected."""
        is_valid, error = validate_user_id("X" + "a" * 32)
        assert not is_valid
        assert "Invalid LINE user ID format" in error

    def test_wrong_length_rejected(self):
        """Test user ID with wrong length is rejected."""
        is_valid, error = validate_user_id("U" + "a" * 31)  # 32 chars total
        assert not is_valid
        assert "Invalid LINE user ID format" in error

    def test_way_too_long_rejected(self):
        """Test user ID that's way too long is rejected."""
        is_valid, error = validate_user_id("U" + "a" * 100)
        assert not is_valid
        assert "Invalid LINE user ID format" in error


class TestAdminPurgeArgs:
    """Tests for purge command arguments."""

    def test_default_values(self):
        """Test default argument values."""
        args = AdminPurgeArgs()
        assert args.target is None
        assert args.confirm is False

    def test_explicit_values(self):
        """Test explicit argument values."""
        args = AdminPurgeArgs(target="group_C123", confirm=True)
        assert args.target == "group_C123"
        assert args.confirm is True


class TestAdminResetArgs:
    """Tests for reset command arguments."""

    def test_default_values(self):
        """Test default argument values."""
        args = AdminResetArgs()
        assert args.target is None
        assert args.confirm is False


class TestAdminLeaveArgs:
    """Tests for leave command arguments."""

    def test_default_values(self):
        """Test default argument values."""
        args = AdminLeaveArgs()
        assert args.chat_id is None


class TestAdminSessionsArgs:
    """Tests for sessions command arguments."""

    def test_default_limit(self):
        """Test default limit value."""
        args = AdminSessionsArgs()
        assert args.limit == 20

    def test_limit_bounds(self):
        """Test limit bounds validation."""
        # Valid bounds
        args = AdminSessionsArgs(limit=1)
        assert args.limit == 1

        args = AdminSessionsArgs(limit=100)
        assert args.limit == 100

        # Invalid bounds
        with pytest.raises(ValueError):
            AdminSessionsArgs(limit=0)

        with pytest.raises(ValueError):
            AdminSessionsArgs(limit=101)


class TestAdminGroupsArgs:
    """Tests for groups command arguments."""

    def test_default_limit(self):
        """Test default limit value."""
        args = AdminGroupsArgs()
        assert args.limit == 20


class TestAdminStatsArgs:
    """Tests for stats command arguments."""

    def test_default_detailed(self):
        """Test default detailed value."""
        args = AdminStatsArgs()
        assert args.detailed is False


class TestAdminMemoryArgs:
    """Tests for memory command arguments."""

    def test_default_values(self):
        """Test default argument values."""
        args = AdminMemoryArgs()
        assert args.chat_id is None
        assert args.flush_mode is None
        assert args.days is None
        assert args.dry_run is True
        assert args.confirm is False

    def test_days_bounds(self):
        """Test days bounds validation."""
        with pytest.raises(ValueError):
            AdminMemoryArgs(days=0)

        with pytest.raises(ValueError):
            AdminMemoryArgs(days=366)

        # Valid
        args = AdminMemoryArgs(days=1)
        assert args.days == 1

        args = AdminMemoryArgs(days=365)
        assert args.days == 365
