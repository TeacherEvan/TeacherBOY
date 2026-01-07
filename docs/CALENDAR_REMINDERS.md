# Calendar and Reminders Feature

Zeus now includes a comprehensive calendar and reminder system that allows users to:

- Add events with automatic reminders
- View their upcoming events
- Remove events (with multi-select support)
- Extract dates from images and add them to the calendar

## Quick Start

### View Your Calendar

```text
Zeus calendar
my events
my reminders
```

### Add an Event

```text
Zeus add event
Zeus remind me
```

### Remove Events

```text
Zeus remove event
Zeus delete event
```

## Features

### 1. Event Management

Every calendar event includes:

- **Title**: Brief description of the event
- **Date**: When the event occurs
- **Description**: Optional details
- **Reminders**: Automatic notifications before the event

### 2. Automatic Reminders

All events come with reminders. When adding an event, you choose from:

- **7 days before** (📅 One week notice)
- **3 days before** (⏰ Few days notice)
- **1 day before** (⚠️ Tomorrow)
- **Day of event** (🚨 Today - always included)

**Important**: The day-of reminder (0) is mandatory and always included.

### 3. Smart Notification Delivery

Zeus intelligently delivers reminders based on your relationship:

| Scenario             | Delivery Method       |
| -------------------- | --------------------- |
| LINE Friend (DM)     | Direct message to you |
| LINE Friend (Group)  | Direct message to you |
| Not a Friend (Group) | Reminder in the group |

**Tip**: Add Zeus as a friend to receive private reminders!

### 4. Image Date Extraction

When using "Zeus analyze this" with an image containing dates (schedules, announcements, etc.), Zeus will:

1. Detect dates in the image
2. Show you what was found
3. Ask if you want to add them to your calendar
4. Guide you through the add process

Example images that work well:

- School announcements
- Event flyers
- Schedules and timetables
- Meeting agendas with dates

## Commands Reference

### View Commands

| Command            | Description               |
| ------------------ | ------------------------- |
| `Zeus calendar`    | View your upcoming events |
| `my events`        | Same as above             |
| `my reminders`     | Same as above             |
| `Zeus my calendar` | Same as above             |

### Add Commands

| Command             | Description              |
| ------------------- | ------------------------ |
| `Zeus add event`    | Start adding a new event |
| `Zeus remind me`    | Same as above            |
| `Zeus calendar add` | Same as above            |

### Remove Commands

| Command                | Description             |
| ---------------------- | ----------------------- |
| `Zeus remove event`    | Select events to remove |
| `Zeus delete event`    | Same as above           |
| `Zeus calendar remove` | Same as above           |

## Add Event Flow

1. **Trigger**: Send "Zeus add event"
2. **Title**: Enter the event title
3. **Date**: Enter the date (various formats supported)
4. **Description**: Add optional details (or skip)
5. **Reminders**: Select reminder days
6. **Confirm**: Review and confirm

### Supported Date Formats

- ISO: `2025-06-15`
- Natural: `June 15, 2025` or `Jun 15`
- Relative: `next Monday`, `in 3 days`
- Thai style: `15/06/2025` (day/month/year)

## Remove Event Flow

1. **Trigger**: Send "Zeus remove event"
2. **Select**: Choose events by number (multi-select: `1,3,5`)
3. **Confirm**: Confirm deletion

**Note**: You can only view and remove your own events.

## Configuration

### Environment Variables

```bash
# Enable/disable calendar feature
CALENDAR_ENABLED=true

# Hour to send daily reminders (24-hour format, Bangkok timezone)
CALENDAR_REMINDER_HOUR=8

# Local storage path for calendar data
CALENDAR_DATA_PATH=./data/calendar

# Optional: Hugging Face Hub backup
CALENDAR_HF_REPO_ID=username/zeus-calendar

# Sync interval for HF Hub (seconds)
CALENDAR_SYNC_INTERVAL_SECONDS=300
```

### HF Hub Persistence

To enable cloud backup of calendar data:

