# Plan: Diagnose translation not producing outputs

Date: 2026-06-06
Phase: PLAN
Status: Pending approval

## TDD note for Option B
Approach is diagnostic, so tests are evidence/instrumentation tests rather than production behavior tests.

## Tasks

1) Inspect existing translation telemetry coverage
- Read `tests/test_ai_translation_service.py`
- Check whether current mocks block observing real provider-state behavior
- Expected: confirm test assumptions, identify mock gaps

2) Add provider-state telemetry in `ai_translation_service.translate`
- Log each provider's `is_configured()` bool and `get_last_error()` before and after calls
- Gate with existing log level; no behavior change
- Expected: runtime logs reveal broken/unconfigured providers in current env

3) Create repro script `scripts/probe_translation.py`
- Instantiate `AITranslationService` and call `.translate("สวัสดี", "th", "en")`
- Capture provider loop output and print final state by provider
- Expected: reproducible output showing which provider succeeds or fails

4) Review evidence and propose minimal fix
- After running probe against dev environment, summarize one concrete failure point
- Expected: one targeted fix candidate with exact location and why
