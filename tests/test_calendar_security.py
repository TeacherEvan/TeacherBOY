"""
Tests for Calendar Security Features

This test suite validates:
- Cross-chat isolation
- Role-based access control (RBAC)
- Encryption at rest
- Rate limiting
- Input validation and sanitization
- Audit logging
"""

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from src.services.calendar_access_control import CalendarAccessControl, CalendarRole
from src.services.calendar_service import CalendarService
from src.services.calendar_validator import CalendarValidator
from src.services.rate_limiter import RateLimiter

# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def calendar_service(tmp_path):
    """Calendar service without encryption."""
    return CalendarService(
        hf_token=None,
        hf_repo_id=None,
        local_storage_path=str(tmp_path / "calendar_data"),
        encryption_key=None,
    )


@pytest.fixture
def encrypted_calendar_service(tmp_path):
    """Calendar service with encryption."""
    # Generate a test encryption key (Fernet compatible)
    import base64
    import os

    test_key = base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8")

    return CalendarService(
        hf_token=None,
        hf_repo_id=None,
        local_storage_path=str(tmp_path / "calendar_encrypted"),
        encryption_key=test_key,
    )


@pytest.fixture
def access_control():
    """Calendar access control instance."""
    return CalendarAccessControl()


@pytest.fixture
def validator():
    """Calendar validator instance."""
    return CalendarValidator()


@pytest.fixture
def rate_limiter():
    """Rate limiter instance."""
    return RateLimiter()


# ============================================================================
# Cross-Chat Isolation Tests
# ============================================================================


def test_chat_isolation_get_events(calendar_service):
    """Test that events are isolated by chat_id."""
    # Add events to different chats
    event1 = calendar_service.add_event(
        user_id="U001",
        chat_id="group_A",
        title="Group A Event",
        event_date=date.today() + timedelta(days=1),
    )

    event2 = calendar_service.add_event(
        user_id="U002",
        chat_id="group_B",
        title="Group B Event",
        event_date=date.today() + timedelta(days=2),
    )

    # Get events for group_A - should only see event1
    group_a_events = calendar_service.get_chat_events("group_A")
    assert len(group_a_events) == 1
    assert group_a_events[0].event_id == event1.event_id

    # Get events for group_B - should only see event2
    group_b_events = calendar_service.get_chat_events("group_B")
    assert len(group_b_events) == 1
    assert group_b_events[0].event_id == event2.event_id


def test_private_dm_isolation(calendar_service):
    """Test that private DM events are isolated from groups."""
    # User creates event in private DM
    dm_event = calendar_service.add_event(
        user_id="U001",
        chat_id="user_U001",
        title="Private Event",
        event_date=date.today() + timedelta(days=1),
    )

    # Same user creates event in group
    group_event = calendar_service.add_event(
        user_id="U001",
        chat_id="group_A",
        title="Group Event",
        event_date=date.today() + timedelta(days=2),
    )

    # DM events should not appear in group
    group_events = calendar_service.get_chat_events("group_A")
    assert len(group_events) == 1
    assert group_events[0].event_id == group_event.event_id

    # Group events should not appear in DM
    dm_events = calendar_service.get_chat_events("user_U001")
    assert len(dm_events) == 1
    assert dm_events[0].event_id == dm_event.event_id


# ============================================================================
# RBAC Tests
# ============================================================================


@pytest.mark.asyncio
async def test_admin_role_bypass(access_control):
    """Test that admins have access to all chats."""
    with patch.object(access_control, "_is_admin", return_value=True):
        role = await access_control.get_user_role(
            user_id="ADMIN001",
            chat_id="group_A",
        )
        assert role == CalendarRole.ADMIN


@pytest.mark.asyncio
async def test_owner_role_detection(access_control):
    """Test that event owners are detected correctly."""
    role = await access_control.get_user_role(
        user_id="U001",
        chat_id="group_A",
        event_owner_id="U001",
    )
    assert role == CalendarRole.OWNER


@pytest.mark.asyncio
async def test_dm_member_access(access_control):
    """Test that user has member access to their own DM."""
    role = await access_control.get_user_role(
        user_id="U001",
        chat_id="user_U001",
    )
    assert role == CalendarRole.MEMBER


