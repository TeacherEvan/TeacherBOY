"""
Document Memory Service - Persistent storage for user-uploaded documents.

Stores PDF/DOCX files and extracted text so Zeus can reference them later.
Supports local storage and optional Hugging Face Hub persistence.
"""

from __future__ import annotations

import hashlib
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


class DocumentMemoryService:
    """Service for persisting documents and extracted text per chat."""

    def __init__(
        self,
        hf_token: str | None = None,
        hf_repo_id: str | None = None,
        storage_path: str = "./data/documents",
        max_file_size_mb: float = DEFAULT_MAX_FILE_SIZE_MB,
        max_text_chars: int = DEFAULT_MAX_TEXT_CHARS,
    ):
        self.hf_token = hf_token
        self.hf_repo_id = hf_repo_id
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self.max_file_size_bytes = int(max_file_size_mb * 1024 * 1024)
        self.max_text_chars = max_text_chars

        self._documents: dict[str, dict[str, dict[str, Any]]] = {}

        self._hf_enabled = bool(hf_token and hf_repo_id)
        self._hf_api: Any | None = None
        self._commit_scheduler: Any | None = None

        if self._hf_enabled:
            self._setup_hf_storage()
        else:
            logger.info("📄 Document memory initialized (local-only)")

        self._load_local_index()

    def _setup_hf_storage(self) -> None:
        """Initialize HF Hub persistence using CommitScheduler."""
        if not self.hf_token or not self.hf_repo_id:
            self._hf_enabled = False
            return

        try:
            import importlib

            hf = importlib.import_module("huggingface_hub")
            HfApi = hf.HfApi
            CommitScheduler = hf.CommitScheduler

            hf_api = HfApi(token=self.hf_token)
            self._hf_api = hf_api

            try:
                hf_api.create_repo(
                    repo_id=self.hf_repo_id,
                    repo_type="dataset",
                    private=True,
                    exist_ok=True,
                )
                logger.info(f"📄 HF Hub dataset ready: {self.hf_repo_id}")
            except Exception as e:
                logger.warning(f"⚠️ Could not create/verify HF repo: {e}")
                self._hf_enabled = False
                return

            self._commit_scheduler = CommitScheduler(
                repo_id=self.hf_repo_id,
                repo_type="dataset",
                folder_path=str(self.storage_path),
                every=HF_SYNC_INTERVAL_MINUTES,
                token=self.hf_token,
                private=True,
                squash_history=True,
            )

            logger.info("📄 Document memory initialized with HF Hub persistence")

        except ModuleNotFoundError:
            logger.warning("⚠️ huggingface_hub not installed, using local-only storage")
            self._hf_enabled = False
        except Exception as e:
            logger.error(f"❌ Failed to initialize document HF storage: {e}")
            self._hf_enabled = False

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
        return self.storage_path / hashed_id / doc_id

    def _load_local_index(self) -> None:
        """Load metadata from local storage into memory."""
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
            "text_excerpt": trimmed_text[:DEFAULT_EXCERPT_CHARS],
            "sha256": checksum,
            "path": str(content_path),
        }

        self._write_metadata(doc_dir, metadata)
        self._documents.setdefault(hashed_id, {})[doc_id] = metadata

        return metadata

    def list_documents(self, chat_id: str) -> list[dict[str, Any]]:
        hashed_id = self._hash_chat_id(chat_id)
        docs = list(self._documents.get(hashed_id, {}).values())
        return sorted(docs, key=lambda d: d.get("uploaded_at", ""), reverse=True)

    def get_document_text(self, chat_id: str, doc_id: str) -> str | None:
        if not self._is_valid_doc_id(doc_id):
            return None
        hashed_id = self._hash_chat_id(chat_id)
        metadata = self._documents.get(hashed_id, {}).get(doc_id)
        if not metadata:
            return None
        doc_dir = self._get_doc_dir(hashed_id, doc_id)
        text_path = doc_dir / "text.txt"
        if not text_path.exists():
            return None
        return text_path.read_text(encoding="utf-8")

    def find_by_name(self, chat_id: str, name: str) -> list[dict[str, Any]]:
        hashed_id = self._hash_chat_id(chat_id)
        name_lower = name.lower().strip()
        results = []
        for metadata in self._documents.get(hashed_id, {}).values():
            if name_lower in metadata.get("file_name", "").lower():
                results.append(metadata)
        return results

    def search_documents(self, chat_id: str, query: str, limit: int = 5) -> list[dict[str, Any]]:
        hashed_id = self._hash_chat_id(chat_id)
        query_lower = query.lower().strip()
        results: list[dict[str, Any]] = []

        for doc_id, metadata in self._documents.get(hashed_id, {}).items():
            text = self.get_document_text(chat_id, doc_id) or ""
            if query_lower in text.lower():
                idx = text.lower().find(query_lower)
                start = max(idx - 80, 0)
                end = min(idx + 220, len(text))
                snippet = text[start:end]
                results.append(
                    {
                        "id": doc_id,
                        "file_name": metadata.get("file_name"),
                        "snippet": snippet,
                    }
                )
            if len(results) >= limit:
                break

        return results

    def delete_document(self, chat_id: str, doc_id: str) -> bool:
        if not self._is_valid_doc_id(doc_id):
            return False
        hashed_id = self._hash_chat_id(chat_id)
        metadata = self._documents.get(hashed_id, {}).pop(doc_id, None)
        if not metadata:
            return False

        doc_dir = self._get_doc_dir(hashed_id, doc_id)
        if doc_dir.exists():
            for item in doc_dir.glob("*"):
                try:
                    item.unlink()
                except Exception:
                    pass
            try:
                doc_dir.rmdir()
            except Exception:
                pass

        return True

    def clear_documents(self, chat_id: str) -> bool:
        hashed_id = self._hash_chat_id(chat_id)
        if hashed_id not in self._documents:
            return False

        chat_dir = self.storage_path / hashed_id
        if chat_dir.exists():
            for doc_dir in chat_dir.glob("*"):
                if not doc_dir.is_dir():
                    continue
                for item in doc_dir.glob("*"):
                    try:
                        item.unlink()
                    except Exception:
                        pass
                try:
                    doc_dir.rmdir()
                except Exception:
                    pass

        self._documents.pop(hashed_id, None)
        return True

    async def _load_from_hub(self) -> None:
        if not self._hf_enabled or not self._hf_api:
            return

        try:
            import importlib

            hf = importlib.import_module("huggingface_hub")
            list_repo_files = hf.list_repo_files
            hf_hub_download = hf.hf_hub_download

            files = list_repo_files(
                repo_id=self.hf_repo_id,
                repo_type="dataset",
                token=self.hf_token,
            )

            if not files:
                logger.info("📄 No existing documents found in HF Hub")
                return

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

        except ModuleNotFoundError:
            logger.info("📄 huggingface_hub not installed; skipping HF Hub document preload")
        except Exception as e:
            logger.error(f"❌ Failed to load documents from HF Hub: {e}")

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
            chat_deleted = False
            for doc_id, doc in list(docs.items()):
                created_at = doc.get("created_at")
                if isinstance(created_at, str):
                    try:
                        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                        if created_dt.tzinfo is None:
                            created_dt = created_dt.replace(tzinfo=UTC)
                        if created_dt < cutoff:
                            to_delete.append((chat_id, doc_id))
                            chat_deleted = True
                    except Exception:
                        continue

            if chat_deleted and not params.dry_run:
                result.deleted_chats += 1

        result.deleted_documents = len(to_delete)
        for chat_id, doc_id in to_delete:
            if not params.dry_run:
                del self._documents[chat_id][doc_id]
                # Delete local file
                doc_path = self.storage_path / chat_id / doc_id
                if doc_path.exists():
                    try:
                        size = doc_path.stat().st_size / (1024 * 1024)
                        result.freed_bytes_mb += size
                    except Exception:
                        pass
                    doc_path.unlink(missing_ok=True)
                # Delete index file
                index_path = self.storage_path / chat_id / f"{doc_id}.json"
                if index_path.exists():
                    index_path.unlink(missing_ok=True)

            if not params.dry_run and not self._documents.get(chat_id):
                self._documents.pop(chat_id, None)

        return result

    async def _purge_size_based(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge to cap total documents or per-chat documents."""
        # If per-chat limit specified, trim each chat
        if params.max_documents_per_chat:
            for chat_id, docs in self._documents.items():
                doc_items = list(docs.items())
                if len(doc_items) > params.max_documents_per_chat:
                    # Sort by created_at (oldest first)
                    doc_items.sort(key=lambda x: x[1].get("created_at", ""))
                    to_remove = doc_items[:-params.max_documents_per_chat]
                    result.deleted_documents += len(to_remove)
                    if not params.dry_run:
                        for doc_id, _ in to_remove:
                            del self._documents[chat_id][doc_id]
                            doc_path = self.storage_path / chat_id / doc_id
                            if doc_path.exists():
                                doc_path.unlink(missing_ok=True)
                            index_path = self.storage_path / chat_id / f"{doc_id}.json"
                            if index_path.exists():
                                index_path.unlink(missing_ok=True)

        # If total limit specified (across all chats)
        if params.max_total_documents:
            all_docs = []
            for chat_id, docs in self._documents.items():
                for doc_id, doc in docs.items():
                    all_docs.append((chat_id, doc_id, doc))

            total_docs = len(all_docs)
            if total_docs > params.max_total_documents:
                # Sort by created_at (oldest first)
                all_docs.sort(key=lambda x: x[2].get("created_at", ""))
                excess = total_docs - params.max_total_documents
                for chat_id, doc_id, doc in all_docs[:excess]:
                    result.deleted_documents += 1
                    if not params.dry_run:
                        if chat_id in self._documents:
                            self._documents[chat_id].pop(doc_id, None)
                            doc_path = self.storage_path / chat_id / doc_id
                            if doc_path.exists():
                                doc_path.unlink(missing_ok=True)
                            index_path = self.storage_path / chat_id / f"{doc_id}.json"
                            if index_path.exists():
                                index_path.unlink(missing_ok=True)

        return result

    async def _purge_manual_selection(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge specific chat IDs provided by admin."""
        if not params.chat_ids:
            return result

        for chat_id in params.chat_ids:
            if chat_id in self._documents:
                docs = self._documents[chat_id]
                result.deleted_chats += 1
                result.deleted_documents += len(docs)
                if not params.dry_run:
                    for doc_id in docs:
                        doc_path = self.storage_path / chat_id / doc_id
                        if doc_path.exists():
                            doc_path.unlink(missing_ok=True)
                        index_path = self.storage_path / chat_id / f"{doc_id}.json"
                        if index_path.exists():
                            index_path.unlink(missing_ok=True)
                    self._documents.pop(chat_id, None)

        return result

    async def _purge_full_purge(self, params: FlushParams, result: FlushResult) -> FlushResult:
        """Purge all documents."""
        result.deleted_chats = len(self._documents)
        for docs in self._documents.values():
            result.deleted_documents += len(docs)

        if not params.dry_run:
            self._documents.clear()
            # Clear all local storage files
            import shutil
            if self.storage_path.exists():
                shutil.rmtree(self.storage_path)
                self.storage_path.mkdir(parents=True, exist_ok=True)

        return result

    def stop(self) -> None:
        if self._commit_scheduler:
            try:
                self._commit_scheduler.stop()
                logger.info("📄 Document memory scheduler stopped")
            except Exception as e:
                logger.warning(f"⚠️ Error stopping document scheduler: {e}")


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
