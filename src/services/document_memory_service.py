"""
Document Memory Service - Persistent storage for user-uploaded documents.

Stores PDF/DOCX files and extracted text so Zeus can reference them later.
Supports local storage and optional Hugging Face Hub persistence.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from src.config import settings
from src.services.hf_storage_mixin import HFStorageMixin

logger = logging.getLogger(__name__)

DEFAULT_MAX_FILE_SIZE_MB = 10.0
DEFAULT_MAX_TEXT_CHARS = 80000
DEFAULT_EXCERPT_CHARS = 600
HF_SYNC_INTERVAL_MINUTES = 5
DOC_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")

SUPPORTED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class FlushMode(StrEnum):
    """Memory flush modes for documents."""

    TIME_BASED = "time_based"           # Delete older than N days
    SIZE_BASED = "size_based"           # Cap total documents / per-chat
    MANUAL_SELECTION = "manual"         # Admin picks specific chats
    FULL_PURGE = "full"                 # Everything (with confirmation)


class FlushParams:
    """Parameters for document flush operations."""

    def __init__(
        self,
        older_than_days: int | None = None,
        max_total_documents: int | None = None,
        max_documents_per_chat: int | None = None,
        chat_ids: list[str] | None = None,
        dry_run: bool = False,
        include_images: bool = False,
    ):
        self.older_than_days = older_than_days
        self.max_total_documents = max_total_documents
        self.max_documents_per_chat = max_documents_per_chat
        self.chat_ids = chat_ids
        self.dry_run = dry_run
        self.include_images = include_images


class FlushResult:
    """Result of a document flush operation."""

    def __init__(
        self,
        deleted_chats: int = 0,
        deleted_documents: int = 0,
        freed_bytes_mb: float = 0.0,
        dry_run: bool = False,
        mode: FlushMode | None = None,
    ):
        self.deleted_chats = deleted_chats
        self.deleted_documents = deleted_documents
        self.freed_bytes_mb = freed_bytes_mb
        self.dry_run = dry_run
        self.mode = mode

    def __repr__(self) -> str:
        action = "Dry run" if self.dry_run else "Executed"
        return (f"FlushResult({action}: deleted_chats={self.deleted_chats}, "
                f"deleted_documents={self.deleted_documents}, freed_mb={self.freed_bytes_mb:.2f})")


class DocumentMemoryService(HFStorageMixin):
    """Service for persisting documents and extracted text per chat."""

    def __init__(
        self,
        hf_token: str | None = None,
        hf_repo_id: str | None = None,
        storage_path: str = "./data/documents",
        max_file_size_mb: float = DEFAULT_MAX_FILE_SIZE_MB,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    ):
        # Set up HF storage mixin attributes
        self.hf_token = hf_token
        self.hf_repo_id = hf_repo_id
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.hf_sync_interval = HF_SYNC_INTERVAL_MINUTES
        self.hf_squash_history = True
        self.hf_path_in_repo = "documents"
        self._hf_enabled = bool(hf_token and hf_repo_id)

        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.max_text_chars = max_text_chars

        self._documents: dict[str, dict[str, dict[str, Any]]] = {}

        super().__init__()  # Initialize mixin

        if self._hf_enabled:
            self._setup_hf_storage()
        else:
            logger.info("📄 Document memory initialized (local-only)")

        self._load_local_index()

    def _hash_chat_id(self, chat_id: str) -> str:
        return hashlib.sha256(chat_id.encode("utf-8")).hexdigest()[:16]

    def _sanitize_filename(self, file_name: str) -> str:
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name.strip())
        return safe or "document"

    def _is_valid_doc_id(self, doc_id: Any) -> bool:
        return isinstance(doc_id, str) and bool(DOC_ID_PATTERN.fullmatch(doc_id))

    def _infer_extension(self, file_name: str) -> str | None:
        _, ext = os.path.splitext(file_name.lower())
        return ext if ext in SUPPORTED_EXTENSIONS else None

    def _get_doc_dir(self, hashed_id: str, doc_id: str) -> Path:
        if not self._is_valid_doc_id(doc_id):
            raise ValueError("invalid_document_id")
        assert self.storage_path is not None
        return self.storage_path / hashed_id / doc_id

    def _load_local_index(self) -> None:
        """Load metadata from local storage into memory."""
        assert self.storage_path is not None
        if not self.storage_path.exists():
            return

        for chat_dir in self.storage_path.iterdir():
            if not chat_dir.is_dir():
                continue
            hashed_id = chat_dir.name
            for doc_dir in chat_dir.iterdir():
                if not doc_dir.is_dir():
                    continue
                meta_path = doc_dir / "meta.json"
                if not meta_path.exists():
                    continue
                try:
                    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
                    doc_id = metadata.get("id") or doc_dir.name
                    if not self._is_valid_doc_id(doc_id):
                        logger.warning("⚠️ Skipping document with invalid ID from storage: %s", doc_id)
                        continue
                    self._documents.setdefault(hashed_id, {})[doc_id] = metadata
                except Exception:
                    continue

    def _write_metadata(self, doc_dir: Path, metadata: dict[str, Any]) -> None:
        meta_path = doc_dir / "meta.json"
        meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    def _extract_text(self, file_bytes: bytes, file_name: str) -> str:
        ext = self._infer_extension(file_name)
        if ext == ".pdf":
            try:
                import io

                from pypdf import PdfReader

                reader = PdfReader(io.BytesIO(file_bytes))
                parts = []
                for page in reader.pages:
                    text = page.extract_text() or ""
                    if text:
                        parts.append(text)
                return "\n".join(parts)
            except Exception as e:
                logger.warning(f"⚠️ PDF extraction failed: {e}")
                return ""

        if ext == ".docx":
            try:
                import io

                from docx import Document

                doc = Document(io.BytesIO(file_bytes))
                return "\n".join(p.text for p in doc.paragraphs if p.text)
            except Exception as e:
                logger.warning(f"⚠️ DOCX extraction failed: {e}")
                return ""

        return ""

    def _truncate_text(self, text: str) -> str:
        if len(text) <= self.max_text_chars:
            return text
        return text[: self.max_text_chars]

    async def add_document(
        self,
        chat_id: str,
        file_name: str,
        file_bytes: bytes,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """Store a document and extracted text."""
        if not file_bytes:
            raise ValueError("Empty file data")

        if len(file_bytes) > self.max_file_size_bytes:
            raise ValueError("file_too_large")

        ext = self._infer_extension(file_name)
        if not ext:
            raise ValueError("unsupported_type")

        hashed_id = self._hash_chat_id(chat_id)
        doc_id = uuid.uuid4().hex
        safe_name = self._sanitize_filename(file_name)

        doc_dir = self._get_doc_dir(hashed_id, doc_id)
        doc_dir.mkdir(parents=True, exist_ok=True)

        content_path = doc_dir / f"content{ext}"
        content_path.write_bytes(file_bytes)

        extracted_text = self._extract_text(file_bytes, safe_name)
        trimmed_text = self._truncate_text(extracted_text)
        text_path = doc_dir / "text.txt"
        text_path.write_text(trimmed_text, encoding="utf-8")

        checksum = hashlib.sha256(file_bytes).hexdigest()
        uploaded_at = datetime.now(UTC).isoformat()

        metadata = {
            "id": doc_id,
            "file_name": safe_name,
            "extension": ext,
            "mime_type": SUPPORTED_EXTENSIONS.get(ext),
            "size_bytes": len(file_bytes),
            "uploaded_at": uploaded_at,
            "user_id": user_id,
            "text_chars": len(trimmed_text),
            "checksum": checksum,
        }

        self._write_metadata(doc_dir, metadata)
        self._documents.setdefault(hashed_id, {})[doc_id] = metadata

        return metadata

    async def get_document(self, chat_id: str, doc_id: str) -> dict[str, Any] | None:
        """Retrieve document metadata by ID."""
        hashed_id = self._hash_chat_id(chat_id)
        return self._documents.get(hashed_id, {}).get(doc_id)

    def list_documents(self, chat_id: str) -> list[dict[str, Any]]:
        """List all documents for a chat."""
        hashed_id = self._hash_chat_id(chat_id)
        docs = self._documents.get(hashed_id, {})
        return list(docs.values())

    def get_document_text(self, chat_id: str, doc_id: str) -> str | None:
        """Retrieve extracted text content."""
        hashed_id = self._hash_chat_id(chat_id)
        doc = self._documents.get(hashed_id, {}).get(doc_id)
        if not doc:
            return None
        try:
            text_path = self._get_doc_dir(hashed_id, doc_id) / "text.txt"
        except ValueError:
            return None
        if text_path.exists():
            return text_path.read_text(encoding="utf-8")
        return None

    def delete_document(self, chat_id: str, doc_id: str) -> bool:
        """Delete a document and its associated files."""
        hashed_id = self._hash_chat_id(chat_id)
        if hashed_id not in self._documents or doc_id not in self._documents[hashed_id]:
            return False

        try:
            doc_dir = self._get_doc_dir(hashed_id, doc_id)
        except ValueError:
            return False
        if doc_dir.exists():
            import shutil

            shutil.rmtree(doc_dir)

        self._documents[hashed_id].pop(doc_id, None)
        if not self._documents[hashed_id]:
            self._documents.pop(hashed_id, None)

        return True

    async def load_documents_from_hub(self) -> int:
        """
        Load existing documents from HF Hub on startup.

        Returns:
            Number of document files downloaded
        """
        if not self._hf_enabled or not self._hf_api or not self.hf_repo_id or not self.hf_token:
            logger.info("HF Hub not configured; skipping document preload")
            return 0

        try:
            hf = importlib.import_module("huggingface_hub")
            list_repo_files = hf.list_repo_files
            hf_hub_download = hf.hf_hub_download

            try:
                files = list_repo_files(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    token=self.hf_token,
                )
            except Exception:
                logger.info("📄 No existing documents found in HF Hub")
                return 0

            downloaded = 0
            for file_path in files:
                if file_path.endswith(".tmp"):
                    continue
                local_target = self.storage_path / file_path
                local_target.parent.mkdir(parents=True, exist_ok=True)
                hf_hub_download(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    filename=file_path,
                    local_dir=str(self.storage_path),
                    local_dir_use_symlinks=False,
                    token=self.hf_token,
                )
                downloaded += 1

            if downloaded:
                self._load_local_index()
                logger.info(f"📄 Loaded {downloaded} document file(s) from HF Hub")

            return downloaded

        except ModuleNotFoundError:
            logger.info("📄 huggingface_hub not installed; skipping HF Hub document preload")
            return 0
        except Exception as e:
            logger.error(f"❌ Failed to load documents from HF Hub: {e}")
            return 0

    def stop(self) -> None:
        """Stop the commit scheduler (call during shutdown)."""
        self.stop_hf_storage()

    def get_stats(self) -> dict[str, Any]:
        """Get service statistics."""
        total_docs = sum(len(docs) for docs in self._documents.values())
        total_size = 0
        for docs in self._documents.values():
            for doc in docs.values():
                total_size += doc.get("size_bytes", 0)

        hf_stats = self.get_hf_stats()

        return {
            "active_chats": len(self._documents),
            "total_documents": total_docs,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "max_file_size_mb": self.max_file_size_bytes / (1024 * 1024),
            "max_text_chars": self.max_text_chars,
            **hf_stats,
        }

    async def purge_documents(
        self,
        mode: FlushMode,
        params: FlushParams,
    ) -> FlushResult:
        """
        Purge documents based on mode and parameters.

        Args:
            mode: Flush mode (TIME_BASED, SIZE_BASED, MANUAL_SELECTION, FULL_PURGE)
            params: Flush parameters

        Returns:
            FlushResult with deletion statistics
        """
        result = FlushResult(mode=mode, dry_run=params.dry_run)

        if mode == FlushMode.TIME_BASED:
            return await self._purge_time_based(params, result)
        elif mode == FlushMode.SIZE_BASED:
            return await self._purge_size_based(params, result)
        elif mode == FlushMode.MANUAL_SELECTION:
            return await self._purge_manual_selection(params, result)
        elif mode == FlushMode.FULL_PURGE:
            return await self._purge_full_purge(params, result)
        else:
            raise ValueError(f"Unknown flush mode: {mode}")

    async def _purge_time_based(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge documents older than specified days."""
        if params.older_than_days is None:
            params.older_than_days = 30

        cutoff = datetime.now(UTC) - timedelta(days=params.older_than_days)
        to_delete = []

        for chat_id, docs in self._documents.items():
            for doc_id, doc in list(docs.items()):
                created_at = doc.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if created_dt.tzinfo is None:
                            created_dt = created_dt.replace(tzinfo=UTC)
                        if created_dt < cutoff:
                            to_delete.append((chat_id, doc_id))
                            # chat_deleted = True
                    except Exception:
                        continue

        result.deleted_chats = len(set(chat_id for chat_id, _ in to_delete))
        result.deleted_documents = len(to_delete)

        if not params.dry_run:
            for chat_id, doc_id in to_delete:
                self.delete_document(chat_id, doc_id)

        return result

    async def _purge_size_based(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge to cap total documents or per-chat documents."""
        total_docs = sum(len(docs) for docs in self._documents.values())

        if params.max_documents_per_chat:
            for chat_id, docs in self._documents.items():
                if len(docs) > params.max_documents_per_chat:
                    sorted_docs = sorted(
                        docs.items(),
                        key=lambda x: x[1].get("uploaded_at", ""),
                    )
                    excess = len(docs) - params.max_documents_per_chat
                    for doc_id, _ in sorted_docs[:excess]:
                        result.deleted_documents += 1
                        if not params.dry_run:
                            self.delete_document(chat_id, doc_id)

        if params.max_total_documents and total_docs > params.max_total_documents:
            all_docs = [
                (chat_id, doc_id, doc.get("uploaded_at", ""))
                for chat_id, docs in self._documents.items()
                for doc_id, doc in docs.items()
            ]
            all_docs.sort(key=lambda x: x[2])
            excess = total_docs - params.max_total_documents
            for chat_id, doc_id, _ in all_docs[:excess]:
                result.deleted_documents += 1
                if not params.dry_run:
                    self.delete_document(chat_id, doc_id)
                    result.deleted_chats = len(set(c for c, _, _ in all_docs[:excess]))

        return result

    async def _purge_manual_selection(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge specific chat IDs provided by admin."""
        if not params.chat_ids:
            return result

        for chat_id in params.chat_ids:
            hashed_id = self._hash_chat_id(chat_id)
            if hashed_id in self._documents:
                docs = self._documents[hashed_id]
                result.deleted_chats += 1
                result.deleted_documents += len(docs)
                if not params.dry_run:
                    for doc_id in list(docs.keys()):
                        self.delete_document(chat_id, doc_id)

        return result

    async def _purge_full_purge(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge all documents (requires confirmation via params.dry_run=False)."""
        for _chat_id, docs in self._documents.items():
            result.deleted_chats += 1
            result.deleted_documents += len(docs)

        if not params.dry_run:
            for chat_id in list(self._documents.keys()):
                for doc_id in list(self._documents[chat_id].keys()):
                    self.delete_document(chat_id, doc_id)

        return result


# Singleton instance (configured during app startup)
document_memory_service: DocumentMemoryService | None = None


def init_document_memory(
    hf_token: str | None = None,
    hf_repo_id: str | None = None,
    storage_path: str | None = None,
    max_file_size_mb: float | None = None,
    max_text_chars: int | None = None,
) -> DocumentMemoryService:
    """Initialize the document memory service."""
    global document_memory_service

    document_memory_service = DocumentMemoryService(
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
        storage_path=storage_path or settings.document_storage_path,
        max_file_size_mb=max_file_size_mb or settings.document_max_file_size_mb,
        max_text_chars=max_text_chars or settings.document_max_text_chars,
    )
    return document_memory_service


def get_document_memory() -> DocumentMemoryService | None:
    return document_memory_service
