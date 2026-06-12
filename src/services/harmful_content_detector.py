"""Keyword + optional LLM harmful content detection."""

import logging

logger = logging.getLogger(__name__)


class HarmfulContentDetector:
    """Detect harmful content using keywords and optional LLM."""

    DEFAULT_KEYWORDS = [
        # English
        "spam", "scam", "fraud", "phishing", "malware", "virus",
        "hate", "harassment", "threat", "violence", "illegal",
        "drugs", "weapon", "bomb", "terrorist", "extremist",
        # Thai (common harmful terms)
        "สแปม", "ฉ้อโกง", "หลอกลวง", "เกยหรือ", "วางไวรัส",
        "เกลียด", "ข่มขู่", "คุกคาม", "ความรุนแรง", "ผิดกฎหมาย",
        "ยาเสพติด", "อาวุธ", "ระเบิด", "ขบวนการสุดขั้ว",
    ]

    def __init__(self, keywords: list[str] | None = None, llm_client=None):
        self.keywords = keywords or self.DEFAULT_KEYWORDS.copy()
        self._llm_client = llm_client  # Optional: for LLM-based detection
        self._llm_enabled = llm_client is not None

    async def detect(self, text: str) -> dict:
        """Detect harmful content in text.

        Returns:
            dict with: is_harmful (bool), matched_keywords (list), method (str), llm_result (optional)
        """
        text_lower = text.lower()
        matched = [kw for kw in self.keywords if kw.lower() in text_lower]

        if matched:
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

    def remove_keyword(self, keyword: str):
        """Remove a keyword from detection list."""
        if keyword in self.keywords:
            self.keywords.remove(keyword)

    def get_keywords(self) -> list[str]:
        """Get current keyword list."""
        return self.keywords.copy()


# Singleton instance - used by main.py and other modules
# No external dependencies needed
harmful_content_detector = HarmfulContentDetector()


def get_harmful_content_detector() -> HarmfulContentDetector:
    """Get the global harmful content detector instance."""
    return harmful_content_detector