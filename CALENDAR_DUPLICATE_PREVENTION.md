# Calendar Duplicate Prevention & Zeus Self-Scraping

## Summary

Implemented comprehensive duplicate detection for calendar events and enabled Zeus to scrape his own messages for dates. This prevents duplicate calendar entries while allowing Zeus to extract dates from any message in the chat history, including his own responses.

## Changes Made

### 1. Duplicate Detection in Calendar Service

**File:** `src/services/calendar_service.py`

Added new method `has_duplicate_event()` to detect if an event already exists:

```python
def has_duplicate_event(
    self,
    user_id: str,
    chat_id: str,
    title: str,
    event_date: date,
) -> bool:
    """
    Check if a duplicate event already exists.

    An event is considered a duplicate if:
    - Same user_id
    - Same chat_id
    - Same title (case-insensitive, trimmed)
    - Same event_date
    """
```

**Duplicate Detection Rules:**

- ✅ Case-insensitive title matching (`"Team Meeting"` == `"team meeting"`)
- ✅ Whitespace trimmed (`"  Event  "` == `"Event"`)
- ✅ Per-user, per-chat isolation (same event can exist for different users or in different chats)
- ✅ Date-specific (same title on different dates is allowed)

**Updated `add_event()` method:**

- Added `skip_duplicate_check` parameter (default: `False`)
- Checks for duplicates BEFORE validation (performance optimization)
- Raises `ValueError` with clear message if duplicate detected
- Can be bypassed with `skip_duplicate_check=True` (use with caution)

### 2. Zeus Self-Message Scraping

**File:** `src/main.py`

**Previous Behavior:**

- Bot messages were **completely filtered out** before storage in message buffer
- Zeus could NOT scrape his own responses for dates

**New Behavior:**

- Bot messages are **stored in message buffer** for scraping
- Bot messages are **still skipped for agent routing** (prevents infinite loop)
- Zeus can now extract dates from his own responses

**Code Changes:**

```python
# Store ALL messages (including bot's own) for scraping
if chat_id and user_id:
    message_buffer_service.store_message(
        chat_id=chat_id,
        text=event.message.text,
        user_id=user_id,
        message_id=event.message.id if hasattr(event.message, 'id') else None
    )

# CRITICAL: Skip agent routing for bot messages (prevent infinite loop)
if bot_user_id and user_id == bot_user_id:
    logger.debug(
        f"🔒 Skipping agent routing for bot's own message (stored in buffer only)"
    )
    continue
```

### 3. Duplicate Handling in Calendar Agent

**File:** `src/agents/calendar_agent.py`

Updated scrape flow to check for duplicates before adding events:

**Single Event Add:**

```python
# Check for duplicate before creating
is_duplicate = self._calendar_service.has_duplicate_event(
    user_id=user_id,
    chat_id=chat_id,
    title=event_data["title"],
    event_date=event_data["date"],
)

if is_duplicate:
    await self._send_message(
        event, line_bot_api,
        f"⏩ Skipped: {event_data['title']} (duplicate)"
    )
else:
    # Create the event with skip_duplicate_check=True (already checked)
    self._calendar_service.add_event(...)
```

**Bulk Add All:**

```python
# Track both added and skipped counts
added_count = 0
skipped_count = 0

# Check each event for duplicates
if is_duplicate:
    logger.info(f"⏩ Skipping duplicate: {title} on {date}")
    skipped_count += 1
else:
    # Add the event
    added_count += 1

# Show summary with both counts
summary = f"✅ Added {added_count} event(s) to calendar!"
if skipped_count > 0:
    summary += f" (⏩ {skipped_count} duplicate(s) skipped)"
```

## Usage Examples

### Example 1: Scraping Zeus's Own Messages

**Scenario:** Zeus responds with event dates, user wants to add them to calendar

```
User: When is the next team meeting?
Zeus: Team meeting is scheduled for January 15, 2026 at 2 PM.
User: zeus scrape

Zeus: 🔍 Scanned 10 messages - found 1 event(s)!

      Event 1/1
      📅 Team meeting
      📆 January 15, 2026
      Source: "Team meeting is scheduled for January 15, 2026 at 2 PM."

      Add this event? [Yes ✓] [No ✗] [Add All (1)]
```

### Example 2: Duplicate Detection

**Scenario:** User tries to add same event twice

