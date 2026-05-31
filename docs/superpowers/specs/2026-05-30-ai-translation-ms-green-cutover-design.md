# AI Translation and Ms. Green Hard-Cutover Design

Date: 2026-05-30

## Goal

Replace the current Google Translate and LibreTranslate translation path with AI-based translation everywhere, refresh help and documentation to match the current feature set, and perform a hard user-facing cutover from Zeus to Ms. Green.

After this change:

- Only Ms. Green commands and naming should work in user-facing behavior.
- Translation should be handled by AI providers, not Google Translate or LibreTranslate.
- Help, docs, startup metadata, and user-visible copy should describe the bot as Ms. Green.

## Non-Goals

- Full internal repository rename in one pass.
- Large module moves or class renames that do not change user-facing behavior.
- Changing unrelated agent priorities, routing rules, or deployment architecture.
- Expanding translation into a general rewrite or summarization feature.

## Current Problem

The current implementation has three conflicting realities:

1. Translation still depends on `google_translation.py` and `translation_service.py`.
2. User-facing help and docs still describe Google Translate, LibreTranslate, and Zeus-branded commands.
3. The repo now has an identity abstraction, but many user-visible strings and prefixed triggers are still Zeus-oriented.

That creates product inconsistency and makes the help surface inaccurate.

## Approaches Considered

### 1. Recommended: Dedicated AI translation service plus user-facing hard cutover

Add a dedicated `AITranslationService` and route all translation use cases through it. Replace user-facing Zeus naming with Ms. Green, but keep internal module/class names in place unless they directly affect behavior or clarity.

Trade-offs:

- Lowest behavioral risk for a cross-cutting change.
- Keeps the new translation logic centralized and testable.
- Avoids a noisy repo-wide rename while still achieving a true hard cutover for users.
- Leaves some internal `zeus_*` identifiers temporarily intact until a later cleanup pass.

### 2. Minimal: Inline AI replacement in existing agents

Replace Google/Libre calls directly inside `TranslationAgent` and `NewsAgent`, then do targeted copy edits for Ms. Green.

Trade-offs:

- Fastest initial slice.
- Higher maintenance cost because translation behavior stays duplicated.
- Easier to miss one translation surface or fallback path.
- Harder to reason about provider fallback and instrumentation consistently.

### 3. Broader: Full repo rename plus AI translation in one pass

Replace all user-facing and internal Zeus naming, config names, docs, comments, and helper APIs while also changing translation providers.

Trade-offs:

- Most complete final state.
- Highest risk, widest blast radius, and heaviest testing burden.
- Increases chances of regressions in unrelated flows because many files change for naming only.
- Slower to review and harder to roll back.

## Recommendation

Use approach 1.

It satisfies the hard cutover requirement for real users while keeping the implementation bounded:

- translation logic becomes centralized,
- help/docs become truthful,
- Ms. Green becomes the only accepted public identity,
- and the codebase avoids an unnecessary large-scale internal rename during the same change.

## Design

### Translation architecture

Create a dedicated AI translation layer responsible for:

- language direction selection,
- translation prompting,
- provider fallback between GitHub Models and OpenRouter,
- preserving formatting, punctuation, and line breaks,
- returning structured metadata for metrics/logging.

Proposed file responsibility:

- `src/services/ai_translation_service.py`
  - Primary entry point for all translation requests.
  - Uses existing provider services rather than duplicating raw HTTP logic.
  - Exposes a narrow API such as `translate(text, source_lang=None, target_lang=None, context=None)`.

Existing consumers to migrate:

- `src/agents/translation_agent.py`
  - Replace Google/Libre fallback chain with `AITranslationService`.
- `src/agents/news_agent.py`
  - Route headline translation through the same service.
- Any startup or health metadata currently describing Google/Libre translation
  - Replace with AI translation capability status.

### Translation behavior

Default behavior should remain translation-first, not chatbot-style paraphrasing.

Service rules:

- Preserve message meaning closely.
- Preserve list structure, emojis, URLs, and line breaks when practical.
- Avoid adding commentary unless the caller explicitly wants it.
- If the input is ambiguous or mixed-language, prefer a faithful translation instead of an explanation.
- If provider calls fail, return a user-safe fallback message rather than exposing provider details.

### Identity hard cutover

Ms. Green becomes the only accepted public identity.

Behavioral consequences:

- `Ms. Green ...` prefixed commands work.
- Legacy `Zeus ...` prefixed commands no longer match.
- Help text, fallback text, prompts, welcome copy, profiler headers, and visible service names switch to Ms. Green.
- Public docs and examples use Ms. Green only.

Internal consequence:

- Existing internal names may remain temporarily if they are not user-visible.
- The identity service defaults and aliases must remove `zeus` from supported prefixes for this cutover.

### Help and docs refresh

Help must reflect both the current feature set and the new translation model.

Required help updates:

- Replace Zeus naming with Ms. Green.
- Remove Google Translate and LibreTranslate provider messaging.
- Describe translation as AI-powered.
- Ensure feature tips reflect the real current feature inventory.

Required doc updates:

- Quickstart and setup guides.
- Translation-related documentation.
- KPS assistant / identity documentation.
- Any examples that still teach Zeus-prefixed commands.

### Startup and observability

Current startup and readiness surfaces expose Google-specific configuration language. That should change from provider-specific legacy wording to capability-based wording.

Examples of intended direction:

- `translation_backend: "ai"`
- `translation_provider_priority: ["github_models", "openrouter"]`
- remove `google_translate_enabled`

This keeps health/readiness truthful without coupling them to retired providers.

## Affected Areas

Primary implementation surfaces:

- `src/agents/translation_agent.py`
- `src/agents/news_agent.py`
- `src/agents/help_agent.py`
- `src/main.py`
- `src/config.py`
- `src/services/bot_identity_service.py`
- `src/services/google_translation.py`
- `src/services/translation_service.py`

Likely test surfaces:

- translation agent tests
- news translation tests
- help tests
- main/readiness tests
- bot identity tests

Likely doc surfaces:

- `README.md`
- `docs/README.md`
- `docs/guides/*.md`
- `docs/reference/*.md`
- any translation- or Zeus-specific docs

## Error Handling

The user should see stable translation behavior even if one AI provider fails.

Design rules:

- Fail over from primary provider to fallback provider inside `AITranslationService`.
- Log provider failures with enough detail for debugging.
- Do not leak raw provider errors to LINE users.
- If both providers fail, return a short neutral failure message in Ms. Green voice.

## Testing and Verification

Required verification should focus on behavior, not only string replacement.

Must verify:

- Translation agent uses AI service rather than Google/Libre paths.
- News headline translation uses the shared AI service.
- `Zeus ...` commands are rejected after cutover.
- `Ms. Green ...` commands are accepted.
- Help output no longer references Google Translate, LibreTranslate, or Zeus.
- Startup/readiness output no longer exposes Google-specific flags.
- Docs reflect Ms. Green and AI translation consistently.

## Migration Notes

This is a product-level hard cutover, not a compatibility rollout.

Operationally that means:

- No legacy public alias for Zeus.
- No mixed documentation period.
- No dual-provider translation stack kept alive for safety.

Rollback should be possible by reverting the change set, but the design does not include a dual-mode feature flag unless implementation proves one is necessary for safe deployment.