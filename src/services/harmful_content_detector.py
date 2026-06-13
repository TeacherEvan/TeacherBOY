"""Keyword + optional LLM harmful content detection."""

import json
import logging
import re
from pathlib import Path

from src.config import settings

logger = logging.getLogger(__name__)


class HarmfulContentDetector:
    """Detect harmful content using keywords and optional LLM."""

    DEFAULT_KEYWORDS = [
        # English
        "spam",
        "scam",
        "fraud",
        "phishing",
        "malware",
        "virus",
        "hate",
        "harassment",
        "threat",
        "violence",
        "illegal",
        "drugs",
        "weapon",
        "bomb",
        "terrorist",
        "extremist",
        # Thai (common harmful terms)
        "สแปม",
        "ฉ้อโกง",
        "หลอกลวง",
        "เกยหรือ",
        "วางไวรัส",
        "เกลียด",
        "ข่มขู่",
        "คุกคาม",
        "ความรุนแรง",
        "ผิดกฎหมาย",
        "ยาเสพติด",
        "อาวุธ",
        "ระเบิด",
        "ขบวนการสุดขั้ว",
    ]

    def __init__(self, keywords: list[str] | None = None, llm_client=None):
        # Load keywords from config if available
        config_keywords = self._load_keywords_from_config()
        self.keywords = keywords or config_keywords or self.DEFAULT_KEYWORDS.copy()
        self._llm_client = llm_client  # Optional: for LLM-based detection
        self._llm_enabled = llm_client is not None
        # Pre-compile case-insensitive regex pattern for O(m) matching
        self._compiled_pattern: re.Pattern | None = None
        self._rebuild_pattern()

    def _load_keywords_from_config(self) -> list[str] | None:
        """Load keywords from config file or environment variable."""
        keywords = []

        # Try loading from file
        if settings.harmful_content_keywords_file:
            try:
                file_path = Path(settings.harmful_content_keywords_file)
                if file_path.exists():
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        keywords.extend(data)
                    elif isinstance(data, dict) and "keywords" in data:
                        keywords.extend(data["keywords"])
                    logger.info(f"Loaded {len(keywords)} harmful keywords from {file_path}")
            except Exception as e:
                logger.warning(f"Failed to load harmful keywords from file: {e}")

        # Try loading from environment variable
        if settings.harmful_content_keywords_env:
            env_keywords = [k.strip() for k in settings.harmful_content_keywords_env.split(",") if k.strip()]
            keywords.extend(env_keywords)
            logger.info(f"Loaded {len(env_keywords)} harmful keywords from env var")

        return keywords if keywords else None

    def _rebuild_pattern(self) -> None:
        """Rebuild the compiled regex pattern from current keywords."""
        if not self.keywords:
            self._compiled_pattern = None
            return
        # Escape each keyword and join with | for alternation
        # Sort by length descending to match longer keywords first
        escaped = [re.escape(kw) for kw in sorted(self.keywords, key=len, reverse=True)]
        pattern = "|".join(escaped)
        self._compiled_pattern = re.compile(pattern, re.IGNORECASE)

    async def detect(self, text: str) -> dict:
        """Detect harmful content in text.

        Returns:
            dict with: is_harmful (bool), matched_keywords (list), method (str), llm_result (optional)
        """
        text_lower = text.lower()

        # Fast path: use compiled regex for keyword matching
        if self._compiled_pattern:
            matches = self._compiled_pattern.findall(text_lower)
            if matches:
                # Deduplicate matches (regex findall may return duplicates for overlapping)
                matched = list(dict.fromkeys(matches))
                return {
                    "is_harmful": True,
                    "matched_keywords": matched,
                    "method": "keyword",
                }

        # Optional LLM detection (if configured)
        if self._llm_enabled:
            try:
                llm_result = await self._llm_detect(text)
                if llm_result.get("is_harmful"):
                    return {
                        "is_harmful": True,
                        "matched_keywords": [],
                        "method": "llm",
                        "llm_result": llm_result,
                    }
            except Exception as e:
                logger.warning(f"LLM detection failed: {e}")

        return {"is_harmful": False, "matched_keywords": [], "method": "none"}

    async def _llm_detect(self, text: str) -> dict:
        """Use LLM to detect harmful content (stub for integration)."""
        # This would call the LLM with a classification prompt
        # For now, return not harmful
        return {"is_harmful": False, "confidence": 0.0}

    def add_keywords(self, keywords: list[str]):
        """Add custom keywords to detection list."""
        self.keywords.extend(keywords)
        self._rebuild_pattern()

    def remove_keyword(self, keyword: str):
        """Remove a keyword from detection list."""
        if keyword in self.keywords:
            self.keywords.remove(keyword)
            self._rebuild_pattern()

    def get_keywords(self) -> list[str]:
        """Get current keyword list."""
        return self.keywords.copy()


# Singleton instance - used by main.py and other modules
# No external dependencies needed
harmful_content_detector = HarmfulContentDetector()


def get_harmful_content_detector() -> HarmfulContentDetector:
    """Get the global harmful content detector instance."""
    return harmful_content_detector
