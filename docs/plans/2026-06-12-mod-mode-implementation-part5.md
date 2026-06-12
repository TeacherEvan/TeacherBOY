### Task 5: Create HarmfulContentDetector

**Objective:** Keyword + optional LLM-based harmful content detection for `/modmode all`.

**Files:**
- Create: `src/services/harmful_content_detector.py`
- Test: `tests/services/test_harmful_content_detector.py`

**Step 1: Write failing test**

```python
# tests/services/test_harmful_content_detector.py
import pytest
from src.services.harmful_content_detector import HarmfulContentDetector

@pytest.fixture
def detector():
    return HarmfulContentDetector()

@pytest.mark.asyncio
async def test_detect_keyword_harmful(detector):
    detector.keywords = ["spam", "scam", "hate"]
    result = await detector.detect("This is spam message")
    assert result["is_harmful"] is True
    assert "spam" in result["matched_keywords"]

@pytest.mark.asyncio
async def test_detect_clean_message(detector):
    detector.keywords = ["spam", "scam"]
    result = await detector.detect("Hello world")
    assert result["is_harmful"] is False

@pytest.mark.asyncio
async def test_detect_case_insensitive(detector):
    detector.keywords = ["SPAM"]
    result = await detector.detect("This is Spam")
    assert result["is_harmful"] is True

@pytest.mark.asyncio
async def test_add_custom_keywords(detector):
    detector.add_keywords(["custom_bad_word"])
    assert "custom_bad_word" in detector.keywords
```

**Step 2: Run test to verify failure**

```bash
pytest tests/services/test_harmful_content_detector.py -v
```

**Step 3: Write implementation**

```python
# src/services/harmful_content_detector.py
"""Keyword + optional LLM harmful content detection."""

from typing: Optional
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

    def __init__(self, keywords: Optional[list[str]] = None, llm_client=None):
        self.keywords = keywords or self.DEFAULT_KEYWORDS.copy()
        self._llm_client = llm_client  # Optional: for LLM-based detection
        self._llm_enabled = llm_client is not None

    async def detect(self, text: str) -> dict:
        """Detect harmful content in text.
        
        Returns:
            dict with: is_harmful (bool), matched_keywords (list), llm_result (optional)
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
```

**Step 4: Run test to verify pass**

```bash
pytest tests/services/test_harmful_content_detector.py -v
```

**Step 5: Commit**

```bash
git add src/services/harmful_content_detector.py tests/services/test_harmful_content_detector.py
git commit -m "feat(mod-mode): add HarmfulContentDetector"
```