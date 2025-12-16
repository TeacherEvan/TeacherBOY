# Architecture Overview

TeacherBOY is a FastAPI webhook app for LINE.

## Runtime flow (high-level)

1. LINE sends events to `POST /webhook`.
2. The app validates the LINE signature.
3. It skips self-messages (to prevent loops).
4. It routes text messages through the Agent Router (priority order).
5. The first agent that successfully handles the message returns a reply via LINE Messaging API.

## Key entrypoints

- App entry + lifecycle: `src/main.py`
- Routing contract: `src/agents/agent_router.py`
- Primary behavior: `src/agents/translation_agent.py`

## Agents

- Admin Agent (priority 5): in-chat operations, only registered when configured.
- Translation Agent (priority 10): Thai ↔ English translation with session + dedup + rate limiting.

## Services

- Shared `httpx.AsyncClient` is created once and injected into translation services.
- Translation providers:
  - Google Cloud Translate (primary)
  - LibreTranslate (fallback)

- Session/rate-limit state:
  - `src/services/session_manager.py`
  - `src/services/rate_limiter.py`

## Operational endpoints

- `/health` (liveness)
- `/readiness` (dependencies/features)

## Observability

Tracing is optional (OpenTelemetry): [docs/TRACING.md](../TRACING.md)
