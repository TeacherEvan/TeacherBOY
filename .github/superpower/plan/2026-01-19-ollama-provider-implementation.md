# Implementation Plan: Ollama Provider for TeacherBOY

## Context
Investigation complete: HF Pro/Buckets/Memory are viable for persistent storage, but HF is not a practical Ollama runtime. The actionable path is:
1. Add Ollama as an LLM provider in TeacherBOY's fallback chain
2. Keep existing HF Hub memory integration intact
3. Allow local/EC2 Ollama to serve Hermes models for Q&A + translation

## TDD Tasks

### Task 1: Ollama Service Skeleton
- File: `src/services/ollama_service.py`
- Create `OllamaService` with `chat(messages, model, **kwargs)` method
- Target: `http://localhost:11434/v1/chat/completions` (OpenAI-compatible)
- Must raise on connection failure, return parsed JSON on success

### Task 2: Config Support
- File: `src/config.py`
- Add fields: `ollama_base_url`, `ollama_default_model`, `ollama_enabled`
- Default: `http://localhost:11434`, `hermes2:latest`, enabled=False

### Task 3: Provider Router Integration
- File: `src/utils/llm_fallback.py` or `src/services/hermes_service.py`
- Parse `llm_fallback_provider_priority` to include `ollama`
- Add routing logic: if `ollama` in priority and enabled, call `OllamaService.chat`

### Task 4: Tests
- File: `tests/test_ollama_service.py`
- Mock HTTP calls to Ollama endpoint
- Test success path, connection error, timeout, invalid response
- Assert provider router honors `ollama` priority order

## Verification
- Run `pytest tests/test_ollama_service.py -v`
- Run `ruff check src/services/ollama_service.py src/config.py`
