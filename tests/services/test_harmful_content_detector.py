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


@pytest.mark.asyncio
async def test_remove_keyword(detector):
    detector.keywords = ["spam", "custom_bad_word"]
    detector.remove_keyword("spam")
    assert "spam" not in detector.keywords
    assert "custom_bad_word" in detector.keywords


@pytest.mark.asyncio
async def test_get_keywords(detector):
    detector.keywords = ["spam", "scam"]
    keywords = detector.get_keywords()
    assert "spam" in keywords
    assert "scam" in keywords
    # Should be a copy, not the original
    keywords.append("hacked")
    assert "hacked" not in detector.keywords
