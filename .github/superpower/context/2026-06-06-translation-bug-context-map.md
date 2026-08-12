# Context Map: Translation bot failure

Date: 2026-06-06
Topic: Translation provider chain not producing outputs

## Primary files
- `src/services/ai_translation_service.py` — core provider chain used by `TranslationAgent._translate_message`
- `src/agents/translation_agent.py` — entry point that calls `ai_translation_service.translate`
- `src/config.py` — settings/env source for API keys (google, libre, openrouter, etc.)

## Dependencies
- `TranslationAgent.handle` → `TranslationAgent._translate_message` → `AITranslationService.translate`
- `AITranslationService` depends on module-level singletons: `github_models_service`, `openrouter_service`, `libre_translate`, `hermes_service`, `nous_inference_service`
- Each provider exposes `is_configured()`, `chat_completion(...)`, `get_last_error()`
- `settings.google_translate_api_key` is read directly inside `translate()` for the Google provider

## Ripple effects
- Adding logging to `ai_translation_service.py` affects all translation traffic, but is read-only telemetry
- Any new script should import `AITranslationService` carefully to avoid side effects from module-level singleton init
- Tests in `tests/test_ai_translation_service.py` and `tests/test_translation_agent_ai.py` may need updates if provider contracts change

## Patterns
- Provider loop iterates and `continue`s on failure, logs at warning/error level
- Thai branch returns `"[Translation failed] {text}"` on None; English branch returns `"Translation failed"` only
- No metric or log currently records provider config state (`is_configured()`) at startup or per attempt
