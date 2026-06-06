import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


from services.debrief_extraction_service import DebriefSchema


def test_debrief_schema_validates_required_fields():
    debrief = DebriefSchema(
        topics_covered=["greetings", "weather"],
        comprehension_level="high",
        key_phrases_learned=["hello", "goodbye"],
        suggested_review=["practice greetings"],
    )
    assert debrief.comprehension_level == "high"
    assert len(debrief.topics_covered) == 2


def test_debrief_schema_accepts_minimal_payload():
    debrief = DebriefSchema(
        topics_covered=["greetings", "weather"],
        comprehension_level="high",
    )


def test_debrief_schema_default_topics_is_empty():
    debrief = DebriefSchema(comprehension_level="medium")
    assert debrief.topics_covered == []
    assert debrief.key_phrases_learned == []
    assert debrief.suggested_review == []
