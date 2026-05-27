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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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


class DocumentMemoryService:
    """Service for persisting documents and extracted text per chat."""

    def __init__(
        self,
        hf_token: Optional[str] = None,
        hf_repo_id: Optional[str] = None,
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

        self._documents: Dict[str, Dict[str, Dict[str, Any]]] = {}

        self._hf_enabled = bool(hf_token and hf_repo_id)
        self._hf_api: Optional[Any] = None
        self._commit_scheduler: Optional[Any] = None

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
            HfApi = getattr(hf, "HfApi")
            CommitScheduler = getattr(hf, "CommitScheduler")

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

    def _infer_extension(self, file_name: str) -> Optional[str]:
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
                        logger.warning(
                            "⚠️ Skipping document with invalid ID from storage: %s", doc_id
                        )
                        continue
                    self._documents.setdefault(hashed_id, {})[doc_id] = metadata
                except Exception:
                    continue

    def _write_metadata(self, doc_dir: Path, metadata: Dict[str, Any]) -> None:
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
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
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
        uploaded_at = datetime.now(timezone.utc).isoformat()

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

    def list_documents(self, chat_id: str) -> List[Dict[str, Any]]:
        hashed_id = self._hash_chat_id(chat_id)
        docs = list(self._documents.get(hashed_id, {}).values())
        return sorted(docs, key=lambda d: d.get("uploaded_at", ""), reverse=True)

    def get_document_text(self, chat_id: str, doc_id: str) -> Optional[str]:
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

    def find_by_name(self, chat_id: str, name: str) -> List[Dict[str, Any]]:
        hashed_id = self._hash_chat_id(chat_id)
        name_lower = name.lower().strip()
        results = []
        for metadata in self._documents.get(hashed_id, {}).values():
            if name_lower in metadata.get("file_name", "").lower():
                results.append(metadata)
        return results

    def search_documents(self, chat_id: str, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        hashed_id = self._hash_chat_id(chat_id)
        query_lower = query.lower().strip()
        results: List[Dict[str, Any]] = []

        for doc_id, metadata in self._documents.get(hashed_id, {}).items():
            text = self.get_document_text(chat_id, doc_id) or ""
            if query_lower in text.lower():
                idx = text.lower().find(query_lower)
                start = max(idx - 80, 0)
                end = min(idx + 220, len(text))
                snippet = text[start:end]
                results.append({
                    "id": doc_id,
                    "file_name": metadata.get("file_name"),
                    "snippet": snippet,
                })
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
            list_repo_files = getattr(hf, "list_repo_files")
            hf_hub_download = getattr(hf, "hf_hub_download")

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

    def stop(self) -> None:
        if self._commit_scheduler:
            try:
                self._commit_scheduler.stop()
                logger.info("📄 Document memory scheduler stopped")
            except Exception as e:
                logger.warning(f"⚠️ Error stopping document scheduler: {e}")


# Singleton instance (configured during app startup)
document_memory_service: Optional[DocumentMemoryService] = None


def init_document_memory(
    hf_token: Optional[str] = None,
    hf_repo_id: Optional[str] = None,
    storage_path: Optional[str] = None,
    max_file_size_mb: Optional[float] = None,
    max_text_chars: Optional[int] = None,
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


def get_document_memory() -> Optional[DocumentMemoryService]:
    return document_memory_service
