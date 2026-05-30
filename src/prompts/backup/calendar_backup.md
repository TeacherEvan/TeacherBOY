# Zeus Calendar Backup

**Generated:** 2026-05-30T10:32:59.691053+00:00
**Event Count:** 1

## Events

```json
[
  {
    "id": "5f605070-cd56-43ad-b02d-4544e27898e9",
    "user_id": "test_user_deletion_123",
    "chat_id": "user_test_user_deletion_123",
    "title": "User 1 Event",
    "date": "2026-01-12",
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
