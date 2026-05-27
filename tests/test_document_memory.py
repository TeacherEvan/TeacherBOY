"""Tests for document memory safety and loading behavior."""

from __future__ import annotations

import json
import sys
from unittest.mock import MagicMock

from src.services.document_memory_service import DocumentMemoryService


def test_load_local_index_skips_invalid_doc_ids(tmp_path):
    """Poisoned metadata IDs should not be loaded into memory."""
    storage_path = tmp_path / "documents"
    doc_dir = storage_path / "chat_hash" / "poisoned"
    doc_dir.mkdir(parents=True)
    (doc_dir / "meta.json").write_text(
        json.dumps(
            {
                "id": "../../outside",
                "file_name": "evil.pdf",
                "extension": ".pdf",
            }
        ),
        encoding="utf-8",
    )

    service = DocumentMemoryService(storage_path=str(storage_path))

    assert service._documents == {}
    assert service.list_documents("any-chat") == []


def test_invalid_doc_id_is_rejected(tmp_path):
    """Malformed document IDs must never be used to access storage paths."""
    storage_path = tmp_path / "documents"
    service = DocumentMemoryService(storage_path=str(storage_path))
    chat_id = "group_123"
    malicious_doc_id = "../../outside"
    hashed_id = service._hash_chat_id(chat_id)

    service._documents.setdefault(hashed_id, {})[malicious_doc_id] = {
        "id": malicious_doc_id,
        "file_name": "evil.pdf",
    }

    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    (outside_dir / "text.txt").write_text("stolen data", encoding="utf-8")

    assert service.get_document_text(chat_id, malicious_doc_id) is None
    assert service.delete_document(chat_id, malicious_doc_id) is False


def test_hf_init_does_not_schedule_background_load(tmp_path, monkeypatch):
    """HF setup should not start a second background preload task."""

    class FakeHfApi:
        def __init__(self, token):
            self.token = token

        def create_repo(self, **kwargs):
            return None

    class FakeCommitScheduler:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def stop(self):
            return None

    fake_module = MagicMock()
    fake_module.HfApi = FakeHfApi
    fake_module.CommitScheduler = FakeCommitScheduler

    monkeypatch.setitem(sys.modules, "huggingface_hub", fake_module)

    DocumentMemoryService(
        hf_token="hf_token_1234567890",
        hf_repo_id="user/test-documents",
        storage_path=str(tmp_path / "documents"),
    )
