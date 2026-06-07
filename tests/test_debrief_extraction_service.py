import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unittest.mock import AsyncMock, patch

import pytest

from services.debrief_extraction_service import (
    DailyDebriefSchema,
    DebriefExtractionService,
    PeriodDebriefSchema,
)


@pytest.fixture
def service():
    return DebriefExtractionService(llm_vision_fn=AsyncMock())


@pytest.mark.asyncio()
async def test_extract_from_image_returns_validated_daily_debrief_schema(service):
    expected = DailyDebriefSchema(
        date="2025-01-01",
        day_name="Wednesday",
        periods=[
            PeriodDebriefSchema(
                period="Period 1",
                subject="Science",
                teacher="Lea",
                lesson="States of Matter",
                topics_covered=["feelings", "greetings"],
                comprehension_level="high",
                key_phrases_learned=["how are you", "good morning"],
                suggested_review=["practice tones"],
                observations="Great progress!",
            )
        ],
        general_observations="Wonderful day",
        confidence_score=0.9,
        notes="Great progress!",
    )

    async def return_model(*args, **kwargs):
        return expected

    with patch.object(service, "_try_structured_extraction", return_model):
        result = await service.extract_from_image(
            image_url_or_base64="data:image/png;base64,AAA",
            chat_id="chat_1",
            date_str="2025-01-01",
        )

    assert isinstance(result, DailyDebriefSchema)
    assert result.day_name == "Wednesday"
    assert result.confidence_score == pytest.approx(0.9)
    assert len(result.periods) == 1
    assert result.periods[0].teacher == "Lea"
    assert result.periods[0].comprehension_level == "high"


@pytest.mark.asyncio()
async def test_extract_from_image_rejects_invalid_json_and_uses_fallback(service):
    with patch.object(service, "_try_structured_extraction", return_value=None):
        result = await service.extract_from_image(
            image_url_or_base64="data:image/png;base64,AAA",
            chat_id="chat_1",
            date_str="2025-01-01",
        )

    # Even when structured extraction fails, the service must return a typed schema.
    assert isinstance(result, DailyDebriefSchema)
    assert result.periods == []
    assert result.confidence_score == 0.0
    assert "Extraction failed" in result.notes


@pytest.mark.asyncio()
async def test_extract_from_image_returns_daily_debrief_schema_from_dict_payload(service):
    """Validate that a dict-like payload from llm_vision_fn becomes a DailyDebriefSchema."""
    payload = {
        "date": "2025-01-01",
        "day_name": "Wednesday",
        "periods": [
            {
                "period": "Period 1",
                "subject": "Science",
                "teacher": "Lea",
                "lesson": "States of Matter",
                "topics_covered": ["topic"],
                "comprehension_level": "medium",
                "key_phrases_learned": [],
                "suggested_review": [],
                "observations": None,
            }
        ],
        "general_observations": None,
        "confidence_score": 0.5,
        "notes": None,
    }
    fake_llm = AsyncMock(return_value=json.dumps(payload))
    updated = DebriefExtractionService(llm_vision_fn=fake_llm)

    result = await updated.extract_from_image(
        image_url_or_base64="data:image/png;base64,AAA",
        chat_id="chat_1",
        date_str="2025-01-01",
    )
    assert isinstance(result, DailyDebriefSchema)
    assert result.day_name == "Wednesday"
    assert len(result.periods) == 1
    assert result.periods[0].subject == "Science"
    assert result.periods[0].teacher == "Lea"
