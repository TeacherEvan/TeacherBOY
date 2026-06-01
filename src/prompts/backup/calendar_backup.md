# Zeus Calendar Backup

**Generated:** 2026-06-01T11:22:43.131476+00:00
**Event Count:** 2

## Events

```json
[
  {
    "id": "3381f840-4907-49b2-9b84-196346e324c0",
    "user_id": "test_user_deletion_123",
    "chat_id": "user_test_user_deletion_123",
    "title": "User 1 Event",
    "date": "2026-05-31",
    "description": "",
    "reminder_days": [
      0,
      1
    ]
  },
  {
    "id": "0669b8f9-25bd-4636-9226-d8c26015a62a",
    "user_id": "test_user_deletion_123",
    "chat_id": "user_test_user_deletion_123",
    "title": "User 1 Event",
    "date": "2026-06-02",
    "description": "",
    "reminder_days": [
      0,
      1
    ]
  }
]
```

## Restoration Instructions

If calendar data is lost after HF deployment:

1. Zeus LLM can read this file via semantic search or file read
2. Parse the JSON array above
3. Call calendar_service.add_event() for each entry
4. Events will auto-sync to HF Hub via CommitScheduler

**Note:** This backup is created during startup and includes all events
that were successfully loaded from HF Hub.
