"""Debrief Formatter - Generates warm, emoji-rich parent-facing messages from structured journal data."""

from __future__ import annotations

import logging
from typing import Any

from src.services.debrief_extraction_service import DailyDebriefSchema

logger = logging.getLogger(__name__)


class DebriefFormatter:
    @staticmethod
    def format_daily_debrief(debrief: DailyDebriefSchema) -> str:
        """Formats a full daily debrief with multiple periods for a parent-facing LINE message."""
        # Format date nicely
        day_name = debrief.day_name
        date_str = debrief.date

        try:
            from datetime import datetime

            dt = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = dt.strftime("%A, %B %d, %Y")
        except Exception:
            formatted_date = f"{day_name}, {date_str}"

        # Emojis for different subjects
        subject_emojis = {
            "science": "🔬",
            "english": "📖",
            "phonics": "🔤",
            "mathematics": "🧮",
            "math": "🧮",
            "art": "🎨",
            "physical education": "🏃",
            "pe": "🏃",
            "music": "🎵",
            "history": "📜",
            "geography": "🌍",
            "language": "🗣️",
            "reading": "📚",
            "writing": "✍️",
        }

        def get_subject_emoji(subject: str) -> str:
            subj_lower = subject.lower()
            for key, emoji in subject_emojis.items():
                if key in subj_lower:
                    return emoji
            return "✨"

        lines = []

        # ── Header ────────────────────────────────────────────────────────────
        lines.append(f"📝 Daily Learning Journal — {formatted_date} 🌸")
        lines.append("")
        lines.append("Dear Parents,")
        lines.append("")
        lines.append(
            "I hope this message finds you well and that your evening is off to a beautiful start. 😊"
        )
        lines.append("")
        lines.append(
            "Today our children had a wonderful day of discovery! "
            "Here is a warm summary of what they experienced:"
        )
        lines.append("")

        # ── Periods ───────────────────────────────────────────────────────────
        for i, period in enumerate(debrief.periods, 1):
            period_label = period.period or f"Period {i}"
            subject = period.subject or "Learning"
            teacher = period.teacher or "the teacher"
            lesson = period.lesson or "the lesson"
            emoji = get_subject_emoji(subject)

            lines.append(f"{emoji} {period_label} — {subject} with {teacher}")

            lines.append(f"• Lesson Focus: {lesson}")

            if period.topics_covered:
                topics_str = ", ".join(period.topics_covered)
                lines.append(f"• Topics Explored: {topics_str}")

            if period.key_phrases_learned:
                phrases_str = ", ".join(period.key_phrases_learned)
                lines.append(f"• Key Vocabulary Practiced: {phrases_str}")

            if period.observations:
                lines.append(f"• Observations: {period.observations}")

            # Comprehension level
            comp_map = {
                "high": ("🌟", "Excellent — students grasped concepts with great confidence!"),
                "medium": ("🌱", "Good — most students understood well; gentle review may help."),
                "low": ("🌿", "Developing — a new concept; continued nurturing will help."),
            }
            comp_emoji, comp_text = comp_map.get(
                period.comprehension_level, ("📊", period.comprehension_level.title())
            )
            lines.append(f"• Comprehension: {comp_emoji} {comp_text}")

            if period.suggested_review:
                review_str = "; ".join(period.suggested_review)
                lines.append(f"🌱 Gentle Home Review Suggestion: {review_str}")

            lines.append("")  # blank line between periods

        # ── General observations ───────────────────────────────────────────────
        if debrief.general_observations:
            lines.append("🌸 General Observations:")
            lines.append(debrief.general_observations)
            lines.append("")

        # ── Closing ───────────────────────────────────────────────────────────
        lines.append(
            "Wishing you all a peaceful and restful evening ahead. "
            "Thank you for your continued love and trust. 💚"
        )
        lines.append("")
        lines.append("— Teacher Evan & The Ms. Green Team 🍎")

        return "\n".join(lines)

    @staticmethod
    def format_single_session(session: dict[str, Any]) -> str:
        """Legacy single-session formatter (backward compatibility)."""
        date = session.get("date", "Today")
        time_period = session.get("timePeriod") or "the day"
        subject = session.get("subject") or "class"
        lesson = session.get("lesson") or "the lesson"
        teacher = session.get("teacher") or "the teacher"
        observations = session.get("observations", "The students had a wonderful time learning and exploring new concepts!")

        # Clean up nulls from LLM
        if time_period == "null":
            time_period = "the day"
        if subject == "null":
            subject = "class"
        if lesson == "null":
            lesson = "the lesson"
        if teacher == "null":
            teacher = "the teacher"

        return (
            f"📅 *{date}* ✨\n\n"
            f"As the day blessed us with the magic of knowledge, during *{time_period}*, "
            f"{teacher} spoiled the children with fun *{lesson}* lessons 🎵 in *{subject}*, "
            f"focusing on each individual student's needs.\n\n"
            f"📝 *Key Observations:*\n{observations}\n\n"
            f"🌟 What a wonderful day of learning!"
        )

    @staticmethod
    def format_weekly_summary(sessions: list[dict[str, Any]], week_range: str) -> str:
        """Formats multiple sessions into a cohesive weekly summary."""
        if not sessions:
            return (
                "📅 *Weekly Journal Summary*\n\nNo journal entries were recorded this week. Everyone had a restful break! 🌿"
            )

        header = f"📅 *Weekly Journal Summary: {week_range}* ✨\n\n"
        header += "What a fantastic week of learning and growth! Here's a look at what your children accomplished:\n\n"

        daily_blocks = []
        for session in sessions:
            date = session.get("date", "Unknown Date")
            subject = session.get("subject") or "Various Subjects"
            lesson = session.get("lesson") or "General Learning"
            teacher = session.get("teacher") or "the teaching team"

            daily_blocks.append(f"🗓️ *{date}*\n➡️ {teacher} led engaging *{lesson}* activities in *{subject}*.\n")

        footer = (
            "\n🌟 We are so proud of the curiosity and effort every student showed this week. "
            "Have a wonderful, restful weekend!\n\n"
            "— *Teacher Evan & The Ms. Green Team* 🍎"
        )

        return header + "\n".join(daily_blocks) + footer
