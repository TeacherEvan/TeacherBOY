from datetime import datetime, timedelta

import pytest

from src.services.admin_confirmation_service import (
    AdminConfirmationService,
    PendingAdminAction,
)


class MutableMetadataBox:
    def __init__(self, tags: list[str]):
        self.tags = list(tags)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, MutableMetadataBox) and self.tags == other.tags


class SelfCopyBox:
    def __init__(self, items: list[str]):
        self.items = list(items)

    def __deepcopy__(self, memo: dict[int, object]) -> "SelfCopyBox":
        return self

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SelfCopyBox) and self.items == other.items


class RaisingCopyBox:
    def __init__(self, items: list[str]):
        self.items = list(items)

    def __deepcopy__(self, memo: dict[int, object]) -> "RaisingCopyBox":
        raise TypeError("cannot deepcopy")

    def __eq__(self, other: object) -> bool:
        return isinstance(other, RaisingCopyBox) and self.items == other.items


def test_create_records_source_target_action_and_preview_metadata():
    service = AdminConfirmationService(default_ttl_seconds=300)

    pending = service.create(
        action="purge",
        requested_by_user_id="U-admin",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    assert pending.action == "purge"
    assert pending.requested_by_user_id == "U-admin"
    assert pending.requested_from_chat_id == "group_123"
    assert pending.payload == {"chat_id": "group_123"}
    assert pending.preview_text == "Purge group_123 conversation history"
    assert pending.created_at < pending.expires_at
    assert pending.expires_at - pending.created_at == timedelta(seconds=300)
    assert isinstance(pending.revision, str)
    assert pending.revision


def test_confirm_rejects_wrong_user():
    service = AdminConfirmationService()
    pending = service.create(
        action="leave",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"kind": "group", "target_id": "C123"},
        preview_text="Leave group C123",
    )

    confirmed, message = service.confirm(pending.token, "U-other")

    assert confirmed is None
    assert message == "❌ This token belongs to a different admin."
    assert service.get(pending.token) == pending


def test_confirm_rejects_expired_pending_action():
    service = AdminConfirmationService(default_ttl_seconds=1)
    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        ttl_seconds=-1,
    )

    confirmed, message = service.confirm(pending.token, "U-owner")

    assert confirmed is None
    assert message == "❌ Unknown or expired confirmation token."
    assert service.get(pending.token) is None


def test_create_preserves_legacy_default_behavior_for_duplicate_pending_action():
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    duplicate = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    assert duplicate.token != original.token
    assert service.get(original.token) == original
    assert service.get(duplicate.token) == duplicate
    assert service.count_pending() == 2


def test_create_explicitly_rejects_duplicate_pending_action_for_same_user_target_and_action():
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    rejected = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        on_duplicate="reject",
    )

    assert rejected == original
    assert service.get(original.token) == original
    assert service.count_pending() == 1


def test_create_reject_duplicate_returns_defensive_copy_of_stored_pending_action():
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123", "targets": ["A", "B"]},
        preview_text="Purge group_123 conversation history",
    )

    rejected = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123", "targets": ["A", "B"]},
        preview_text="Purge group_123 conversation history",
        on_duplicate="reject",
    )

    rejected.payload["chat_id"] = "group_999"
    rejected.payload["targets"].append("C")

    assert service.get(original.token).payload == {
        "chat_id": "group_123",
        "targets": ["A", "B"],
    }


def test_create_explicitly_replaces_duplicate_pending_action_for_same_user_target_and_action():
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    replacement = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        on_duplicate="replace",
    )

    assert replacement.token != original.token
    assert service.get(original.token) is None
    assert service.get(replacement.token) == replacement
    assert service.count_pending() == 1


def test_create_treats_different_requested_from_chat_id_as_distinct_duplicate_identity():
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        on_duplicate="reject",
    )

    different_chat = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_999",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        on_duplicate="reject",
    )

    assert different_chat.token != original.token
    assert service.get(original.token) == original
    assert service.get(different_chat.token) == different_chat
    assert service.count_pending() == 2


