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
async def test_detect_multiple_keywords(detector):
    detector.keywords = ["spam", "scam", "fraud"]
    result = await detector.detect("This is spam and fraud")
    assert result["is_harmful"] is True
    assert len(result["matched_keywords"]) == 2


@pytest.mark.asyncio
async def test_add_custom_keywords(detector):
    detector.add_keywords(["custom_bad_word"])
    assert "custom_bad_word" in detector.keywords


@pytest.mark.asyncio
async def test_remove_keyword(detector):
    detector.keywords = ["spam", "scam"]
    detector.remove_keyword("spam")
    assert "spam" not in detector.keywords
    assert "scam" in detector.keywords


@pytest.mark.asyncio
async def test_get_keywords(detector):
    detector.keywords = ["spam", "scam"]
    keywords = detector.get_keywords()
    assert "spam" in keywords
    assert "scam" in keywords
    # Verify it's a copy
    keywords.append("test")
    assert "test" not in detector.keywords


@pytest.mark.asyncio
async def test_detect_thai_keywords(detector):
    detector.keywords = ["สแปม", "ฉ้อโกง", "หลอกลวง"]
    result = await detector.detect("ข้อความนี้เป็น สแปม")
    assert result["is_harmful"] is True
    assert "สแปม" in result["matched_keywords"]


@pytest.mark.asyncio
async def test_detect_returns_method(detector):
    detector.keywords = ["spam"]
    result = await detector.detect("spam message")
    assert result["method"] == "keyword"


@pytest.mark.asyncio
async def test_detect_clean_returns_none_method(detector):
    detector.keywords = ["spam"]
    result = await detector.detect("hello")
    assert result["method"] == "none"