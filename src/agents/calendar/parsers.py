"""
Calendar Date Parsing - Extracted from main agent.
Handles various date formats for inline event creation.
"""

import logging
import re
from datetime import datetime, timedelta

from src.services.bot_identity_service import get_bot_identity_service

logger = logging.getLogger(__name__)


class DateParser:
    """Parse various date formats for calendar events."""

    MONTH_MAP = {
        "jan": 1,
        "january": 1,
        "feb": 2,
        "february": 2,
        "mar": 3,
        "march": 3,
        "apr": 4,
        "april": 4,
        "may": 5,
        "jun": 6,
        "june": 6,
        "jul": 7,
        "july": 7,
        "aug": 8,
        "august": 8,
        "sep": 9,
        "sept": 9,
        "september": 9,
        "oct": 10,
        "october": 10,
        "nov": 11,
        "november": 11,
        "dec": 12,
        "december": 12,
    }

    @staticmethod
    def parse_inline_date(text: str) -> tuple[datetime, str] | None:
        """
        Parse 'zeus add [date] [title]' format.

        Supported formats:
        - tomorrow
        - today
        - in X days
        - Jan 15, January 15
        - 15/01/2025 (DD/MM/YYYY)
        - 2025-06-15 (YYYY-MM-DD)

        Args:
            text: Input text with date and title

        Returns:
            Tuple of (parsed_date, remaining_title) or None
        """
        prefix, rest = get_bot_identity_service().split_command_prefix(text)
        if prefix and rest.lower().startswith("add "):
            text = rest[4:].strip()
        else:
            text = re.sub(r"^zeus\s+add\s+", "", text, flags=re.IGNORECASE).strip()

        if not text:
            return None

        # Try: tomorrow
        if text.lower().startswith("tomorrow"):
            date = datetime.now() + timedelta(days=1)
            title = text[8:].strip()  # Remove 'tomorrow'
            if title:
                return (date, title)

        # Try: today
        if text.lower().startswith("today"):
            date = datetime.now()
            title = text[5:].strip()  # Remove 'today'
            if title:
                return (date, title)

        # Try: in X days
        match = re.match(r"in\s+(\d+)\s+days?\s+(.+)", text, re.IGNORECASE)
        if match:
            days = int(match.group(1))
            title = match.group(2).strip()
            if title:
                date = datetime.now() + timedelta(days=days)
                return (date, title)

        # Try: Month Day format (Jan 15, January 15)
        month_pattern = "|".join(DateParser.MONTH_MAP.keys())
        match = re.match(rf"({month_pattern})\s+(\d{{1,2}})\s+(.+)", text, re.IGNORECASE)
        if match:
            month_str = match.group(1).lower()
            day = int(match.group(2))
            title = match.group(3).strip()

            if title and month_str in DateParser.MONTH_MAP:
                month = DateParser.MONTH_MAP[month_str]
                year = datetime.now().year

                try:
                    date = datetime(year, month, day)

                    # If date is in past, use next year
                    if date < datetime.now():
                        date = datetime(year + 1, month, day)

                    return (date, title)
                except ValueError:
                    logger.warning(f"Invalid date: month={month}, day={day}")

        # Try: DD/MM/YYYY format
        match = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})\s+(.+)", text)
        if match:
            day = int(match.group(1))
            month = int(match.group(2))
            year = int(match.group(3))
            title = match.group(4).strip()

            if title:
                try:
                    date = datetime(year, month, day)
                    return (date, title)
                except ValueError:
                    logger.warning(f"Invalid date: {day}/{month}/{year}")

        # Try: YYYY-MM-DD format (ISO)
        match = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})\s+(.+)", text)
        if match:
            year = int(match.group(1))
            month = int(match.group(2))
            day = int(match.group(3))
            title = match.group(4).strip()

            if title:
                try:
                    date = datetime(year, month, day)
                    return (date, title)
                except ValueError:
                    logger.warning(f"Invalid date: {year}-{month}-{day}")

        return None

    @staticmethod
    def format_date_display(date: datetime) -> str:
        """
        Format date for user-friendly display.

        Args:
            date: Datetime object

        Returns:
            Formatted string like "Jan 15, 2026"
        """
        return date.strftime("%b %d, %Y")

    @staticmethod
    def is_past_date(date: datetime) -> bool:
        """Check if date is in the past."""
        return date.replace(hour=0, minute=0, second=0, microsecond=0) < datetime.now().replace(
            hour=0, minute=0, second=0, microsecond=0
        )
