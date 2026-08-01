"""
HF Storage Mixin - Shared Hugging Face Hub persistence logic.

Eliminates duplicate HF Hub initialization code across:
- ConversationMemoryService
- DocumentMemoryService
- HistoryLogService

This mixin provides a standard interface for CommitScheduler-based HF Hub sync.
"""

import importlib
import logging
from collections.abc import Callable
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class HFStorageMixin:
    """
    Mixin class for Hugging Face Hub persistence using CommitScheduler.

    Usage:
        class MyService(HFStorageMixin):
            def __init__(self, hf_token, hf_repo_id, storage_path, ...):
                super().__init__()
                self.hf_token = hf_token
                self.hf_repo_id = hf_repo_id
                self.storage_path = Path(storage_path)
                self.hf_sync_interval = 5  # minutes
                self.hf_squash_history = True
                self.hf_path_in_repo = None  # optional subfolder
                self._hf_enabled = bool(hf_token and hf_repo_id)
                if self._hf_enabled:
                    self._setup_hf_storage()
    """

    # Configurable attributes (set by subclass before calling _setup_hf_storage)
    hf_token: str | None = None
    hf_repo_id: str | None = None
    storage_path: Path | None = None
    hf_sync_interval: int = 5  # minutes
    hf_squash_history: bool = False
    hf_path_in_repo: str | None = None  # e.g., "logs", "conversations", "documents"
    hf_repo_type: str = "dataset"
    hf_private: bool = True

    # Internal state
    _hf_enabled: bool = False
    _hf_api: Any | None = None
    _commit_scheduler: Any | None = None
    _hf_sync_folder: Path | None = None

    def _setup_hf_storage(self) -> None:
        """Initialize Hugging Face Hub storage backend."""
        if not self.hf_token or not self.hf_repo_id:
            self._hf_enabled = False
            logger.info("HF storage disabled: missing token or repo_id")
            return

        if not self.storage_path:
            self._hf_enabled = False
            logger.error("HF storage disabled: storage_path not set")
            return

        try:
            hf = importlib.import_module("huggingface_hub")
            HfApi = hf.HfApi
            CommitScheduler = hf.CommitScheduler

            hf_api = HfApi(token=self.hf_token)
            self._hf_api = hf_api

            self._hf_sync_folder = self.storage_path
            self._hf_sync_folder.mkdir(parents=True, exist_ok=True)

            # Ensure the dataset repo exists
            try:
                hf_api.create_repo(
                    repo_id=self.hf_repo_id,
                    repo_type=self.hf_repo_type,
                    private=self.hf_private,
                    exist_ok=True,
                )
                logger.info(f"HF Hub dataset ready: {self.hf_repo_id}")
            except Exception as e:
                logger.warning(f"Could not create/verify HF repo: {e}")
                self._hf_enabled = False
                return

            # Set up scheduled commits
            self._commit_scheduler = CommitScheduler(
                repo_id=self.hf_repo_id,
                repo_type=self.hf_repo_type,
                folder_path=str(self._hf_sync_folder),
                every=self.hf_sync_interval,
                token=self.hf_token,
                private=self.hf_private,
                squash_history=self.hf_squash_history,
                path_in_repo=self.hf_path_in_repo,
            )

            logger.info(
                f"HF Hub persistence enabled: {self.hf_repo_id} "
                f"(sync every {self.hf_sync_interval} min, squash={self.hf_squash_history})"
            )
            self._hf_enabled = True

        except ModuleNotFoundError:
            logger.warning("huggingface_hub not installed; HF storage disabled")
            self._hf_enabled = False
        except Exception as e:
            logger.error(f"Failed to initialize HF storage: {e}")
            self._hf_enabled = False

    def stop_hf_storage(self) -> None:
        """Stop the commit scheduler (call during shutdown)."""
        if self._commit_scheduler:
            try:
                self._commit_scheduler.stop()
                logger.info("HF Hub commit scheduler stopped")
            except Exception as e:
                logger.warning(f"Error stopping commit scheduler: {e}")

    def get_hf_stats(self) -> dict[str, Any]:
        """Get HF storage statistics."""
        return {
            "hf_enabled": self._hf_enabled,
            "hf_repo_id": self.hf_repo_id if self._hf_enabled else None,
            "hf_sync_interval_minutes": self.hf_sync_interval,
            "hf_squash_history": self.hf_squash_history,
            "hf_path_in_repo": self.hf_path_in_repo,
        }

    def load_from_hub(
        self,
        file_extension: str = ".json",
        max_files: int = 100,
        post_process: Callable[[str, dict[str, Any]], dict[str, Any]] | None = None,
    ) -> int:
        """
        Load existing data from HF Hub on startup.

        Args:
            file_extension: Filter files by extension (e.g., ".json")
            max_files: Maximum files to load (default 100)
            post_process: Optional function(hashed_id, data) -> transformed_data

        Returns:
            Number of items loaded
        """
        if not self._hf_enabled or not self._hf_api or not self.hf_repo_id or not self.hf_token:
            logger.info("HF Hub not configured; skipping preload")
            return 0

        if self._hf_sync_folder is None:
            return 0
        if not self._hf_sync_folder.exists():
            self._hf_sync_folder.mkdir(parents=True, exist_ok=True)

        try:
            hf = importlib.import_module("huggingface_hub")
            hf_hub_download = hf.hf_hub_download
            list_repo_files = hf.list_repo_files

            # List files in the repo
            try:
                repo_path = self.hf_path_in_repo or ""
                files = list_repo_files(
                    repo_id=self.hf_repo_id,
                    repo_type=self.hf_repo_type,
                    token=self.hf_token,
                )
            except Exception as e:
                logger.info(f"No existing data found in HF Hub: {e}")
                return 0

            # Download and process each file
            target_files = [f for f in files if f.endswith(file_extension)]
            if repo_path:
                # Filter by subfolder
                target_files = [f for f in target_files if f.startswith(repo_path)]

            # CRITICAL FIX: Prior buggy starts uploaded data nested one level too
            # deep (e.g. "conversations/conversations/<hash>.json"). Skip any file
            # that lives deeper than the intended subfolder so we don't replay
            # corrupted data; those should be purged from the repo manually.
            nested_corrupted = 0
            if repo_path:
                flat_targets = []
                for f in target_files:
                    rel = f[len(repo_path) :].lstrip("/")
                    if "/" in rel:
                        nested_corrupted += 1
                        continue
                    flat_targets.append(f)
                if nested_corrupted:
                    logger.warning(
                        f"⚠️ Skipping {nested_corrupted} nested/corrupted file(s) under "
                        f"'{repo_path}/' (e.g. '{repo_path}/{repo_path}/...'). Purge them "
                        f"from the HF dataset to reclaim space."
                    )
                target_files = flat_targets

            # CRITICAL FIX: The sync folder (self._hf_sync_folder) already
            # represents hf_path_in_repo (e.g. "./data/conversations" maps to
            # repo path "conversations/"). Downloading the full repo path
            # ("conversations/<hash>.json") INTO that folder double-nests the
            # file ("./data/conversations/conversations/<hash>.json"), which the
            # CommitScheduler then re-syncs back to the repo, producing unbounded
            # "conversations/conversations/..." growth and a startup that never
            # finishes. Pass the PARENT as local_dir so the subfolder is created
            # exactly once.
            if self.hf_path_in_repo:
                local_dir = str(self._hf_sync_folder.parent)
            else:
                local_dir = str(self._hf_sync_folder)

            loaded = 0
            for filename in target_files[:max_files]:
                try:
                    local_path = hf_hub_download(
                        repo_id=self.hf_repo_id,
                        filename=filename,
                        repo_type=self.hf_repo_type,
                        token=self.hf_token,
                        local_dir=local_dir,
                        local_dir_use_symlinks=False,
                    )

                    import json

                    with open(local_path, encoding="utf-8") as f:
                        data = json.load(f)

                    hashed_id = Path(filename).stem

                    if post_process:
                        data = post_process(hashed_id, data)

                    loaded += 1

                except Exception as e:
                    logger.warning(f"Failed to load {filename}: {e}")

            if loaded > 0:
                logger.info(f"Loaded {loaded} item(s) from HF Hub")

            return loaded

        except ModuleNotFoundError:
            logger.info("huggingface_hub not installed; skipping HF Hub preload")
            return 0
        except Exception as e:
            logger.error(f"Failed to load data from HF Hub: {e}")
            return 0

    def save_to_local(self, hashed_id: str, data: dict[str, Any], file_extension: str = ".json") -> bool:
        """
        Save data to local storage for HF Hub sync.

        Args:
            hashed_id: Unique identifier for the data
            data: Serializable data dict
            file_extension: File extension (default .json)

        Returns:
            True if saved successfully
        """
        if not self._hf_sync_folder:
            return False

        try:
            file_path = self._hf_sync_folder / f"{hashed_id}{file_extension}"

            # Write atomically
            temp_path = file_path.with_suffix(".tmp")
            import json

            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            temp_path.rename(file_path)

            return True

        except Exception as e:
            logger.error(f"Failed to save {hashed_id}: {e}")
            return False
