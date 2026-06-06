# Plan — eliminate duplicate short-message passthrough bug in legacy LINE handler

**Date:** 2026-06-06  
**Scope:** one-file fix + regression test  
**Risk:** low; behavior match with already-fixed `TranslationAgent`.

## Task 1 — reproduce with a regression test
- Add/adjust test in `tests/test_translation_agent_ai.py` (or the closest legacy-handler test):
  - Simulate Thai input under 30 chars through the legacy handler/service path.
  - Assert the translation is attempted (not silently dropped).

## Task 2 — patch the legacy handler
- File: `src/handlers/message_handler.py`
- Change the unconditional
```python
if len(text.strip()) < 30:
    return
```
into an English-only passthrough exactly like the fixed agent:
```python
if source_lang == "en" and len(text.strip()) < 30:
    return
```

## Task 3 — verify and then stop
- Run `pytest tests/test_translation_agent_ai.py -q` and the most relevant legacy handler test(s).
- If green, commit with a focused message; do not change OpenRouter model or add Ollama paths in this change.

## Success criteria
- Short Thai translation no longer silently dropped in the legacy path.
- Same English short-passthrough behavior preserved.
- Test output shown, no claims without evidence.
