# Google Calendar Integration Guide

TeacherBOY now supports **Google Calendar** as the backend for calendar events and reminders. This provides:

- ✅ **Native mobile reminders** - Get notifications on your phone
- ✅ **Cross-device sync** - Access events from any device
- ✅ **Natural language parsing** - "Meeting tomorrow at 3pm"
- ✅ **Calendar sharing** - Share with family/team
- ✅ **Google Assistant integration** - Voice commands

## Quick Setup

### 1. Create Google Cloud Credentials

1. Go to [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
2. Create a new project (or select existing)
3. Enable the **Google Calendar API**:
   - Go to "APIs & Services" → "Enable APIs and Services"
   - Search for "Google Calendar API" and enable it
4. Create OAuth 2.0 credentials:
   - Go to "Credentials" → "Create Credentials" → "OAuth client ID"
   - Application type: **Desktop app**
   - Name: "TeacherBOY Calendar"
   - Download the JSON file

### 2. Save Credentials

Save the downloaded JSON as:
```
data/google_credentials.json
```

### 3. Run Authorization

```bash
python scripts/setup_google_calendar.py
```

This opens a browser for Google account authorization. After authorizing:
- A token is saved to `data/google_token.json`
- You only need to do this once (token auto-refreshes)

### 4. Enable Google Calendar

Add to your `.env` file:

```env
GOOGLE_CALENDAR_ENABLED=true
```

### 5. Restart TeacherBOY

```bash
# Docker
docker-compose restart

# Local
uvicorn src.main:app --reload
```

## Configuration Options

| Variable | Default | Description |
|----------|---------|-------------|
| `GOOGLE_CALENDAR_ENABLED` | `false` | Enable Google Calendar integration |
| `GOOGLE_CALENDAR_CREDENTIALS_FILE` | `data/google_credentials.json` | Path to OAuth credentials |
| `GOOGLE_CALENDAR_TOKEN_FILE` | `data/google_token.json` | Path for authorization token |
| `GOOGLE_CALENDAR_ID` | `primary` | Calendar ID (use 'primary' for main calendar) |

## Usage

### Same Commands, Better Backend

All existing calendar commands work the same:

| Command | Description |
|---------|-------------|
| `zeus calendar` | View upcoming events |
| `zeus add event` | Start add flow |
| `zeus add tomorrow Team meeting` | Quick inline add |
| `zeus scrape` | AI-extract dates from chat |
| `zeus remove event` | Remove events |

### New: Natural Language Events

With Google Calendar, you can use more natural language:

```
zeus add Meeting with John tomorrow at 2pm
zeus add Dentist appointment next Tuesday 10am
zeus add Mom's birthday party on Jan 15 at 6pm
```

### Native Reminders

When you add an event, reminders are set automatically in Google Calendar:
- 1 day before
- 1 hour before

You can customize reminders in Google Calendar's web/mobile app.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    CalendarAgent                      │
│  (same interface, same commands)                      │
└────────────────────────┬─────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────┐
│                  CalendarAdapter                      │
│  (routes to appropriate backend)                      │
└────────────────────────┬─────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
┌─────────────────────┐       ┌─────────────────────┐
│  Local JSON         │       │  Google Calendar    │
│  (default)          │       │  (if enabled)       │
│                     │       │                     │
│  data/calendar/     │       │  calendar.google.   │
│  calendar_events.   │       │  com/calendar       │
│  json               │       │                     │
└─────────────────────┘       └─────────────────────┘
```

## Fallback Behavior

If Google Calendar fails to initialize (missing credentials, network error), TeacherBOY automatically falls back to local JSON storage. Check logs for:

```
✅ Calendar adapter initialized with Google Calendar backend
```
or
```
📁 Calendar adapter initialized with local storage backend
```

## Troubleshooting

### "Google Calendar libraries not installed"

```bash
pip install google-api-python-client google-auth-oauthlib
```

### "Credentials file not found"

Download OAuth credentials from Google Cloud Console and save to `data/google_credentials.json`.

### "Authorization failed"

1. Ensure you enabled "Google Calendar API" in Google Cloud Console
2. Make sure the OAuth consent screen is configured
3. Try deleting `data/google_token.json` and re-running setup

### "Events not syncing"

1. Check that `GOOGLE_CALENDAR_ENABLED=true` is set
2. Verify the token hasn't expired (run setup script again if needed)
3. Check Google Calendar's web interface directly

## Migration from Local Storage

If you have existing events in local JSON storage:

1. View your current events: `zeus calendar`
2. Note down important events
3. Enable Google Calendar
4. Re-add events (they'll sync to Google)

> **Note:** Automatic migration from local JSON to Google Calendar is not implemented. This ensures you don't accidentally duplicate events.

## Security

- OAuth tokens are stored locally in `data/google_token.json`
- Tokens are automatically refreshed when expired
- No passwords or API keys are stored
- You can revoke access anytime at [Google Account Permissions](https://myaccount.google.com/permissions)

## Files Created

| File | Purpose |
|------|---------|
| `src/services/google_calendar_service.py` | Google Calendar API integration |
| `src/services/calendar_adapter.py` | Unified adapter for both backends |
| `scripts/setup_google_calendar.py` | OAuth setup script |
| `data/google_credentials.json` | OAuth client credentials (you provide) |
| `data/google_token.json` | Authorization token (generated) |
