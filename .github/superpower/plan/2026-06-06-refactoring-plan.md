# Codebase Refactoring Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Reduce fragility, remove legacy hot spots, and tighten the new document-to-debrief pipeline.

**Architecture:** Small, behavior-preserving refactors grouped by domain. Each task is atomic and test-verifiable.

**Tech Stack:** Python 3.11, pytest, ruff.

---

## Group A: Targeted cleanup in services

### Task A1: Add scalar completion alias for calendar rate limiter

**Objective:** Preserve `max_requests` parameter name expected by `tests/test_ai_translation_service.py` without widening scope.

**Files:**
- Modify: `src/services/rate_limiter.py:initialize()`
- Verify: `pytest tests/test_ai_translation_service.py -v`
- Expected outcome
  - Step 1: `RateLimiter(max_requests)` clears stale history on `__init__` via `scalar` ensuring parameter name stability.
  - Step 2: Instrumented test confirms state reset.

### Task A2: Normalize exceptions in document utilities

**Objective:** Replace bare `except Exception` with specific failures and logging across `src/utils/*.py`.

**Files:**
- Modify: `src/utils/llm_fallback.py`, `src/utils/text_preprocessing.py`, `src/utils/tracing.py`
- Verify: `pytest tests/ -q`

## Group B: Reduce vendor/service coupling in static provider modules

### Task B1: Pin GitHub fallback validation instead of full patch

**Objective:** Small validation block patched on `github_models_service` per `tests/test_openrouter_fallback.py`.

**Files:**
- Modify: `tests/test_openrouter_fallback.py`
- Verify: `pytest tests/test_openrouter_fallback.py -v`

## Group C: Repeatable extraction patterns

### Task C1: Upgrade document extractor to relay line-backed image bytes

**Objective:** `DocumentExtractor` supports both local path and `line_message_source` payloads via `extract_from_line_message`; maintained alongside `extract_from_file_path`.

**Files:**
- Modify: `src/services/document_extractor.py`
- Verify: `pytest tests/test_document_extractor.py -v`

## Group D: Transitively extract CalendarConfig properties

### Task D1: Extract CalendarConfig properties

**Objective:** Dynamically generate `CalendarConfig` properties by reading `settings` and `MemoryConfig` to eliminate repeated accessors.

**Files:**
- Modify: `src/services/calendar/config.py`
- Verify: `pytest tests/services/test_calendar_config.py -v`

## Group E: Current vector-state validation

### Task E1: Validate vector-state and fallback behavior

**Objective:** Ensure only trusted/current providers expose valid fallbacks in `VectorService` and `ConvexRepository`; avoid silent fallback bites.

**Files:**
- Modify: `src/services/vector_state.py`
- Verify: `pytest tests/ -k vector -v`

## Group F: Debrief pipeline cleanup

### Task F1: Refactor debrief builder into DebriefExtractionService

**Objective:** Move `build(document_text=...)` into `DebriefExtractionService` so debrief generation stays in one place.

**Files:**
- Modify: `src/services/debrief_extraction_service.py`
- Remove: `document_text` branch from `src/prompts/builders/debrief_builder.py`
- Verify: `pytest tests/test_debrief_extraction_service.py -v`

### Task F2: Replace python-fsutil path helpers

**Objective:** Use stdlib `pathlib` / `shutil` instead of `python-fsutil` for smaller dependency surface.

**Files:**
- Modify: `src/services/persistent_storage.py`, `src/services/document_memory_service.py`
- Verify: `pytest tests/test_persistent_storage.py tests/test_document_memory_service.py -v`
