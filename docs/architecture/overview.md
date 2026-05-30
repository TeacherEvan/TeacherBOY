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

- Help Agent (priority 5): interactive help and command discovery.
- Admin Agent (priority 5): in-chat operations, only registered when configured.
- Calendar Agent (priority 6): reminders, inline add, scrape, and event management.
- Hannibal Profile Agent (priority 6): message-history profiling when GitHub Models is configured.
- Profiler Agent (priority 7): image-based psychological profiling.
- Image Analyzer Agent (priority 7): general image Q&A plus calendar image integration.
- Document Memory Agent (priority 8): PDF/DOCX storage and retrieval when enabled.
- Search Agent (priority 8): Brave Search via `Zeus search ...`.
- LLM Agent (priority 9): Zeus chat via configured LLM providers.
- Translation Agent (priority 10): Thai ↔ English translation with session + dedup + rate limiting.
- Special News Agent (priority 12): `/special news` (DM-only).
- News Agent (priority 15): `news` / `ข่าว` (friend-gated in groups; translation-only for non-friends).

## Services

- Shared `httpx.AsyncClient` is created once and injected into translation services.
- Translation providers:
  - Google Cloud Translate (primary)
  - LibreTranslate (fallback)

- Session/rate-limit state:
  - `src/services/session_manager.py`
  - `src/services/rate_limiter.py`

## Operational endpoints

- `/health` (cheap liveness probe; no external provider calls)
- `/readiness` (startup/data/agent readiness; returns HTTP 503 until ready)

## Observability

Tracing is optional (OpenTelemetry): [docs/TRACING.md](../TRACING.md)