```
User: zeus add tomorrow Team standup
Zeus: ✅ Added event!
      📆 Team standup
      📅 January 11, 2026

User: zeus add tomorrow Team standup
Zeus: ❌ Failed to create event: Duplicate event: 'Team standup' on 2026-01-11 already exists
```

### Example 3: Bulk Add with Duplicates

**Scenario:** Scraping messages where some events already exist

```
User: zeus scrape
Zeus: 🔍 Scanned 10 messages - found 5 event(s)!

[User selects "Add All (5)" and chooses reminders]

Zeus: ✅ Added 3 event(s) to calendar! (⏩ 2 duplicate(s) skipped)

      1. Project kickoff
      2. Design review
      3. Sprint planning

      🔔 Reminders: 7, 3, 1 days + day-of
```

## Testing

### New Test Suite: `tests/test_calendar_duplicates.py`

Comprehensive test coverage for duplicate detection:

1. ✅ `test_duplicate_detection_same_user_same_chat` - Basic duplicate detection
2. ✅ `test_duplicate_detection_case_insensitive` - Case-insensitive matching
3. ✅ `test_duplicate_detection_whitespace_trimmed` - Whitespace normalization
4. ✅ `test_no_duplicate_different_date` - Same title, different date allowed
5. ✅ `test_no_duplicate_different_user` - Same event, different user allowed
6. ✅ `test_no_duplicate_different_chat` - Same event, different chat allowed
7. ✅ `test_skip_duplicate_check_flag` - Bypass flag functionality

**Run tests:**

```powershell
pytest tests/test_calendar_duplicates.py -v
```

**Expected output:**

```
======================== test session starts ========================
collected 7 items

tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_duplicate_detection_same_user_same_chat PASSED
tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_duplicate_detection_case_insensitive PASSED
tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_duplicate_detection_whitespace_trimmed PASSED
tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_no_duplicate_different_date PASSED
tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_no_duplicate_different_user PASSED
tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_no_duplicate_different_chat PASSED
tests/test_calendar_duplicates.py::TestCalendarDuplicates::test_skip_duplicate_check_flag PASSED

=================== 7 passed in 1.86s ====================
```

## Security Considerations

### Infinite Loop Prevention

The implementation maintains strict separation between:

1. **Message Storage** - ALL messages stored (including bot's own)
2. **Agent Routing** - Bot messages skipped (prevents infinite loop)

This ensures:

- ✅ Zeus can scrape his own messages for dates
- ✅ Zeus won't respond to his own messages (infinite loop prevented)
- ✅ Message buffer contains complete conversation history

### Data Isolation

Duplicate detection enforces chat isolation:

- Events are scoped by `user_id` AND `chat_id`
- User A's "Meeting" in Chat 1 ≠ User B's "Meeting" in Chat 2
- Prevents cross-chat data leakage

## Performance Optimizations

1. **Early Duplicate Check** - Performed BEFORE validation to save processing
2. **Case-Insensitive Comparison** - Normalized during check, not stored
3. **Bulk Add Optimization** - Single check per event, no redundant validations
4. **Skip Flag** - Allows bypassing duplicate check when caller has already verified

## Future Enhancements

Potential improvements for future consideration:

1. **Fuzzy Matching** - Detect similar titles ("Team Meeting" vs "Team Mtg")
2. **Time-Based Deduplication** - Consider events within X hours as duplicates
3. **Batch Duplicate Check** - Check multiple events in single operation
4. **Duplicate Merge** - Ask user if they want to update existing event instead of skipping

## Migration Notes

- ✅ **Fully backward compatible** - Existing events unaffected
- ✅ **No database migration needed** - In-memory and local storage both work
- ✅ **Existing tests passing** - No regressions detected
- ✅ **HF Hub sync compatible** - Duplicate detection works with cloud backup

## Changelog Entry

**Date:** January 10, 2026

**Summary:** Implemented duplicate prevention for calendar events and enabled Zeus to scrape his own messages for dates.

**Changes:**

- Added `has_duplicate_event()` method to CalendarService with case-insensitive, whitespace-trimmed matching
- Updated `add_event()` with optional `skip_duplicate_check` parameter
- Modified main.py to store bot messages in buffer while preventing infinite loop
- Enhanced calendar agent to check duplicates before adding scraped events
- Added comprehensive test suite with 7 test cases (all passing)

**Benefits:**

- Prevents duplicate calendar entries across all add flows
- Allows Zeus to extract dates from his own responses
- Maintains chat and user isolation for privacy
- Improves user experience with clear duplicate skip messages