@pytest.mark.asyncio
async def test_dm_non_member_access(access_control):
    """Test that other users cannot access private DMs."""
    role = await access_control.get_user_role(
        user_id="U002",
        chat_id="user_U001",
    )
    assert role == CalendarRole.NON_MEMBER


@pytest.mark.asyncio
async def test_can_view_events_permission(access_control):
    """Test view events permission checking."""
    # Admin can view
    with patch.object(access_control, "_is_admin", return_value=True):
        assert await access_control.can_view_events("ADMIN", "group_A")

    # Member can view their own DM
    assert await access_control.can_view_events("U001", "user_U001")

    # Non-member cannot view other's DM
    assert not await access_control.can_view_events("U002", "user_U001")


@pytest.mark.asyncio
async def test_can_modify_event_permission(access_control):
    """Test modify event permission checking."""
    # Owner can modify
    can_modify = await access_control.can_modify_event(
        user_id="U001",
        chat_id="group_A",
        event_owner_id="U001",
    )
    assert can_modify

    # Non-owner cannot modify
    can_modify = await access_control.can_modify_event(
        user_id="U002",
        chat_id="group_A",
        event_owner_id="U001",
    )
    assert not can_modify


# ============================================================================
# Encryption Tests
# ============================================================================


def test_encryption_enabled(encrypted_calendar_service):
    """Test that encryption is properly initialized."""
    assert encrypted_calendar_service._cipher_suite is not None
    assert encrypted_calendar_service._encryption_key is not None


def test_encrypted_storage_cycle(encrypted_calendar_service, tmp_path):
    """Test that data is encrypted when saved and decrypted when loaded."""
    encrypted_calendar_service.local_storage_path = tmp_path

    # Add event
    encrypted_calendar_service.add_event(
        user_id="U001",
        chat_id="group_A",
        title="Encrypted Event",
        event_date=date.today() + timedelta(days=1),
    )

    # Verify file exists and is encrypted (not plain JSON)
    calendar_file = tmp_path / "calendar_events.json"
    assert calendar_file.exists()

    # Read raw file - should be encrypted bytes, not JSON
    with open(calendar_file, "rb") as f:
        raw_content = f.read()

    # Should not be valid JSON
    import json

    with pytest.raises(json.JSONDecodeError):
        import json

        json.loads(raw_content)

    # Create new service instance to test decryption on load
    new_service = CalendarService(
        hf_token=None,
        hf_repo_id=None,
        local_storage_path=str(tmp_path),
        encryption_key=encrypted_calendar_service._encryption_key,
    )

    # Should successfully decrypt and load event
    loaded_events = new_service.get_chat_events("group_A")
    assert len(loaded_events) == 1
    assert loaded_events[0].title == "Encrypted Event"


# ============================================================================
# Rate Limiting Tests
# ============================================================================


def test_calendar_rate_limit_user(rate_limiter):
    """Test user-based calendar rate limiting."""
    user_id = "U001"
    chat_id = "group_A"

    # First 10 operations should succeed
    for _i in range(10):
        assert rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin=False)

    # 11th operation should fail (limit is 10/minute)
    assert not rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin=False)


def test_calendar_rate_limit_chat(rate_limiter):
    """Test chat-based calendar rate limiting."""
    chat_id = "group_A"

    # Simulate 30 operations from different users (chat limit)
    for i in range(30):
        user_id = f"U{i:03d}"
        assert rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin=False)

    # 31st operation should fail (chat limit is 30/minute)
    assert not rate_limiter.is_calendar_operation_allowed("U999", chat_id, is_admin=False)


def test_calendar_rate_limit_admin_bypass(rate_limiter):
    """Test that admins bypass rate limits."""
    user_id = "ADMIN"
    chat_id = "group_A"

    # Admin should be able to exceed limits
    for _i in range(50):
        assert rate_limiter.is_calendar_operation_allowed(user_id, chat_id, is_admin=True)


# ============================================================================
# Input Validation Tests
# ============================================================================


