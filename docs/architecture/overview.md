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

- **ModModeAgent** (Priority 4): Group moderation — activation, modes (all/special), kick/warn/ban, 3-strike warnings, harmful content detection, ban list with auto-kick, Flex dashboard. Intercepts FIRST in mod-enabled groups.
- Admin Agent (priority 5): in-chat operations, only registered when configured.
- Search Agent (priority 8): Brave Search via `Ms. Green search ...` (DM-only for non-admins).
- LLM Agent (priority 9): OpenRouter chat via `Ms. Green ...` (DM-only for non-admins).
- Translation Agent (priority 10): Thai ↔ English translation with session + dedup + rate limiting.
- Special News Agent (priority 12): `/special news` (DM-only).
- News Agent (priority 15): `news` / `ข่าว` (friend-gated in groups; translation-only for non-friends).

## Services

- **ModModeService** (`src/services/mod_mode_service.py`): Convex CRUD for modModeState; activation/deactivation; mode queries
- **BanListService** (`src/services/ban_list_service.py`): Convex CRUD for banList; auto-kick on join; unban
- **WarningService** (`src/services/warning_service.py`): Convex CRUD for userWarnings; 3-strike logic; read tracking; **`reset_warnings`** for admin unban
- **HarmfulContentDetector** (`src/services/harmful_content_detector.py`): Configurable keyword + optional LLM detection; supports JSON file and env var
- **ModAuditLog** (`src/services/mod_audit_log.py`): Append-only JSONL audit trail to Hugging Face Hub
- **MetricsService** (`src/services/metrics_service.py`): In-memory counters + **provider latency tracking** (avg ms per provider)
- Shared `httpx.AsyncClient` pool created once in lifespan and injected into all services (translation, Convex, etc.)
- Translation providers:
  - Shared AI translation service (Gemini primary, OpenRouter fallback)
  - **Latency metrics recorded per provider** via `metrics_service.record_provider_latency()`

- Session/rate-limit state:
  - `src/services/session_manager.py`
  - `src/services/rate_limiter.py`

## Operational endpoints

- `/health` (liveness)
- `/readiness` (reports startup/data/agent readiness once the service is serving requests; may return HTTP 503 when startup data or agents are not ready)

## Observability

Tracing is optional (OpenTelemetry): [docs/TRACING.md](../TRACING.md)
