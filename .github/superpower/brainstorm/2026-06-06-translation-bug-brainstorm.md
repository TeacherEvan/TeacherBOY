# Brainstorm: Translation bot not producing outputs

Date: 2026-06-06
Topic: Translation failures in TeacherBOY / Ms. Green LINE bot
Status: Proposed

## Observed symptom
- Bot translation is "isn't working and not providing outputs"
- Recent commits suggest translation behavior was recently touched:
  - `fix(legacy): long Thai translation guard in legacy handler; regression test`
  - `fix(translation): prefer google translate then nous fallback; guard libre; keep Thai always translating`

## Codebase context discovered
- Three translation-related service files exist:
  - `src/services/ai_translation_service.py` (used by `TranslationAgent`)
  - `src/services/google_translation.py`
  - `src/services/translation_service.py`
- `TranslationAgent._translate_message` calls `self.ai_translation_service.translate(...)`
- `AITranslationService.translate` builds providers: Google → Nous → OpenRouter → Hermes; Libre only if `is_configured()`
- Thai path in `_translate_message` is special: if provider returns None, it still returns `"[Translation failed] ..."` rather than empty None

## Approaches

### Option A — Consolidate and harden provider chain
- Make `ai_translation_service` the single source of truth for translation
- Remove or deprecate `src/services/translation_service.py` and `src/services/google_translation.py`
- Add deterministic provider selection + explicit error surfacing per provider
- Trade-off: larger refactor, higher risk of breaking other flows unless tests prove no callers remain

### Option B — Diagnose-first with runtime evidence, then minimal fix
- Add temporary telemetry/logging to `ai_translation_service.translate` to capture per-provider status, config state, last error, tenant config hints
- Run integration style probe against live providers directly
- Fix only the discovered break
- Trade-off: faster to restore; exposes why previous attempts failed, but uses runtime env state (not test env)

### Option C — Defensive translation path + provider gating
- Tighten provider gating so failures are visible instead of swallowed
- Make LibreTranslate optional but explicit with config check
- Ensure Thai text never silently short-circuits
- Trade-off: safer behavior but may still not fix underlying provider failure if provider itself is unreachable or unconfigured in production

## Branch and merge candidate
- Feature branch: `fix/translation-provider-chain` off `main` before modifying anything
- Rationale: recent commits already touched translation; maintain clean reroll path

## Recommendation
- Recommend Option B immediately, then move to Option A/C based on findings
- Prioritize evidence over assumptions to avoid doubling down on stale provider logic

## Open questions before plan
1. Is Google Translate key configured on HF Spaces? Is the provider auth/call succeeding?
2. Are LibreTranslate and Hermes actually configured in production `.env`?
3. Which test files currently cover translation and are they mocked to always succeed?