@pytest.mark.parametrize(
    ("preview_text", "preview_fields"),
    [
        ("Purge group_123 now", None),
        ("Purge group_123 conversation history", {"scope": "full"}),
    ],
)
def test_create_treats_different_preview_metadata_as_distinct_duplicate_identity(
    preview_text: str,
    preview_fields: dict[str, str] | None,
):
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields={"scope": "summary"},
        on_duplicate="reject",
    )

    different_preview = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text=preview_text,
        preview_fields=preview_fields,
        on_duplicate="reject",
    )

    assert different_preview.token != original.token
    assert service.get(original.token) == original
    assert service.get(different_preview.token) == different_preview
    assert service.count_pending() == 2


def test_create_replace_removes_all_matching_legacy_duplicates():
    service = AdminConfirmationService()
    first = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields={"scope": "summary"},
    )
    second = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields={"scope": "summary"},
    )
    third = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields={"scope": "summary"},
    )

    replacement = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields={"scope": "summary"},
        on_duplicate="replace",
    )

    assert service.get(first.token) is None
    assert service.get(second.token) is None
    assert service.get(third.token) is None
    assert service.get(replacement.token) == replacement
    assert service.count_pending() == 1


def test_create_rejects_invalid_on_duplicate_value():
    service = AdminConfirmationService()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    with pytest.raises(ValueError, match="Invalid on_duplicate value"):
        service.create(
            action="purge",
            requested_by_user_id="U-owner",
            requested_from_chat_id="group_123",
            payload={"chat_id": "group_123"},
            preview_text="Purge group_123 conversation history",
            on_duplicate="merge",
        )

    assert service.get(original.token) == original
    assert service.count_pending() == 1


def test_create_handles_non_json_serializable_duplicate_payload_values():
    service = AdminConfirmationService()
    marker = object()
    original = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"marker": marker},
        preview_text="Purge group_123 conversation history",
    )

    duplicate = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"marker": marker},
        preview_text="Purge group_123 conversation history",
        on_duplicate="reject",
    )

    assert duplicate == original
    assert service.count_pending() == 1


def test_create_copies_and_isolates_preview_fields():
    service = AdminConfirmationService()
    preview_fields = {"chat_id": "group_123", "action": "purge"}

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields=preview_fields,
    )

    preview_fields["chat_id"] = "group_999"

    assert dict(pending.preview_fields) == {
        "chat_id": "group_123",
        "action": "purge",
    }
    with pytest.raises(TypeError):
        pending.preview_fields["chat_id"] = "group_mutated"  # type: ignore[index]


def test_create_snapshots_payload_to_isolate_pending_action_from_caller_mutation():
    service = AdminConfirmationService()
    payload = {"chat_id": "group_123", "targets": ["A", "B"]}

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload=payload,
        preview_text="Purge group_123 conversation history",
    )

    payload["chat_id"] = "group_999"
    payload["targets"].append("C")

    assert pending.payload == {"chat_id": "group_123", "targets": ["A", "B"]}
    assert service.get(pending.token).payload == {
        "chat_id": "group_123",
        "targets": ["A", "B"],
    }


def test_create_snapshots_nested_custom_mutable_payload_metadata():
    service = AdminConfirmationService()
    metadata_box = MutableMetadataBox(["A", "B"])
    payload = {
        "chat_id": "group_123",
        "metadata": {"box": metadata_box},
    }

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload=payload,
        preview_text="Purge group_123 conversation history",
    )

    metadata_box.tags.append("C")

    assert pending.payload["metadata"]["box"] == MutableMetadataBox(["A", "B"])
    assert pending.payload["metadata"]["box"] is not metadata_box


def test_create_deepcopies_unsupported_mutable_builtin_payload_values():
    service = AdminConfirmationService()
    payload = {
        "chat_id": "group_123",
        "raw_bytes": bytearray(b"AB"),
    }

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload=payload,
        preview_text="Purge group_123 conversation history",
    )

    payload["raw_bytes"].extend(b"C")
    fetched = service.get(pending.token)
    fetched.payload["raw_bytes"].extend(b"D")

    assert pending.payload["raw_bytes"] == bytearray(b"AB")
    assert service.get(pending.token).payload == {
        "chat_id": "group_123",
        "raw_bytes": bytearray(b"AB"),
    }


def test_create_snapshots_custom_payload_value_when_deepcopy_returns_self():
    service = AdminConfirmationService()
    box = SelfCopyBox(["A"])

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123", "box": box},
        preview_text="Purge group_123 conversation history",
    )

    box.items.append("B")

    assert pending.payload == {
        "chat_id": "group_123",
        "box": SelfCopyBox(["A"]),
    }
    assert pending.payload["box"] is not box
    assert service.get(pending.token).payload == {
        "chat_id": "group_123",
        "box": SelfCopyBox(["A"]),
    }
    assert service.get(pending.token).payload["box"] is not box


