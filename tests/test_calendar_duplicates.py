"""Tests for calendar duplicate detection and Zeus scraping own messages."""

import pytest
from datetime import date, timedelta
from src.services.calendar_service import CalendarService


class TestCalendarDuplicates:
    """Test calendar duplicate detection."""

    @pytest.fixture
    def calendar_service(self):
        """Create calendar service with local storage only."""
        service = CalendarService(
            hf_token=None,
            hf_repo_id=None,
            local_storage_path="./test_calendar_duplicates",
            encryption_key=None,
        )
        yield service
        # Cleanup
        import shutil
        import pathlib
        test_path = pathlib.Path("./test_calendar_duplicates")
        if test_path.exists():
            shutil.rmtree(test_path)

    def test_duplicate_detection_same_user_same_chat(self, calendar_service):
        """Test that duplicates are detected for same user in same chat."""
        user_id = "U123456"
        chat_id = "group_G123"
        title = "Team Meeting"
        event_date = date.today() + timedelta(days=7)

        # Add first event
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
            description="Weekly sync",
            reminder_days=[7, 1, 0],
        )
        assert event1 is not None

        # Check duplicate detection
        has_dup = calendar_service.has_duplicate_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
        )
        assert has_dup is True

        # Attempt to add duplicate (should raise ValueError)
        with pytest.raises(ValueError) as exc_info:
            calendar_service.add_event(
                user_id=user_id,
                chat_id=chat_id,
                title=title,
                event_date=event_date,
                description="Another sync",
                reminder_days=[3, 0],
            )
        assert "Duplicate" in str(exc_info.value)

    def test_duplicate_detection_case_insensitive(self, calendar_service):
        """Test that duplicate detection is case-insensitive."""
        user_id = "U123456"
        chat_id = "group_G123"
        event_date = date.today() + timedelta(days=7)

        # Add event with uppercase title
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="TEAM MEETING",
            event_date=event_date,
        )
        assert event1 is not None

        # Check lowercase version is detected as duplicate
        has_dup = calendar_service.has_duplicate_event(
            user_id=user_id,
            chat_id=chat_id,
            title="team meeting",
            event_date=event_date,
        )
        assert has_dup is True

    def test_duplicate_detection_whitespace_trimmed(self, calendar_service):
        """Test that duplicate detection trims whitespace."""
        user_id = "U123456"
        chat_id = "group_G123"
        event_date = date.today() + timedelta(days=7)

        # Add event with title
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title="Team Meeting",
            event_date=event_date,
        )
        assert event1 is not None

        # Check version with extra spaces is detected as duplicate
        has_dup = calendar_service.has_duplicate_event(
            user_id=user_id,
            chat_id=chat_id,
            title="  Team Meeting  ",
            event_date=event_date,
        )
        assert has_dup is True

    def test_no_duplicate_different_date(self, calendar_service):
        """Test that same title on different date is NOT a duplicate."""
        user_id = "U123456"
        chat_id = "group_G123"
        title = "Team Meeting"
        date1 = date.today() + timedelta(days=7)
        date2 = date.today() + timedelta(days=14)

        # Add event on date1
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=date1,
        )
        assert event1 is not None

        # Check same title on different date is NOT duplicate
        has_dup = calendar_service.has_duplicate_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=date2,
        )
        assert has_dup is False

        # Should be able to add event on different date
        event2 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=date2,
        )
        assert event2 is not None

    def test_no_duplicate_different_user(self, calendar_service):
        """Test that same event for different user is NOT a duplicate."""
        user_id1 = "U111111"
        user_id2 = "U222222"
        chat_id = "group_G123"
        title = "Team Meeting"
        event_date = date.today() + timedelta(days=7)

        # Add event for user1
        event1 = calendar_service.add_event(
            user_id=user_id1,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
        )
        assert event1 is not None

        # Check same event for user2 is NOT duplicate
        has_dup = calendar_service.has_duplicate_event(
            user_id=user_id2,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
        )
        assert has_dup is False

        # Should be able to add event for user2
        event2 = calendar_service.add_event(
            user_id=user_id2,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
        )
        assert event2 is not None

    def test_no_duplicate_different_chat(self, calendar_service):
        """Test that same event in different chat is NOT a duplicate."""
        user_id = "U123456"
        chat_id1 = "group_G111"
        chat_id2 = "group_G222"
        title = "Team Meeting"
        event_date = date.today() + timedelta(days=7)

        # Add event in chat1
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id1,
            title=title,
            event_date=event_date,
        )
        assert event1 is not None

        # Check same event in chat2 is NOT duplicate
        has_dup = calendar_service.has_duplicate_event(
            user_id=user_id,
            chat_id=chat_id2,
            title=title,
            event_date=event_date,
        )
        assert has_dup is False

        # Should be able to add event in chat2
        event2 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id2,
            title=title,
            event_date=event_date,
        )
        assert event2 is not None

    def test_skip_duplicate_check_flag(self, calendar_service):
        """Test that skip_duplicate_check flag bypasses duplicate detection."""
        user_id = "U123456"
        chat_id = "group_G123"
        title = "Team Meeting"
        event_date = date.today() + timedelta(days=7)

        # Add first event
        event1 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
        )
        assert event1 is not None

        # Add duplicate with skip flag (should succeed despite duplicate)
        event2 = calendar_service.add_event(
            user_id=user_id,
            chat_id=chat_id,
            title=title,
            event_date=event_date,
            skip_duplicate_check=True,
        )
        assert event2 is not None
        assert event2.event_id != event1.event_id

        # Now we have 2 events with same title/date
        events = calendar_service.get_chat_events(chat_id)
        assert len(events) == 2
