"""
Image Storage Service - Handles background storage and lifecycle of incoming images.
Provides contact/group-isolated directory structure and daily cleanup.
"""

from __future__ import annotations

import base64
import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


class ImageStorageService:
    """
    Manages filesystem-based image storage per contact/group.
    Enforces daily cleanup (purging unenquired images after 24 hours).
    """

    def __init__(self, base_path: str = "./data/incoming_images"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"📁 ImageStorageService initialized at {self.base_path}")

    def _get_chat_dir(self, chat_id: str) -> Path:
        """Get the group/user-specific directory."""
        # Sanitize chat_id to prevent directory traversal
        safe_chat_id = "".join(c for c in chat_id if c.isalnum() or c in ("-", "_"))
        chat_dir = self.base_path / safe_chat_id
        chat_dir.mkdir(parents=True, exist_ok=True)
        return chat_dir

    def store_incoming_image(self, chat_id: str, message_id: str, image_bytes: bytes) -> str:
        """
        Store an incoming image and write its companion metadata.

        Args:
            chat_id: Group or user identifier.
            message_id: LINE message identifier.
            image_bytes: Raw binary content of the image.

        Returns:
            The file path of the stored image.
        """
        chat_dir = self._get_chat_dir(chat_id)
        timestamp_str = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        # Save image file
        image_filename = f"{timestamp_str}_{message_id}.jpg"
        image_path = chat_dir / image_filename
        image_path.write_bytes(image_bytes)

        # Save metadata file
        metadata_filename = f"{timestamp_str}_{message_id}.json"
        metadata_path = chat_dir / metadata_filename

        metadata = {
            "message_id": message_id,
            "chat_id": chat_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "enquired": False,
        }

        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"📸 Saved incoming image and metadata for chat {chat_id} (msg: {message_id})")
        return str(image_path)

    def get_last_image(self, chat_id: str, mark_enquired: bool = True) -> str | None:
        """
        Retrieve the most recent image for a chat as a base64 data URL.

        Args:
            chat_id: Group or user identifier.
            mark_enquired: Whether to mark the image as enquired in metadata.

        Returns:
            Base64 encoded Data URL of the image, or None if not found.
        """
        chat_dir = self._get_chat_dir(chat_id)

        # Find all .jpg files and sort by modification time (newest first)
        jpg_files = sorted(chat_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if not jpg_files:
            return None

        last_image_path = jpg_files[0]
        try:
            image_bytes = last_image_path.read_bytes()
            encoded_bytes = base64.b64encode(image_bytes).decode("utf-8")
            data_url = f"data:image/jpeg;base64,{encoded_bytes}"

            if mark_enquired:
                self.mark_image_enquired(chat_id, last_image_path.stem)

            return data_url
        except Exception as e:
            logger.error(f"❌ Failed to read or encode last image {last_image_path}: {e}")
            return None

    def mark_image_enquired(self, chat_id: str, file_stem: str) -> None:
        """
        Mark a specific image as enquired in its metadata.

        Args:
            chat_id: Group or user identifier.
            file_stem: The filename without extension (e.g. timestamp_messageid).
        """
        chat_dir = self._get_chat_dir(chat_id)
        metadata_path = chat_dir / f"{file_stem}.json"

        if not metadata_path.exists():
            return

        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["enquired"] = True
            metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"📝 Marked image {file_stem} as enquired in chat {chat_id}")
        except Exception as e:
            logger.warning(f"⚠️ Failed to update metadata for {file_stem}: {e}")

    def mark_last_image_enquired(self, chat_id: str) -> None:
        """Mark the absolute most recent image for a chat as enquired."""
        chat_dir = self._get_chat_dir(chat_id)
        jpg_files = sorted(chat_dir.glob("*.jpg"), key=lambda p: p.stat().st_mtime, reverse=True)
        if jpg_files:
            self.mark_image_enquired(chat_id, jpg_files[0].stem)

    def cleanup_old_images(self, ttl_hours: int = 24, keep_enquired_days: int = 7) -> int:
        """
        Clean up stored images.
        Unenquired images older than ttl_hours are purged.
        Enquired images older than keep_enquired_days are purged to save disk space.

        Returns:
            Number of files deleted.
        """
        now = datetime.now(UTC)
        deleted_count = 0

        # Walk through base path recursively
        for path in list(self.base_path.glob("**/*.json")):
            try:
                metadata = json.loads(path.read_text(encoding="utf-8"))
                timestamp_str = metadata.get("timestamp")
                if not timestamp_str:
                    continue

                timestamp = datetime.fromisoformat(timestamp_str)
                enquired = metadata.get("enquired", False)

                # Check expiration limits
                if not enquired:
                    expired = (now - timestamp) > timedelta(hours=ttl_hours)
                else:
                    expired = (now - timestamp) > timedelta(days=keep_enquired_days)

                if expired:
                    # Find associated jpg
                    jpg_path = path.with_suffix(".jpg")

                    # Delete metadata
                    if path.exists():
                        path.unlink()
                        deleted_count += 1
                    # Delete jpg
                    if jpg_path.exists():
                        jpg_path.unlink()
                        deleted_count += 1

                    logger.debug(f"🗑️ Cleaned up expired image file: {jpg_path.name} (enquired={enquired})")
            except Exception as e:
                logger.error(f"❌ Error during image cleanup for {path}: {e}")

        if deleted_count > 0:
            logger.info(f"🗑️ Image storage cleanup: deleted {deleted_count} files.")
        return deleted_count


# Singleton instance
image_storage_service = ImageStorageService()
