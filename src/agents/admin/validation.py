"""Validation schemas for admin commands using Pydantic."""

from pydantic import BaseModel, Field, field_validator


class AdminModelListArgs(BaseModel):
    """Arguments for /admin model list command."""

    vision_only: bool = False


class AdminModelVisionArgs(BaseModel):
    """Arguments for /admin model vision command."""

    pass


class AdminModelSetArgs(BaseModel):
    """Arguments for /admin model set <model_id> command."""

    model_id: str = Field(..., min_length=1, max_length=100)

    @field_validator("model_id")
    @classmethod
    def validate_model_id(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Model ID cannot be empty")
        return v


class AdminPurgeArgs(BaseModel):
    """Arguments for /admin purge command."""

    target: str | None = None  # chat_id or "all"
    confirm: bool = False


class AdminResetArgs(BaseModel):
    """Arguments for /admin reset command."""

    target: str | None = None  # chat_id or "all"
    confirm: bool = False


class AdminLeaveArgs(BaseModel):
    """Arguments for /admin leave command."""

    chat_id: str | None = None


class AdminSessionsArgs(BaseModel):
    """Arguments for /admin sessions command."""

    limit: int | None = Field(default=20, ge=1, le=100)


class AdminGroupsArgs(BaseModel):
    """Arguments for /admin groups command."""

    limit: int | None = Field(default=20, ge=1, le=100)


class AdminStatsArgs(BaseModel):
    """Arguments for /admin stats command."""

    detailed: bool = False


class AdminMemoryArgs(BaseModel):
    """Arguments for /admin memory command."""

    chat_id: str | None = None
    flush_mode: str | None = None
    days: int | None = Field(default=None, ge=1, le=365)
    dry_run: bool = True
    confirm: bool = False


# Valid model IDs for NOUS Portal
VALID_NOUS_MODELS = {
    "Hermes-3-Llama-3.1-70B",
    "Hermes-3-Llama-3.1-70B-Vision",
    "Hermes-3-Llama-3.1-8B",
    "Hermes-3-Llama-3.1-8B-Vision",
    "Nous-Hermes-2-Mixtral-8x7B-DPO",
}


def validate_nous_model(model_id: str) -> tuple[bool, str]:
    """Validate a NOUS model ID.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if model_id not in VALID_NOUS_MODELS:
        return False, f"Unknown model: {model_id}. Valid models: {', '.join(sorted(VALID_NOUS_MODELS))}"
    return True, ""


def validate_chat_id(chat_id: str) -> tuple[bool, str]:
    """Validate a chat ID format.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not chat_id:
        return False, "Chat ID cannot be empty"

    # Must start with user_, group_, or room_
    if not (chat_id.startswith("user_") or chat_id.startswith("group_") or chat_id.startswith("room_")):
        return False, "Chat ID must start with user_, group_, or room_"

    return True, ""


def validate_user_id(user_id: str) -> tuple[bool, str]:
    """Validate a LINE user ID format.

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not user_id:
        return False, "User ID cannot be empty"

    # LINE user IDs typically start with 'U' and are 33 characters
    if not user_id.startswith("U") or len(user_id) != 33:
        return False, "Invalid LINE user ID format"

    return True, ""
