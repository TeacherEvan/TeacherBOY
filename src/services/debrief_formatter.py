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

        # Try to parse and format date nicely
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
            "phonics": "🔤",
        }

        def get_subject_emoji(subject: str) -> str:
            subj_lower = subject.lower()
            for key, emoji in subject_emojis.items():
                if key in subj_lower:
                    return emoji
            return "✨"

        # Build the message
        lines = []
        lines.append(f"📅 *{formatted_date}* ✨")
        lines.append("")

        # Opening warmth
        lines.append(f"On this wonderful {day_name}, our students embarked on a beautiful journey of learning and discovery! 🌈")
        lines.append("")

        # Process each period
        for i, period in enumerate(debrief.periods, 1):
            period_label = period.period or f"Period {i}"
            subject = period.subject or "Learning"
            teacher = period.teacher or "the teacher"
            lesson = period.lesson or "the lesson"
            emoji = get_subject_emoji(subject)

            # Period header
            lines.append(f"{emoji} *{period_label} - {subject}*")

            # Teacher and lesson description with warmth
            lines.append(f"Our students had an intriguing lesson with *{teacher}* regarding *{lesson}*!")

            # Observations if available
            if period.observations:
                lines.append(f"💫 {period.observations}")

            # Topics covered
            if period.topics_covered:
                topics_str = ", ".join(period.topics_covered)
                lines.append(f"📚 Topics explored: {topics_str}")

            # Key phrases
            if period.key_phrases_learned:
                phrases_str = ", ".join(period.key_phrases_learned)
                lines.append(f"🗣️ Key words practiced: {phrases_str}")

            # Comprehension
            comp_emoji = "🌟" if period.comprehension_level == "high" else "🌱" if period.comprehension_level == "medium" else "🌿"
            if period.comprehension_level == "high":
                comp_text = f"{comp_emoji} Comprehension: *{period.comprehension_level.title()}* - All students participated actively and grasped concepts beautifully!"
            elif period.comprehension_level == "medium":
                comp_text = f"{comp_emoji} Comprehension: *{period.comprehension_level.title()}* - Most students understood well, some may benefit from gentle review."
            else:
                comp_text = f"{comp_emoji} Comprehension: *{period.comprehension_level.title()}* - This is a new concept; we'll continue nurturing understanding."
            lines.append(comp_text)

            # Suggested review
            if period.suggested_review:
                review_str = "; ".join(period.suggested_review)
                lines.append(f"📝 *Gentle suggestion for home:* {review_str}")

            lines.append("")  # Empty line between periods

        # General observations
        if debrief.general_observations:
            lines.append("🌸 *General Observations:*")
            lines.append(debrief.general_observations)
            lines.append("")

        # Closing warmth
        lines.append("🌟 What a wonderful day of learning and growth!")
        lines.append("")
        lines.append(
            f"We end this beautiful {day_name} on a positive note, "
            f"knowing all our students went home smarter than when they arrived "
            f"and more prepared for their bright futures! 🌈"
        )
        lines.append("")
        lines.append(
            "As always, we deeply appreciate all your support and trust in us. "
            "Wishing you a wonderful evening and a joyful weekend ahead! 🌙✨"
        )
        lines.append("")
        lines.append("See you Monday! 👋🍎")
        lines.append("")
        lines.append("— *Teacher Evan & The Ms. Green Team* 💚")

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
                "📅 *Weekly Journal Summary*\n\n"
                "No journal entries were recorded this week. Everyone had a restful break! 🌿"
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
