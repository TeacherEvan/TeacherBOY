# Calendar and Reminders Feature

Ms. Green now includes a comprehensive calendar and reminder system that allows users to:

- Add events with automatic reminders
- View their upcoming events
- Remove events (with multi-select support)
- Extract dates from images and add them to the calendar

## Quick Start

### View Your Calendar

```text
Ms. Green calendar
my events
my reminders
```

### Add an Event

```text
Ms. Green add event
Ms. Green remind me
```

### Remove Events

```text
Ms. Green remove event
Ms. Green delete event
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

Ms. Green intelligently delivers reminders based on your relationship:

| Scenario             | Delivery Method       |
| -------------------- | --------------------- |
| LINE Friend (DM)     | Direct message to you |
| LINE Friend (Group)  | Direct message to you |
| Not a Friend (Group) | Reminder in the group |

**Tip**: Add Ms. Green as a friend to receive private reminders!

### 4. Image Date Extraction

When using `Ms. Green analyze this` with an image containing dates (schedules, announcements, etc.), Ms. Green will:

1. Detect dates in the image
2. Show you what was found
3. Ask if you want to add them to your calendar
4. Guide you through the add process
5. Let you add the remaining extracted events in one step after you confirm the reminder schedule

Example images that work well:

- School announcements
- Event flyers
- Schedules and timetables
- Meeting agendas with dates

When multiple dates are detected, you can review them one by one or use the
bulk-add option to save the remaining events with the same reminder selection.

## Commands Reference

### View Commands

| Command                 | Description               |
| ----------------------- | ------------------------- |
| `Ms. Green calendar`    | View your upcoming events |
| `my events`             | Same as above             |
| `my reminders`          | Same as above             |
| `Ms. Green my calendar` | Same as above             |

Calendar visibility is chat-scoped: events created in a group stay in that
group, and events created in a direct message stay private to that direct
message.

### Add Commands

| Command                  | Description              |
| ------------------------ | ------------------------ |
| `Ms. Green add event`    | Start adding a new event |
| `Ms. Green remind me`    | Same as above            |
| `Ms. Green calendar add` | Same as above            |

### Remove Commands

| Command                     | Description             |
| --------------------------- | ----------------------- |
| `Ms. Green remove event`    | Select events to remove |
| `Ms. Green delete event`    | Same as above           |
| `Ms. Green calendar remove` | Same as above           |

## Add Event Flow

1. **Trigger**: Send `Ms. Green add event`
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

1. **Trigger**: Send `Ms. Green remove event`
2. **Select**: Choose events by number (multi-select: `1,3,5`)
3. **Confirm**: Confirm deletion

**Note**: You can only view and remove your own events.

## Configuration

## Persistence Backends

Calendar persistence now supports two operator-selected modes:

- `PERSISTENCE_BACKEND=local`: keep the existing local JSON plus optional HF backup path.
- `PERSISTENCE_BACKEND=convex`: make Convex the primary structured backend for calendar events and reminder state.

When Convex is primary, the local calendar directory remains available as a cache and rollback path. To roll back, set `PERSISTENCE_BACKEND=local` and restart the app.

### Environment Variables

```bash
# Primary structured persistence backend
PERSISTENCE_BACKEND=local

# Enable/disable calendar feature
CALENDAR_ENABLED=true

# Hour to send daily reminders (24-hour format, Bangkok timezone)
CALENDAR_REMINDER_HOUR=8

# Local storage path for calendar data
CALENDAR_DATA_PATH=./data/calendar

# Convex primary backend (required when PERSISTENCE_BACKEND=convex)
CONVEX_DEPLOYMENT_URL=
CONVEX_SYNC_TOKEN=
CONVEX_REQUEST_TIMEOUT_SECONDS=10

# Optional: Hugging Face Hub backup
CALENDAR_HF_REPO_ID=username/ms-green-calendar

# Sync interval for HF Hub (seconds)
CALENDAR_SYNC_INTERVAL_SECONDS=300
```

### Persistence Notes

- `CALENDAR_DATA_PATH` controls the local filesystem path for calendar data.
- `CALENDAR_HF_REPO_ID` remains the separate optional HF dataset for calendar backup.
- For the shared storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).

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

With `PERSISTENCE_BACKEND=convex`, `CalendarService` routes calendar CRUD and reminder state through the Convex repository adapter. With `PERSISTENCE_BACKEND=local`, it keeps the existing local/HF-backed behavior.

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

- **Chat Isolation**: Event visibility is scoped to the current chat.
    Group events stay in that group, and direct-message events stay private.
- **Flow Ownership**: Only the user who started a flow can continue interactive calendar prompts.
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
User: Ms. Green add event
Ms. Green: What is the title?
User: Team standup
Ms. Green: What date?
User: next Monday
Ms. Green: Description? (or "skip")
User: skip
Ms. Green: Select reminders: [1, 3]
User: 1,3
Ms. Green: Confirm? [Shows summary]
User: yes
Ms. Green: ✅ Event added with reminders!
```

### Removing Events

```text
User: Ms. Green remove event
Ms. Green: Your events:
      1. Team standup - Jun 16
      2. Doctor visit - Jun 20
      Select numbers to remove:
User: 2
Ms. Green: Remove "Doctor visit"?
User: yes
Ms. Green: ✅ Removed 1 event
```

### Image Date Extraction

```text
User: Ms. Green analyze this [sends school schedule image]
Ms. Green: [Analysis response]
      📅 I detected 3 dates:
      1. 2025-06-09: Final Grades Due
      2. 2025-07-03: New Enrollment
      3. 2025-08-15: School Opens
      Add to calendar?
User: yes
Ms. Green: [Starts add flow for each date]
```

## Related Documentation

- [Admin Commands](ADMIN_COMMANDS.md) - Admin features
- [Conversation Memory](CONVERSATION_MEMORY.md) - HF Hub persistence
- [Profiler Usage](PROFILER_USAGE.md) - Image analysis features
