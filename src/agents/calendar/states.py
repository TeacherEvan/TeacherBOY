"""
Calendar Agent State Machine - Separated for clarity.
All session states used in multi-step flows.
"""

from enum import Enum


class CalendarState(Enum):
    """Session states for calendar multi-step flows."""

    IDLE = "idle"
    AWAITING_ACTION = "awaiting_action"
    AWAITING_EVENT_TITLE = "awaiting_event_title"
    AWAITING_EVENT_DATE = "awaiting_event_date"
    AWAITING_REMINDER_SELECTION = "awaiting_reminder_selection"
    EXTRACTING_DATES = "extracting_dates"
    AWAITING_EXTRACTED_DATE_RESPONSE = "awaiting_extracted_date_response"
    AWAITING_BULK_REMINDER = "awaiting_bulk_reminder"
    AWAITING_REMOVE_SELECTION = "awaiting_remove_selection"
    AWAITING_REMOVE_CONFIRMATION = "awaiting_remove_confirmation"
    IMAGE_EXTRACTION_STARTED = "image_extraction_started"
    AWAITING_IMAGE_EXTRACTED_DATE_RESPONSE = "awaiting_image_extracted_date_response"
    AWAITING_IMAGE_BULK_REMINDER = "awaiting_image_bulk_reminder"


def is_active_state(state: str) -> bool:
    """Check if state represents an active multi-step flow."""
    return state != CalendarState.IDLE.value
