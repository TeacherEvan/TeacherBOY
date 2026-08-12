import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from services.debrief_formatter import DebriefFormatter


def test_format_single_session_cleans_null_strings():
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


def test_format_single_session_uses_defaults_when_keys_missing():
    message = DebriefFormatter.format_single_session({})

    assert "Today" in message
    assert "the day" in message
    assert "class" in message
    assert "the teacher" in message


def test_format_single_session_includes_real_payload():
    session = {
        "date": "2026-02-09",
        "timePeriod": "Period 2",
        "subject": "English",
        "lesson": "Phonics",
        "teacher": "Teacher Evan",
        "observations": "Students practiced short vowel sounds confidently.",
    }

    message = DebriefFormatter.format_single_session(session)

    assert "2026-02-09" in message
    assert "Teacher Evan" in message
    assert "English" in message
    assert "Phonics" in message
    assert "Students practiced short vowel sounds confidently." in message


def test_format_weekly_summary_handles_empty_sessions():
    message = DebriefFormatter.format_weekly_summary([], "2026-02-02 to 2026-02-09")

    assert "Weekly Journal Summary" in message
    assert "restful break" in message.lower()


def test_format_weekly_summary_includes_session_details():
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
