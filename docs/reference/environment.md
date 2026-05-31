# Environment variables

Ms. Green reads configuration from `.env` (local) and environment variables (production).

Start from `.env.example`.

## Required

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

## Recommended

- `GITHUB_MODELS_PAT` (preferred AI provider for translation and vision)
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

## AI Translation

- Translation uses the shared AI translation service.
- Configure at least one provider:
	- `GITHUB_MODELS_PAT`
	- `OPENROUTER_API_KEY`

## LLM (OpenRouter)

- `OPENROUTER_API_KEY`
- `OPENROUTER_DEFAULT_MODEL` (default: `google/gemma-2-9b-it`)
- `DEFAULT_MODEL` (alias of `OPENROUTER_DEFAULT_MODEL`, useful on Hugging Face Spaces)
- `LLM_SYSTEM_PROMPT` (optional; controls bot personality/tone)

## LLM (GitHub Models)

- `GITHUB_MODELS_PAT`
- `GITHUB_MODELS_DEFAULT_MODEL`
- `LLM_PROVIDER_PRIORITY` (`github,openrouter` by default)

## Web Search (Brave)

- `BRAVE_SEARCH_API_KEY`

## News (optional)

- `EXCHANGE_RATE_API_KEY` (ExchangeRate-API)
- `TAT_API_KEY` (Tourism Authority of Thailand events)

## Conversation Memory (HF Hub)

- `CONVERSATION_MEMORY_ENABLED`
- `CONVERSATION_MAX_MESSAGES`
- `CONVERSATION_TTL_HOURS`
- `HF_MEMORY_TOKEN`
- `HF_MEMORY_REPO_ID`

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
- `ZEUS_ERROR_STYLE`

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

### `CALENDAR_HF_REPO_ID`

- **Type:** String (Optional)
- **Default:** `None`
- **Description:** Hugging Face repository ID for calendar data synchronization (requires `HF_MEMORY_TOKEN`)
- **Example:** `CALENDAR_HF_REPO_ID=username/calendar-data`

### `CALENDAR_SYNC_INTERVAL_SECONDS`

- **Type:** Integer
- **Default:** `300`
- **Description:** Interval in seconds between Hugging Face sync operations
- **Example:** `CALENDAR_SYNC_INTERVAL_SECONDS=600`
