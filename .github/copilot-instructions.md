# TeacherBOY — Copilot coding-agent notes

## Extensions:

- Disable all extensions not related to the current project

## What this repo is

- Production LINE bot: Thai ↔ English translation is the core feature.
- FastAPI webhook app with a priority-based multi-agent router.

## Runtime flow (read these first)

- Entry point + lifecycle: `src/main.py` (FastAPI `lifespan`, `/webhook`, health endpoints).
- Webhook flow: LINE signature validation → parse events → **skip self-messages** via `bot_user_id` → `AgentRouter.route_message()`.
- Router contract: `src/agents/agent_router.py` iterates agents in ascending `get_priority()` and stops at the first successful `handle()`.

## Agents & priorities (lower = higher priority)

- `AdminAgent` (priority **5**) only registers when `ADMIN_USER_IDS` is set; commands start with `/admin` or `!admin` (`src/agents/admin_agent.py`).
- `TranslationAgent` (priority **10**) is the primary behavior (`src/agents/translation_agent.py`).
- `CalendarAgent` (priority **20**) is optional/scheduled-only and only registers when `GOOGLE_CALENDAR_GROUP_ID` is set (`src/agents/calendar_agent.py`, scheduler in `src/main.py`).

## Translation-specific conventions (don’t fight these)

- Chat IDs are normalized in `TranslationAgent._get_chat_id()` as `user_<id>`, `group_<id>`, `room_<id>`.
- Session state is in `src/services/session_manager.py`:
  - `is_session_active()` returns false while sleeping.
  - Sleep mode: `sleep_chat(chat_id, hours=24)`; wake: `wake_chat(chat_id)`.
  - Dedup: `is_duplicate_message(chat_id, text)` (per-chat history, default 60s window).
- Rate limiting uses `src/services/rate_limiter.py` singleton: **10 requests / 60s per chat**.

## Translation providers (shared HTTP client)

- `src/main.py` creates a single optimized `httpx.AsyncClient` and injects it into:
  - Google: `src/services/google_translation.py` (primary; async retry via `with_retry()` and `settings.translation_max_retries`).
  - LibreTranslate: `src/services/translation_service.py` (fallback).

## Dev workflows

- Run (Docker): `docker-compose up --build` (expects `.env`, binds `8000`).
- Run (local): `python -m uvicorn src.main:app --reload --port 8000`.
- Tests: `pytest` (async tests supported; `asyncio_mode=auto` in `pytest.ini`).
- Coverage: `pytest --cov=src --cov-report=html`.

## Adding a new agent (project pattern)

- Implement `BaseAgent` (`src/agents/base_agent.py`) with **async** `should_handle()` + `handle()`.
- Pick priority carefully: use **<10** only if the agent must preempt translation; otherwise use **>10**.
- Register the agent in the `lifespan` agent-registration section in `src/main.py`.

## Notes about legacy code

- `src/handlers/message_handler.py` contains an older “Flex-message translation” handler, but the production webhook path routes via agents; update it only if a test/feature explicitly depends on it.
