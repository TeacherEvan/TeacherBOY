"""
Calendar Input Validation Service - Security-focused input sanitization.

This service provides comprehensive validation for calendar event data:
- Title and description sanitization (XSS prevention)
- Length limits enforcement
- Date range validation
- Banned character filtering
- SQL injection prevention
"""

import logging
import re
from datetime import date, timedelta
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Security constants
MAX_TITLE_LENGTH = 200
MAX_DESCRIPTION_LENGTH = 1000
MAX_FUTURE_YEARS = 5
# Characters stripped for defense-in-depth (XSS + common injection delimiters)
BANNED_CHARS_PATTERN = re.compile(r"[<>{}\[\]\\`'\";]")
CONTROL_CHARS_PATTERN = re.compile(r'[\x00-\x1F\x7F]')  # Control characters


class ValidationError(Exception):
    """Raised when input validation fails."""
    pass


class CalendarValidator:
    """
    Validates and sanitizes calendar event inputs.
    
    Enforces security best practices:
    - XSS prevention via character filtering
    - Length limits to prevent DoS
    - Date range validation
    - Control character removal
    """

    def __init__(
        self,
        max_title_length: int = MAX_TITLE_LENGTH,
        max_description_length: int = MAX_DESCRIPTION_LENGTH,
        max_future_years: int = MAX_FUTURE_YEARS,
    ):
        """
        Initialize validator with custom limits.
        
        Args:
            max_title_length: Maximum characters in event title
            max_description_length: Maximum characters in description
            max_future_years: Maximum years into the future for events
        """
        self.max_title_length = max_title_length
        self.max_description_length = max_description_length
        self.max_future_years = max_future_years
        
        logger.info(
            f"✅ CalendarValidator initialized "
            f"(title:{max_title_length}, desc:{max_description_length}, years:{max_future_years})"
        )

    def validate_title(self, title: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate and sanitize event title.
        
        Args:
            title: Raw event title
            
        Returns:
            Tuple of (is_valid, sanitized_title, error_message)
        """
        if not title or not title.strip():
            return False, None, "Event title cannot be empty"
        
        # Remove control characters
        title = CONTROL_CHARS_PATTERN.sub('', title)
        title = title.strip()
        
        # Check length
        if len(title) > self.max_title_length:
            return False, None, f"Title too long (max {self.max_title_length} characters)"
        
        # Check for banned characters (XSS prevention)
        if BANNED_CHARS_PATTERN.search(title):
            # Remove banned chars instead of rejecting
            title = BANNED_CHARS_PATTERN.sub('', title)
            logger.warning(f"⚠️ Removed banned characters from title: {title[:50]}...")
        
        # Ensure not all spaces after sanitization
        if not title.strip():
            return False, None, "Title contains only invalid characters"
        
        return True, title, None

    def validate_description(self, description: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Validate and sanitize event description.
        
        Args:
            description: Raw event description
            
        Returns:
            Tuple of (is_valid, sanitized_description, error_message)
        """
        # Empty description is allowed
        if not description:
            return True, "", None
        
        # Remove control characters
        description = CONTROL_CHARS_PATTERN.sub('', description)
        description = description.strip()
        
        # Check length
        if len(description) > self.max_description_length:
            # Truncate instead of rejecting
            description = description[:self.max_description_length]
            logger.warning(f"⚠️ Truncated description to {self.max_description_length} chars")
        
        # Check for banned characters (XSS prevention)
        if BANNED_CHARS_PATTERN.search(description):
            # Remove banned chars
            description = BANNED_CHARS_PATTERN.sub('', description)
            logger.warning(f"⚠️ Removed banned characters from description")
        
        return True, description, None

    def validate_date(self, event_date: date) -> Tuple[bool, Optional[str]]:
        """
        Validate event date.
        
        Args:
            event_date: Event date to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        today = date.today()
        
        # Check if date is in the past
        if event_date < today:
            return False, "Event date cannot be in the past"
        
        # Check if date is too far in the future
        max_future_date = today + timedelta(days=365 * self.max_future_years)
        if event_date > max_future_date:
            return False, f"Event date cannot be more than {self.max_future_years} years in the future"
        
        return True, None

    def validate_reminder_days(self, reminder_days: list) -> Tuple[bool, Optional[list], Optional[str]]:
        """
        Validate reminder days configuration.
        
        Args:
            reminder_days: List of days before event to send reminders
            
        Returns:
            Tuple of (is_valid, sanitized_reminder_days, error_message)
        """
        if not reminder_days:
            # Default to day-of reminder
            return True, [0], None
        
        # Remove duplicates and sort
        reminder_days = sorted(set(reminder_days))
        
        # Validate each value
        valid_days = []
        for days in reminder_days:
            if not isinstance(days, int):
                continue
            if days < 0:
                continue
            if days > 365:  # Max 1 year reminder
                continue
            valid_days.append(days)
        
        if not valid_days:
            return False, None, "No valid reminder days provided"
        
        # Ensure day-of reminder is included
        if 0 not in valid_days:
            valid_days.append(0)
            valid_days.sort()
        
        return True, valid_days, None

    def validate_event(
        self,
        title: str,
        event_date: date,
        description: str = "",
        reminder_days: Optional[list] = None
    ) -> Tuple[bool, Optional[dict], Optional[str]]:
        """
        Validate complete event data.
        
        Args:
            title: Event title
            event_date: Event date
            description: Event description
            reminder_days: Reminder days configuration
            
        Returns:
            Tuple of (is_valid, sanitized_data_dict, error_message)
        """
        # Validate title
        title_valid, sanitized_title, title_error = self.validate_title(title)
        if not title_valid:
            return False, None, title_error
        
        # Validate description
        desc_valid, sanitized_desc, desc_error = self.validate_description(description)
        if not desc_valid:
            return False, None, desc_error
        
        # Validate date
        date_valid, date_error = self.validate_date(event_date)
        if not date_valid:
            return False, None, date_error
        
        # Validate reminder days
        reminder_valid, sanitized_reminders, reminder_error = self.validate_reminder_days(
            reminder_days or [0]
        )
        if not reminder_valid:
            return False, None, reminder_error
        
        # Return sanitized data
        sanitized_data = {
            "title": sanitized_title,
            "description": sanitized_desc,
            "event_date": event_date,
            "reminder_days": sanitized_reminders,
        }
        
        logger.debug(f"✅ Event validated: {sanitized_title} on {event_date}")
        return True, sanitized_data, None


# Singleton instance
calendar_validator = CalendarValidator()
