# Environment variables

The bot reads configuration from `.env` (local) and environment variables (production).

Start from `.env.example`.

## Required

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

## Recommended

- `GEMINI_API_KEY` or `GOOGLE_API_KEY` (primary AI provider - free tier)
- `OPENROUTER_API_KEY` (fallback AI provider)

## Admin

- `ADMIN_USER_IDS` (comma-separated)
- `ADMIN_SETUP_KEY` (temporary bootstrap)

## Named Users (Outbound Messaging)

Configure named recipients the admin can message via `/admin send` and `/admin llm_send`.

- `USER_<ALIAS>=<LINE_USER_ID>`

Example:

```env
USER_BOSS=U1234567890abcdef
USER_ALICE=Uabcdef0123456789
```

Notes:

- Aliases are case-insensitive (stored as lowercase).
- Recipients are **whitelisted** by env var only (prevents pushing to arbitrary IDs).

## Moderators

- `MODERATOR_USER_IDS` (comma-separated)

## Tracing

- `ENABLE_TRACING` (default: `False`)
- `OTEL_SERVICE_NAME` (default: `Ms. Green`)
- `OTEL_EXPORTER_OTLP_ENDPOINT` (default: `http://localhost:4318`)

## Server

- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)
- `DEBUG` (default: `False`)

## Structured Persistence (Convex)

- `PERSISTENCE_BACKEND`
	- `local` keeps the existing local/HF-backed runtime path.
	- `convex` makes Convex the primary structured persistence backend.
- `CONVEX_DEPLOYMENT_URL`
- `CONVEX_SYNC_TOKEN`
- `CONVEX_REQUEST_TIMEOUT_SECONDS` (default: `10`)
- `CONVEX_REQUIRE_HEALTHCHECK_ON_STARTUP` (default: `False`)

When `PERSISTENCE_BACKEND=convex`, the runtime routes structured calendar data and review-agent staff memory through Convex. The admin-only config window is not implemented yet, but Convex `appSettings` is now the persistence target prepared for that future work.

Rollback path:

- Set `PERSISTENCE_BACKEND=local`
- Restart the app

This returns the bot to the existing local/HF-backed path without deleting local files.

## AI Translation

- Translation uses the shared AI translation service.
- Configure at least one provider:
  - `GEMINI_API_KEY` or `GOOGLE_API_KEY` (primary via fallback chain)
  - `OPENROUTER_API_KEY` (fallback)

## LLM (Provider Fallback Chain)

- `GEMINI_API_KEY` / `GOOGLE_API_KEY` (primary - free tier, recommended)
- `OPENROUTER_API_KEY` (fallback)
- `OPENROUTER_DEFAULT_MODEL` (default: `nvidia/nemotron-3-ultra-550b-a55b:free`)
- `DEFAULT_MODEL` (alias of `OPENROUTER_DEFAULT_MODEL`, useful on Hugging Face Spaces)
- `LLM_PROVIDER_PRIORITY` (default: `gemini` only; other providers only as fallback)
- `LLM_SYSTEM_PROMPT` (optional; controls bot personality/tone)

## Web Search (Brave)

- `BRAVE_SEARCH_API_KEY`

## News (optional)

- `EXCHANGE_RATE_API_KEY` (ExchangeRate-API)
- `TAT_API_KEY` (Tourism Authority of Thailand events)

## Conversation Memory

- `CONVERSATION_MEMORY_ENABLED`
- `CONVERSATION_MAX_MESSAGES`
- `CONVERSATION_TTL_HOURS`
- `CONVERSATION_STORAGE_PATH`
- `HF_MEMORY_TOKEN`
- `HF_MEMORY_REPO_ID`

## Bot Identity

- `BOT_IDENTITY_STORAGE_PATH`

## Document Memory

- `DOCUMENT_MEMORY_ENABLED`
- `DOCUMENT_STORAGE_PATH`
- `DOCUMENT_MAX_FILE_SIZE_MB`
- `DOCUMENT_MAX_TEXT_CHARS`
- `DOCUMENT_HF_REPO_ID`

## History Logging

- `HISTORY_LOG_ENABLED`
- `HISTORY_LOG_PATH`
- `HISTORY_LOG_ROTATION_DAYS`
- `HISTORY_LOG_ENCRYPTION_KEY`
- `HISTORY_LOG_HF_REPO_ID`

## Staff Memory

- `STAFF_MEMORY_STORAGE_PATH`

## Profiler

- `PROFILER_ENABLED`
- `PROFILER_MODEL`
- `PROFILER_ANALYSIS_TYPE`
- `PROFILER_ANALYSIS_DEPTH`
- `PROFILER_RATE_LIMIT_PER_HOUR`
- `PROFILER_MAX_IMAGE_SIZE_MB`

## Productivity

- `USE_OPTIMIZED_PROMPTS`
- `ENABLE_CONVERSATION_SUMMARIZATION`
- `CONVERSATION_SUMMARY_INTERVAL`
- `CONVERSATION_MESSAGES_TO_KEEP_FULL`

## Harmful Content Detection (Moderator Mode)

### `HARMFUL_CONTENT_KEYWORDS`

- **Type:** String (comma-separated)
- **Default:** `None`
- **Description:** Comma-separated list of custom harmful keywords. Overrides/adds to built-in English/Thai keyword lists.
- **Example:** `HARMFUL_CONTENT_KEYWORDS=spam,scam,phishing,customterm`

### `HARMFUL_CONTENT_KEYWORDS_FILE`

