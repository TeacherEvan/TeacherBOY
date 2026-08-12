# Plan — OpenRouter provider hardening without touching `main.py`

**Date:** 2026-06-06  
**Scope:** `src/services/openrouter_service.py` + `tests/test_openrouter_service.py`  
**Risk:** low; behavior-preserving overrides only.

## Context
- Latest `main.py` was merged with unrelated startup/telemetry work; I already reverted my unsafe `main.py` patch.
- Current default model: `google/gemma-2-9b-it` (invalid for current registry).
- Fast free candidates from API survey: `z-ai/glm-4.5-air:free`, `qwen/qwen3-coder:free`.
- `AITranslationService` already calls `model_for_translation() or default_model`.

## Task 1 — regression test: OpenRouter skips when default model is invalid
- In `tests/test_openrouter_service.py` (create if missing, probably exists):
  - Patch `settings.openrouter_default_model` to `google/gemma-2-9b-it`.
  - Stub HTTP 404 response.
  - Assert completion returns `None` and `is_configured()` remains true.

## Task 2 — runtime fallback in `OpenRouterService`
- In `src/services/openrouter_service.py`:
  - After constructing `target_model`, if request fails with 404/400 model-token error, fallback to one valid free model from a small whitelist chosen at runtime from `/api/v1/models` if available.
  - Cache the chosen fallback in-memory for the process lifetime.
  - Always try `z-ai/glm-4.5-air:free` first if present.

## Task 3 — default-model validation on startup
- Still in `src/services/openrouter_service.py`, in `__init__`:
  - If `settings.openrouter_default_model` is not in current `/api/v1/models`, downgrade to a known-valid free fallback and log reason.

## Success criteria
- Invalid model no longer causes 404 fallthrough.
- Tests pass.
- `main.py` unchanged.
