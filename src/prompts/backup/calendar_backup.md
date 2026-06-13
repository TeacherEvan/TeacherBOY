# Zeus Calendar Backup

**Generated:** 2026-06-13T07:32:59.779510+00:00
**Event Count:** 5

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
  },
  {
    "id": "91dc74a7-6b25-4015-afd6-0543e71842d8",
    "user_id": "test_user_deletion_123",
    "chat_id": "user_test_user_deletion_123",
    "title": "User 1 Event",
    "date": "2026-06-04",
    "description": "",
    "reminder_days": [
      0,
      1
    ]
  },
  {
    "id": "95adfd97-1e1d-47dc-aeb2-59ea8007792c",
    "user_id": "U5390303cc145d53483ee15b4ec61d8f0",
    "chat_id": "group_Caf46e5b4b72b2605d38d23576db03407",
    "title": "22/06/2026",
    "date": "2026-06-22",
    "description": "",
    "reminder_days": [
      0,
      3
    ]
  },
  {
    "id": "f1c91913-ff11-4c0e-8cf0-cb4fef29e2fb",
    "user_id": "U5390303cc145d53483ee15b4ec61d8f0",
    "chat_id": "group_Caf46e5b4b72b2605d38d23576db03407",
    "title": "Event",
    "date": "2026-06-22",
    "description": "",
    "reminder_days": [
      0,
      3
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
