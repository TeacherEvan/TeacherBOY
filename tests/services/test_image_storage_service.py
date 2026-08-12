"""
Tests for ImageStorageService — filesystem-based image lifecycle management.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from src.services.image_storage_service import ImageStorageService


@pytest.fixture
def storage(tmp_path: Path) -> ImageStorageService:
    """Fresh service pointed at a temp directory."""
    return ImageStorageService(base_path=str(tmp_path / "images"))


FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal JPEG-like bytes


# ---------------------------------------------------------------------------
# Directory namespacing
# ---------------------------------------------------------------------------


class TestDirectoryIsolation:
    def test_different_chats_get_different_directories(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_A", "msg1", FAKE_JPEG)
        storage.store_incoming_image("chat_B", "msg2", FAKE_JPEG)

        dir_a = storage._get_chat_dir("chat_A")
        dir_b = storage._get_chat_dir("chat_B")

        assert dir_a != dir_b
        assert dir_a.exists()
        assert dir_b.exists()

    def test_chat_id_sanitization_strips_traversal(self, storage: ImageStorageService) -> None:
        """Ensure path traversal characters are stripped from chat IDs."""
        safe_dir = storage._get_chat_dir("../../etc/passwd")
        assert storage.base_path in safe_dir.parents or safe_dir.parent == storage.base_path

    def test_same_chat_uses_same_directory(self, storage: ImageStorageService) -> None:
        path1 = storage._get_chat_dir("group_123")
        path2 = storage._get_chat_dir("group_123")
        assert path1 == path2


# ---------------------------------------------------------------------------
# Image storage and metadata
# ---------------------------------------------------------------------------


class TestStoreIncomingImage:
    def test_stores_jpeg_file(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_X", "msg_1", FAKE_JPEG)
        chat_dir = storage._get_chat_dir("chat_X")
        jpg_files = list(chat_dir.glob("*.jpg"))
        assert len(jpg_files) == 1

    def test_creates_companion_json_metadata(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_X", "msg_1", FAKE_JPEG)
        chat_dir = storage._get_chat_dir("chat_X")
        json_files = list(chat_dir.glob("*.json"))
        assert len(json_files) == 1

    def test_metadata_defaults_enquired_false(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_X", "msg_1", FAKE_JPEG)
        chat_dir = storage._get_chat_dir("chat_X")
        json_file = next(chat_dir.glob("*.json"))
        meta = json.loads(json_file.read_text(encoding="utf-8"))
        assert meta["enquired"] is False

    def test_metadata_contains_correct_fields(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_X", "msg_42", FAKE_JPEG)
        chat_dir = storage._get_chat_dir("chat_X")
        json_file = next(chat_dir.glob("*.json"))
        meta = json.loads(json_file.read_text(encoding="utf-8"))
        assert meta["message_id"] == "msg_42"
        assert meta["chat_id"] == "chat_X"
        assert "timestamp" in meta

    def test_returns_image_path_string(self, storage: ImageStorageService) -> None:
        result = storage.store_incoming_image("chat_X", "msg_1", FAKE_JPEG)
        assert result.endswith(".jpg")
        assert Path(result).exists()


# ---------------------------------------------------------------------------
# get_last_image
# ---------------------------------------------------------------------------


class TestGetLastImage:
    def test_returns_none_when_no_images(self, storage: ImageStorageService) -> None:
        result = storage.get_last_image("empty_chat", mark_enquired=False)
        assert result is None

    def test_returns_base64_data_url(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_Y", "msg_1", FAKE_JPEG)
        result = storage.get_last_image("chat_Y", mark_enquired=False)
        assert result is not None
        assert result.startswith("data:image/jpeg;base64,")

    def test_mark_enquired_toggles_metadata(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_Y", "msg_1", FAKE_JPEG)
        storage.get_last_image("chat_Y", mark_enquired=True)

        chat_dir = storage._get_chat_dir("chat_Y")
        json_file = next(chat_dir.glob("*.json"))
        meta = json.loads(json_file.read_text(encoding="utf-8"))
        assert meta["enquired"] is True


# ---------------------------------------------------------------------------
# Cleanup logic
# ---------------------------------------------------------------------------


class TestCleanupOldImages:
    def _backdate_json(self, json_path: Path, hours_ago: float) -> None:
        """Move the stored timestamp back in time."""
        meta = json.loads(json_path.read_text(encoding="utf-8"))
        backdated = (datetime.now(UTC) - timedelta(hours=hours_ago)).isoformat()
        meta["timestamp"] = backdated
        json_path.write_text(json.dumps(meta), encoding="utf-8")

    def test_deletes_unenquired_images_past_ttl(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_Z", "old_msg", FAKE_JPEG)
        chat_dir = storage._get_chat_dir("chat_Z")
        json_file = next(chat_dir.glob("*.json"))
        self._backdate_json(json_file, hours_ago=25)

        deleted = storage.cleanup_old_images(ttl_hours=24, keep_enquired_days=7)
        assert deleted == 2  # jpg + json

    def test_keeps_unenquired_images_within_ttl(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_Z", "recent_msg", FAKE_JPEG)

        deleted = storage.cleanup_old_images(ttl_hours=24)
        assert deleted == 0

    def test_keeps_enquired_images_within_keep_period(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_Z", "enquired_msg", FAKE_JPEG)
        storage.mark_last_image_enquired("chat_Z")
        chat_dir = storage._get_chat_dir("chat_Z")
        json_file = next(chat_dir.glob("*.json"))
        self._backdate_json(json_file, hours_ago=25)  # 25h old, within 7-day keep

        deleted = storage.cleanup_old_images(ttl_hours=24, keep_enquired_days=7)
        assert deleted == 0

    def test_deletes_enquired_images_past_keep_period(self, storage: ImageStorageService) -> None:
        storage.store_incoming_image("chat_Z", "old_enquired", FAKE_JPEG)
        storage.mark_last_image_enquired("chat_Z")
        chat_dir = storage._get_chat_dir("chat_Z")
        json_file = next(chat_dir.glob("*.json"))
        self._backdate_json(json_file, hours_ago=24 * 8)  # 8 days old

        deleted = storage.cleanup_old_images(ttl_hours=24, keep_enquired_days=7)
        assert deleted == 2

    def test_returns_zero_for_empty_store(self, storage: ImageStorageService) -> None:
        assert storage.cleanup_old_images() == 0
