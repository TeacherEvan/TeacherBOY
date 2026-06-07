"""Tests for debrief schema to formatter conversion."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.debrief_extraction_service import DailyDebriefSchema, PeriodDebriefSchema
from services.debrief_formatter import DebriefFormatter


def test_daily_debrief_schema_converts_to_formatter():
    """Test that DailyDebriefSchema produces correct formatted output via format_daily_debrief."""
    debrief = DailyDebriefSchema(
        date="2025-01-17",
        day_name="Friday",
        periods=[
            PeriodDebriefSchema(
                period="Period 1",
                subject="Science",
                teacher="Lea",
                lesson="States of Matter - Water, Gas and Ice",
                topics_covered=["solid", "liquid", "gas", "melting", "freezing"],
                comprehension_level="high",
                key_phrases_learned=["solid", "liquid", "gas", "melting", "freezing"],
                suggested_review=[],
                observations="Students were responsive and intrigued by demonstrations",
            ),
            PeriodDebriefSchema(
                period="Period 2",
                subject="English",
                teacher="Evan",
                lesson="Phonics - Short Vowel Sounds",
                topics_covered=["short vowel sounds", "phonics"],
                comprehension_level="medium",
                key_phrases_learned=["cat", "hat", "bat", "mat", "sat"],
                suggested_review=["Practice short 'e' sound"],
                observations="Teacher Evan engaged children with fun phonics games",
            ),
        ],
        general_observations="All students were well-behaved and engaged today.",
        confidence_score=0.9,
        notes="Excellent day!",
    )

    message = DebriefFormatter.format_daily_debrief(debrief)

    assert "Friday, January 17, 2025" in message
    assert "Lea" in message
    assert "Evan" in message
    assert "Science" in message
    assert "English" in message
    assert "States of Matter" in message
    assert "Phonics" in message
    assert "cat, hat, bat, mat, sat" in message
    assert "solid, liquid, gas" in message
    assert "high" in message.lower() or "High" in message
    assert "medium" in message.lower() or "Medium" in message
    assert "gentle suggestion" in message.lower()
    assert "short 'e' sound" in message
    assert "positive note" in message.lower()
    assert "smarter" in message.lower()
    assert "Teacher Evan & The Ms. Green Team" in message
    assert "👋" in message
    assert "🍎" in message


def test_format_single_session_backward_compatibility():
    """Test that the legacy format_single_session still works."""
    session = {
        "date": "2026-01-01",
        "timePeriod": "null",
        "subject": "null",
        "lesson": "null",
        "teacher": "null",
        "observations": "Null observation",
    }

    message = DebriefFormatter.format_single_session(session)

    assert "null" not in message.lower() or "the teacher" in message
    assert "2026-01-01" in message


def test_format_weekly_summary():
    """Test weekly summary formatting."""
    sessions = [
        {
            "date": "2026-02-03",
            "subject": "English",
            "lesson": "Phonics",
            "teacher": "Teacher Evan",
        },
        {
            "date": "2026-02-04",
            "subject": "Science",
            "lesson": "Plants",
            "teacher": "Ms. Green",
        },
    ]

    message = DebriefFormatter.format_weekly_summary(sessions, "2026-02-02 to 2026-02-09")

    assert "Teacher Evan" in message
    assert "Ms. Green" in message
    assert "English" in message
    assert "Phonics" in message
    assert "Science" in message
    assert "Plants" in message
    assert "Teacher Evan & The Ms. Green Team" in message


if __name__ == "__main__":
    test_daily_debrief_schema_converts_to_formatter()
    test_format_single_session_backward_compatibility()
    test_format_weekly_summary()
    print("All tests passed!")
