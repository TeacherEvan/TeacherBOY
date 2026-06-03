# Hermes Fallback Integration

I'm creating a minimal planning doc so we have one consistent source of truth while making the code changes.

## Scope

- Add a new provider path: Hermes, accessible via `src.services.HermesService`.
- Route TeacherBOY text LLM calls through a fallback helper in `src/utils/llm_fallback.py`.
- Provider order: GitHub Models -> OpenRouter -> Hermes.

## Files to touch after this plan

1. `src/config.py`
   - Add Hermes settings/helpers: base URL, API key, model ID, fallback chain.

2. `src/services/hermes_service.py` (new)
   - Thin OpenAI-compatible client to POST `BASE_URL/v1/chat/completions`.

3. `src/utils/llm_fallback.py` (new)
   - Try providers in priority order and return the first successful result.

4. `src/main.py`
   - Initialize Hermes if configured.
   - No broad rewrites.

## Verify

- Boot Doctor after edits: `python -m src.main --dry-run` from the TeacherBOY folder.
- Confirm fallback order from logs includes Hermes only if configured.