"""
Debrief Formatter - Generates warm, emoji-rich parent-facing messages from structured journal data.
"""
from __future__ import annotations

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class DebriefFormatter:
    @staticmethod
    def format_single_session(session: Dict[str, Any]) -> str:
        """Formats a single debrief session for a parent-facing LINE message."""
        date = session.get("date", "Today")
        time_period = session.get("timePeriod") or "the day"
        subject = session.get("subject") or "class"
        lesson = session.get("lesson") or "the lesson"
        teacher = session.get("teacher") or "the teacher"
        observations = session.get("observations", "The students had a wonderful time learning and exploring new concepts!")

        # Clean up nulls from LLM
        if time_period == "null": time_period = "the day"
        if subject == "null": subject = "class"
        if lesson == "null": lesson = "the lesson"
        if teacher == "null": teacher = "the teacher"

        return (
            f"📅 *{date}* ✨\n\n"
            f"As the day blessed us with the magic of knowledge, during *{time_period}*, "
            f"{teacher} spoiled the children with fun *{lesson}* lessons 🎵 in *{subject}*, "
            f"focusing on each individual student's needs.\n\n"
            f"📝 *Key Observations:*\n{observations}\n\n"
            f"🌟 What a wonderful day of learning!"
        )

    @staticmethod
    def format_weekly_summary(sessions: List[Dict[str, Any]], week_range: str) -> str:
        """Formats multiple sessions into a cohesive weekly summary."""
        if not sessions:
            return "📅 *Weekly Journal Summary*\n\nNo journal entries were recorded this week. Everyone had a restful break! 🌿"

        header = f"📅 *Weekly Journal Summary: {week_range}* ✨\n\n"
        header += "What a fantastic week of learning and growth! Here's a look at what your children accomplished:\n\n"

        daily_blocks = []
        for session in sessions:
            date = session.get("date", "Unknown Date")
            subject = session.get("subject") or "Various Subjects"
            lesson = session.get("lesson") or "General Learning"
            teacher = session.get("teacher") or "the teaching team"
            
            daily_blocks.append(
                f"🗓️ *{date}*\n"
                f"➡️ {teacher} led engaging *{lesson}* activities in *{subject}*.\n"
            )

        footer = (
            "\n🌟 We are so proud of the curiosity and effort every student showed this week. "
            "Have a wonderful, restful weekend!\n\n"
            "— *Teacher Evan & The Ms. Green Team* 🍎"
        )

        return header + "\n".join(daily_blocks) + footer
