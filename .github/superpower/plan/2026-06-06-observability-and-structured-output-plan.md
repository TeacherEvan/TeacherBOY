# Implementation Plan: Observability & Structured Output

**Date:** 2026-06-06
**Design:** [2026-06-06-next-phase-enhancements-design.md](./../brainstorm/2026-06-06-next-phase-enhancements-design.md)
**Goal:** Add structured logging, validated debrief extraction, and persistent HF storage awareness.

**Status:** Complete — all tasks executed and verified 2026-06-06.

---

## Completed Implementation

### 1. Structured logging via loguru
- Added `src/services/logging_service.py` with one-object-per-line JSON output
- File + stderr sinks; rotation + retention
- Singleton `logging_service` instantiated at import time
- Tests: `tests/test_logging_service.py` validates JSON schema and message/level fields
- Wired into `src/main.py` lifespan: startup/shutdown + `/data` availability reporting

### 2. Debrief schema for structured debrief extraction
- Added `DebriefSchema` to `src/services/debrief_extraction_service.py`
- Fields: `topics_covered`, `comprehension_level`, `key_phrases_learned`, `suggested_review`, `confidence_score`, `notes`
- Tests: `tests/test_debrief_schema.py` covers valid and invalid cases

### 3. HF Spaces persistent storage helper
- Added `src/services/persistent_storage.py`
- Exposes `get_persistent_path()`, `is_persistent_storage_available()`, `get_storage_subdir()`
- Fallback to `./data/<name>` when `/data` is unavailable
- Tests: `tests/test_persistent_storage.py` validates path resolution, availability check, fallback

### 4. Dependency fix for HF build
- Relaxed `requirements.txt`: `pydantic==2.5.0` → `pydantic>=2.7.0,<3.0.0`
- Unblocked `instructor==1.3.0` dependency resolver

## Verification Commands
- `pytest tests/test_logging_service.py -v`
- `pytest tests/test_persistent_storage.py -v`
- `pytest tests/test_debrief_schema.py -v`

## Remaining Follow-ups (future phase)
- LLM tracing with Phoenix/Arize in a separate service file
- Use `DebriefSchema` as response model in `extract_debrief_structured`
- Add loguru-powered rotation for HF Space disk limits