- **Type:** String (path)
- **Default:** `None`
- **Description:** Path to JSON file containing custom harmful keywords. Supports array format `["keyword1", "keyword2"]` or object format `{"keywords": ["keyword1", "keyword2"]}`.
- **Example:** `HARMFUL_CONTENT_KEYWORDS_FILE=./config/harmful_keywords.json`

## HTTP Client

- `HTTP_CLIENT_TIMEOUT_SECONDS`
- `HTTP_CLIENT_MAX_CONNECTIONS`
- `HTTP_CLIENT_MAX_KEEPALIVE`

## MCP

- `MCP_SERVER_URL`

## Cache TTLs (seconds)

- `WEATHER_CACHE_TTL_SECONDS`
- `NEWS_CACHE_TTL_SECONDS`
- `HOLIDAY_CACHE_TTL_SECONDS`
- `BITCOIN_CACHE_TTL_SECONDS`
- `EXCHANGE_CACHE_TTL_SECONDS`
- `COLOR_CACHE_TTL_SECONDS`
- `SUNSET_CACHE_TTL_SECONDS`
- `FRIEND_CACHE_TTL_SECONDS`

## Mounted-Volume Deployment

- Mounted storage backs local filesystem paths. It does not replace the separate Hugging Face dataset repo IDs.
- Keep HF repo separation explicit: `HF_MEMORY_REPO_ID` for conversations,
  `DOCUMENT_HF_REPO_ID` for document memory, `HISTORY_LOG_HF_REPO_ID` for
  history logs, and `CALENDAR_HF_REPO_ID` for calendar data.
- Use mounted paths for local filesystem state and CommitScheduler working data.
- For conversation memory, `CONVERSATION_STORAGE_PATH` is the local working/cache
  directory used by the HF-backed sync path. Restart persistence for
  conversation history still depends on `HF_MEMORY_TOKEN` and
  `HF_MEMORY_REPO_ID` in the current implementation.
- `BOT_IDENTITY_STORAGE_PATH` stores runtime identity overrides.
- `STAFF_MEMORY_STORAGE_PATH` stores review-agent staff memory.
- There is no persisted APScheduler task store in this implementation. Scheduled jobs remain runtime-only.

Example mounted-volume paths:

```env
CONVERSATION_STORAGE_PATH=/data/ms-sunshine/conversations
DOCUMENT_STORAGE_PATH=/data/ms-sunshine/documents
HISTORY_LOG_PATH=/data/ms-sunshine/logs
CALENDAR_DATA_PATH=/data/ms-sunshine/calendar
BOT_IDENTITY_STORAGE_PATH=/data/ms-sunshine/bot_identity/profile.json
STAFF_MEMORY_STORAGE_PATH=/data/ms-sunshine/staff_memory/staff_memory.json
```

## Local Storage Paths

This section expands the mounted-path variables that are listed briefly in the
feature sections above.

### `CONVERSATION_STORAGE_PATH`

- **Type:** String
- **Default:** `./data/conversations`
- **Description:** Local working/cache directory used by the HF-backed
  conversation memory sync path; by itself it does not enable restart
  persistence
- **Example:** `CONVERSATION_STORAGE_PATH=/data/ms-sunshine/conversations`

### `BOT_IDENTITY_STORAGE_PATH`

- **Type:** String
- **Default:** `./data/bot_identity/profile.json`
- **Description:** Local JSON file for runtime bot identity name and alias overrides
- **Example:** `BOT_IDENTITY_STORAGE_PATH=/data/ms-sunshine/bot_identity/profile.json`

### `STAFF_MEMORY_STORAGE_PATH`

- **Type:** String
- **Default:** `./data/staff_memory/staff_memory.json`
- **Description:** Local JSON file for review-agent staff memory on the mounted volume
- **Example:** `STAFF_MEMORY_STORAGE_PATH=/data/ms-sunshine/staff_memory/staff_memory.json`

## Calendar & Reminder Configuration

### `CALENDAR_ENABLED`

- **Type:** Boolean
- **Default:** `true`
- **Description:** Enable/disable calendar and reminder functionality
- **Example:** `CALENDAR_ENABLED=true`

### `CALENDAR_REMINDER_HOUR`

- **Type:** Integer
- **Default:** `8`
- **Description:** Hour (0-23) for daily calendar reminders in server timezone
- **Example:** `CALENDAR_REMINDER_HOUR=9`

### `CALENDAR_DATA_PATH`

- **Type:** String
- **Default:** `./data/calendar`
- **Description:** Local directory path for calendar event storage
- **Example:** `CALENDAR_DATA_PATH=./data/calendar`

This path remains the local cache/rollback store even when `PERSISTENCE_BACKEND=convex`.

### `CALENDAR_HF_REPO_ID`

- **Type:** String (Optional)
- **Default:** `None`
- **Description:** Hugging Face repository ID for calendar data synchronization (requires `HF_MEMORY_TOKEN`)
- **Example:** `CALENDAR_HF_REPO_ID=username/calendar-data`

This is used only when the calendar runtime path remains local/HF-backed. When `PERSISTENCE_BACKEND=convex`, Convex becomes the primary structured store for calendar data.

### `CALENDAR_SYNC_INTERVAL_SECONDS`

- **Type:** Integer
- **Default:** `300`
- **Description:** Interval in seconds between Hugging Face sync operations
- **Example:** `CALENDAR_SYNC_INTERVAL_SECONDS=600`