def test_title_validation_empty(validator):
    """Test that empty titles are rejected."""
    valid, sanitized, error = validator.validate_title("")
    assert not valid
    assert "cannot be empty" in error


def test_title_validation_too_long(validator):
    """Test that overly long titles are rejected."""
    long_title = "A" * 300
    valid, sanitized, error = validator.validate_title(long_title)
    assert not valid
    assert "too long" in error


def test_title_validation_xss_prevention(validator):
    """Test that dangerous characters are removed."""
    malicious_title = "Event<script>alert('xss')</script>"
    valid, sanitized, error = validator.validate_title(malicious_title)
    assert valid
    assert "<" not in sanitized
    assert ">" not in sanitized
    assert "script" in sanitized  # Text remains, tags removed


def test_description_validation_truncation(validator):
    """Test that long descriptions are truncated."""
    long_desc = "A" * 1500
    valid, sanitized, error = validator.validate_description(long_desc)
    assert valid
    assert len(sanitized) == 1000  # Max length


def test_date_validation_past(validator):
    """Test that past dates are rejected."""
    past_date = date.today() - timedelta(days=1)
    valid, error = validator.validate_date(past_date)
    assert not valid
    assert "past" in error


def test_date_validation_too_far_future(validator):
    """Test that dates too far in future are rejected."""
    far_future = date.today() + timedelta(days=365 * 10)  # 10 years
    valid, error = validator.validate_date(far_future)
    assert not valid
    assert "5 years" in error


def test_reminder_days_validation(validator):
    """Test reminder days validation and sanitization."""
    # Invalid values should be filtered
    valid, sanitized, error = validator.validate_reminder_days([7, -1, 500, 3])
    assert valid
    assert sanitized == [0, 3, 7]  # -1 and 500 removed, 0 added


def test_complete_event_validation(validator):
    """Test complete event validation."""
    valid, data, error = validator.validate_event(
        title="Team Meeting", event_date=date.today() + timedelta(days=7), description="Discuss Q1 goals", reminder_days=[7, 1]
    )
    assert valid
    assert data["title"] == "Team Meeting"
    assert 0 in data["reminder_days"]  # Day-of reminder auto-added


# ============================================================================
# Audit Logging Tests
# ============================================================================


@pytest.mark.asyncio
async def test_audit_log_event_creation(calendar_service, monkeypatch):
    """Test that event creation is logged."""
    log_calls = []

    async def mock_log(**kwargs):
        log_calls.append(kwargs)

    class _MockHistoryLog:
        async def log(self, **kwargs):
            await mock_log(**kwargs)

    from src.services import calendar_service as calendar_service_module

    monkeypatch.setattr(calendar_service_module, "get_history_log", lambda: _MockHistoryLog())

    # Create event
    calendar_service.add_event(
        user_id="U001",
        chat_id="group_A",
        title="Test Event",
        event_date=date.today() + timedelta(days=1),
    )

    # Allow background task to run
    import asyncio

    await asyncio.sleep(0)

    # Verify log was called
    assert len(log_calls) > 0
    # Audit log is scheduled as a background task; ensure at least one call happened
    assert log_calls[0]["event_type"].value == "calendar_event_created"


# ============================================================================
# Edge Cases & Security
# ============================================================================


def test_sql_injection_prevention(validator):
    """Test that SQL injection attempts are sanitized."""
    malicious_title = "'; DROP TABLE events;--"
    valid, sanitized, error = validator.validate_title(malicious_title)
    assert valid
    assert "DROP" in sanitized  # Text preserved
    assert "'" not in sanitized  # Single quotes removed


def test_control_character_removal(validator):
    """Test that control characters are removed."""
    title_with_control = "Event\x00\x01\x1fTitle"
    valid, sanitized, error = validator.validate_title(title_with_control)
    assert valid
    assert "\x00" not in sanitized
    assert sanitized == "EventTitle"


def test_unicode_handling(validator):
    """Test that Unicode characters are preserved."""
    unicode_title = "กิจกรรม 活动 イベント 🎉"
    valid, sanitized, error = validator.validate_title(unicode_title)
    assert valid
    assert sanitized == unicode_title
