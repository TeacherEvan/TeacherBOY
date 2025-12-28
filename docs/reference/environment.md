# Environment variables

TeacherBOY reads configuration from `.env` (local) and environment variables (production).

Start from `.env.example`.

## Required

- `LINE_CHANNEL_SECRET`
- `LINE_CHANNEL_ACCESS_TOKEN`

## Recommended

- `GOOGLE_TRANSLATE_API_KEY` (higher-quality translations)

## Admin

- `ADMIN_USER_IDS` (comma-separated)
- `ADMIN_SETUP_KEY` (temporary bootstrap)

## Moderators

- `MODERATOR_USER_IDS` (comma-separated)

## Tracing

- `ENABLE_TRACING` (default: `False`)
- `OTEL_SERVICE_NAME` (default: `TeacherBOY`)
- `OTEL_EXPORTER_OTLP_ENDPOINT` (default: `http://localhost:4318`)

## Server

- `HOST` (default: `0.0.0.0`)
- `PORT` (default: `8000`)
- `DEBUG` (default: `False`)

## Translation (fallback)

- `LIBRETRANSLATE_API_URL`
- `LIBRETRANSLATE_API_KEY`

## LLM (OpenRouter)

- `OPENROUTER_API_KEY`
- `OPENROUTER_DEFAULT_MODEL` (default: `google/gemma-2-9b-it:free`)
- `LLM_SYSTEM_PROMPT` (optional; controls bot personality/tone)

## Web Search (Brave)

- `BRAVE_SEARCH_API_KEY`

## News (optional)

- `EXCHANGE_RATE_API_KEY` (ExchangeRate-API)
- `TAT_API_KEY` (Tourism Authority of Thailand events)

## Cache TTLs (seconds)

- `WEATHER_CACHE_TTL_SECONDS`
- `NEWS_CACHE_TTL_SECONDS`
- `HOLIDAY_CACHE_TTL_SECONDS`
- `BITCOIN_CACHE_TTL_SECONDS`
- `EXCHANGE_CACHE_TTL_SECONDS`
- `COLOR_CACHE_TTL_SECONDS`
- `SUNSET_CACHE_TTL_SECONDS`
- `FRIEND_CACHE_TTL_SECONDS`
