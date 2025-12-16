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
