import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.debrief_extraction_service import DebriefSchema
import pytest


def test_debrief_schema_validates_required_fields():
    debrief = DebriefSchema(
        topics_covered=["greetings", "weather"],
        comprehension_level="high",
        key_phrases_learned=["hello", "goodbye"],
        suggested_review=["practice greetings"],
    )
    assert debrief.comprehension_level == "high"
    assert len(debrief.topics_covered) == 2


def test_debrief_schema_rejects_empty_topics():
    with pytest.raises(Exception):
        DebriefSchema(
            topics_covered=[],
            comprehension_level="low",
        )