def test_create_snapshots_preview_fields_when_custom_value_deepcopy_raises():
    service = AdminConfirmationService()
    box = RaisingCopyBox(["A"])

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        preview_fields={"box": box},
    )

    box.items.append("B")
    stored = service.get(pending.token)

    assert dict(pending.preview_fields) == {"box": RaisingCopyBox(["A"])}
    assert pending.preview_fields["box"] is not box
    assert dict(stored.preview_fields) == {"box": RaisingCopyBox(["A"])}
    assert stored.preview_fields["box"] is not box


def test_payload_cannot_be_mutated_through_returned_pending_action_or_service_get():
    service = AdminConfirmationService()

    pending = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123", "targets": ["A", "B"]},
        preview_text="Purge group_123 conversation history",
    )

    stored = service.get(pending.token)

    pending.payload["chat_id"] = "group_999"
    pending.payload["targets"].append("C")
    stored.payload["chat_id"] = "group_888"
    stored.payload["targets"].append("D")

    assert service.get(pending.token).payload == {
        "chat_id": "group_123",
        "targets": ["A", "B"],
    }


def test_pending_actions_are_not_visible_across_service_instances():
    original = AdminConfirmationService()
    pending = original.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    fresh = AdminConfirmationService()

    assert original.get(pending.token) == pending
    assert fresh.get(pending.token) is None
    assert fresh.count_pending() == 0


def test_pending_admin_action_supports_legacy_direct_instantiation_with_defaults():
    pending = PendingAdminAction(
        token="tok-123",
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
    )

    assert pending.preview_text is None
    assert dict(pending.preview_fields) == {}
    assert pending.created_at <= pending.expires_at
    assert pending.revision == ""


def test_pending_admin_action_preserves_legacy_seven_positional_arguments():
    created_at = datetime(2026, 5, 31, 12, 0, 0)
    expires_at = created_at + timedelta(minutes=5)

    pending = PendingAdminAction(
        "tok-legacy",
        "purge",
        "U-owner",
        "group_123",
        {"chat_id": "group_123"},
        created_at,
        expires_at,
    )

    assert pending.created_at == created_at
    assert pending.expires_at == expires_at
    assert pending.preview_text is None
    assert dict(pending.preview_fields) == {}
    assert pending.revision == ""


def test_create_exposes_nonce_alias_for_revision():
    service = AdminConfirmationService(default_ttl_seconds=300)

    pending = service.create(
        action="purge",
        requested_by_user_id="U-admin",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    assert pending.revision
    assert pending.nonce == pending.revision


def test_create_ignores_expired_duplicate_before_creating_new_request():
    service = AdminConfirmationService(default_ttl_seconds=300)
    expired = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
        ttl_seconds=-1,
    )

    replacement = service.create(
        action="purge",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"chat_id": "group_123"},
        preview_text="Purge group_123 conversation history",
    )

    assert replacement.token != expired.token
    assert service.get(expired.token) is None
    assert service.get(replacement.token) == replacement
    assert service.count_pending() == 1


def test_cancel_removes_only_matching_users_pending_action():
    service = AdminConfirmationService()
    owners_pending = service.create(
        action="leave",
        requested_by_user_id="U-owner",
        requested_from_chat_id="group_123",
        payload={"kind": "group", "target_id": "C123"},
        preview_text="Leave group C123",
    )
    others_pending = service.create(
        action="purge",
        requested_by_user_id="U-other",
        requested_from_chat_id="group_999",
        payload={"chat_id": "group_999"},
        preview_text="Purge group_999 conversation history",
    )

    ok, message = service.cancel(owners_pending.token, "U-other")

    assert ok is False
    assert message == "❌ This token belongs to a different admin."
    assert service.get(owners_pending.token) == owners_pending
    assert service.get(others_pending.token) == others_pending

    ok, message = service.cancel(owners_pending.token, "U-owner")

    assert ok is True
    assert message == "✅ Cancelled."
    assert service.get(owners_pending.token) is None
    assert service.get(others_pending.token) == others_pending