1. Set `HF_MEMORY_TOKEN` (same token as conversation memory)
2. Set `CALENDAR_HF_REPO_ID` to your dataset repo

The calendar data syncs automatically every 5 minutes (configurable).

## Technical Details

### Architecture

```text
CalendarAgent (Priority: 6)
    ↓
CalendarSessionManager (State Machine)
    ↓
CalendarService (CRUD + Persistence)
    ↓
ReminderService (APScheduler + LINE Push)
```

### Components

| Component                     | Purpose                               |
| ----------------------------- | ------------------------------------- |
| `calendar_agent.py`           | Handles triggers and multi-step flows |
| `calendar_service.py`         | CRUD operations, HF Hub sync          |
| `calendar_session_manager.py` | State machine for flows               |
| `reminder_service.py`         | Scheduled notifications               |

### Data Model

```python
@dataclass
class CalendarEvent:
    event_id: str           # UUID
    user_id: str            # LINE user ID
    title: str              # Event title
    event_date: date        # When it happens
    description: str        # Optional details
    reminder_days: List[int]  # [7, 3, 1, 0]
    notified_dates: List[str] # Already sent (date strings)
    created_at: datetime    # When added
    chat_id: str            # For group reminders
```

### State Machine States

```python
class CalendarState(Enum):
    IDLE = "idle"
    VIEWING_EVENTS = "viewing"
    ADDING_TITLE = "adding_title"
    ADDING_DATE = "adding_date"
    ADDING_DESCRIPTION = "adding_description"
    SELECTING_REMINDERS = "selecting_reminders"
    CONFIRMING_ADD = "confirming_add"
    SELECTING_REMOVE = "selecting_remove"
    CONFIRMING_REMOVE = "confirming_remove"
    PROCESSING_EXTRACTED_DATES = "processing_extracted"
```

## Privacy and Security

- **User Isolation**: Users can only view/remove their own events
- **Session Ownership**: Only the user who started a flow can interact
- **Data Location**: Stored locally by default; HF Hub is optional
- **No Image Storage**: Images analyzed for dates are not saved

## Troubleshooting

### Reminders Not Sending

1. Check `CALENDAR_ENABLED=true`
2. Verify `CALENDAR_REMINDER_HOUR` is set correctly
3. Check LINE bot has correct access token
4. Review logs for scheduler errors

### Date Parsing Fails

1. Try ISO format: `YYYY-MM-DD`
2. Use English month names: `June 15, 2025`
3. Avoid ambiguous formats like `01/02/2025`

### Session Expires

Calendar sessions have a 2-minute timeout. If you get "session expired":

1. Start the flow again
2. Respond more quickly to prompts

## Examples

### Adding a Meeting

```text
User: Zeus add event
Zeus: What is the title?
User: Team standup
Zeus: What date?
User: next Monday
Zeus: Description? (or "skip")
User: skip
Zeus: Select reminders: [1, 3]
User: 1,3
Zeus: Confirm? [Shows summary]
User: yes
Zeus: ✅ Event added with reminders!
```

### Removing Events

```text
User: Zeus remove event
Zeus: Your events:
      1. Team standup - Jun 16
      2. Doctor visit - Jun 20
      Select numbers to remove:
User: 2
Zeus: Remove "Doctor visit"?
User: yes
Zeus: ✅ Removed 1 event
```

### Image Date Extraction

```text
User: Zeus analyze this [sends school schedule image]
Zeus: [Analysis response]
      📅 I detected 3 dates:
      1. 2025-06-09: Final Grades Due
      2. 2025-07-03: New Enrollment
      3. 2025-08-15: School Opens
      Add to calendar?
User: yes
Zeus: [Starts add flow for each date]
```

## Related Documentation

- [Admin Commands](ADMIN_COMMANDS.md) - Admin features
- [Conversation Memory](CONVERSATION_MEMORY.md) - HF Hub persistence
- [Profiler Usage](PROFILER_USAGE.md) - Image analysis features
