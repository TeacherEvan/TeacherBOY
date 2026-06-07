# Image Analyzer Vision Fix Design

## Problem Statement

The ImageAnalyzerAgent fails to analyze images because:
1. **No vision-capable model configured**: `openrouter_default_model` (`nvidia/nemotron-3-ultra-550b-a55b:free`) is text-only; `openrouter_vision_model` is not set
2. **Reply token expiry**: Vision API calls take 30-60s, exceeding LINE's ~1min reply token TTL. The agent sends "analyzing" via `reply_message` (consuming token), then vision call blocks, then result via `push_message` — but the token may already be invalid
3. **Limited fallback chain**: Only Hermes → OpenRouter (text model) → GitHub Models; no HF Inference API

Error observed:
```
linebot.v3.messaging.exceptions.ApiException: (400) Bad Request
{"message":"Invalid reply token"}
```

## Solution Overview

| Component | Change |
|-----------|--------|
| **OpenRouter vision model** | Configure `openrouter_vision_model=google/gemini-flash-1.5` (free, fast, vision-capable) |
| **HuggingFace Inference API** | New service `hf_inference_service.py` with `meta/llama-3.2-90b-vision-instruct` (free tier) |
| **Fallback chain** | Add `hf_inference` to priority after OpenRouter: `hermes,openrouter,hf_inference,github` |
| **Push-message pattern** | Replace `reply_message` for "analyzing" with `push_message` to avoid reply token expiry |
| **Config** | Add HF API key env var, vision model settings, update provider priority |

## Architecture

```
User sends image/question
       │
       ▼
_send_analyzing_message() ← NOW uses push_message (no reply token)
       │
       ▼
chat_completion_with_vision_fallback()
       │
       ├── hermes_service.chat_completion_with_vision()
       ├── openrouter_service.chat_completion_with_vision() ← uses openrouter_vision_model
       ├── hf_inference_service.chat_completion_with_vision() ← NEW: meta/llama-3.2-90b-vision-instruct
       └── github_models_service.chat_completion_with_vision()
       │
       ▼
Format response → push_message result
```

## Detailed Changes

### 1. Config (`src/config.py`)
- Add `hf_inference_api_key: str | None`
- Add `hf_inference_vision_model: str = "meta/llama-3.2-90b-vision-instruct"`
- Update `llm_fallback_provider_priority` default: `"hermes,openrouter,hf_inference,github"`
- Set `openrouter_vision_model: str = "google/gemini-flash-1.5"`

### 2. New Service: `src/services/hf_inference_service.py`
```python
class HFInferenceService:
    - is_configured() → checks HF_API_KEY
    - chat_completion_with_vision(messages, model, temperature, max_tokens)
    - Uses HF Inference API: https://api-inference.huggingface.co/models/{model}
    - OpenAI-compatible payload format
    - 60s timeout for vision models
```

### 3. Update Fallback (`src/utils/llm_fallback.py`)
- Import `hf_inference_service`
- Add `"hf_inference"` to `_run_one_vision_provider()` wrapper
- Add HF to priority loop in `chat_completion_with_vision_fallback()`

### 4. Fix Reply Token Expiry (`src/agents/image_analyzer_agent.py`)
- **Change `_send_analyzing_message()`**: Use `push_message` instead of `reply_message`
  - Compute `target` from event (group_id / room_id / user_id)
  - If no target, skip silently (edge case)
- **Update call sites** to not rely on `event.reply_token`:
  - `_handle_question()` → already uses push for result
  - `_process_direct_debrief()` → already uses push for result
  - `_handle_calendar_confirmation()` → uses reply for confirmation; keep reply (user just responded, token is fresh)

### 5. Update Session Manager (if needed)
- `src/services/image_analyzer_session_manager.py` — no changes needed

### 6. Tests
- Add test for HF inference service
- Update image analyzer tests to mock new provider
- Test push-message pattern

## Configuration (Environment Variables)

```bash
# Existing
OPENROUTER_API_KEY=...
OPENROUTER_VISION_MODEL=google/gemini-flash-1.5    # NEW: set explicitly

# New
HF_INFERENCE_API_KEY=hf_...                         # Get from https://huggingface.co/settings/tokens
HF_INFERENCE_VISION_MODEL=meta/llama-3.2-90b-vision-instruct

# Updated priority
LLM_FALLBACK_PROVIDER_PRIORITY=hermes,openrouter,hf_inference,github
```

## Success Criteria

1. ✅ Image analysis completes without "Invalid reply token" error
2. ✅ Vision fallback chain works: Hermes → OpenRouter (gemini-flash) → HF (Llama-3.2-Vision) → GitHub Models
3. ✅ Response time < 60s (push-message avoids token expiry)
4. ✅ All existing tests pass
5. ✅ New tests for HF inference service pass

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| HF Inference API rate limits | Free tier has limits; catch 429, retry with backoff, fall through to next provider |
| Vision model unavailable | Multiple providers in chain; graceful degradation |
| Push message fails (not friend) | `_send_analyzing_message` logs warning but continues; result push may also fail — handled by existing error flow |
| Config migration | New env vars are optional; defaults preserve current behavior if not set |

## Implementation Order

1. **Config** — Add new settings, update defaults
2. **HF Inference Service** — New file, unit tests
3. **Fallback Chain** — Update `llm_fallback.py`
4. **Push-Message Fix** — Update `image_analyzer_agent.py`
5. **Tests** — Add/update tests
6. **Verify** — Run full test suite, manual test on HF Spaces

## Out of Scope

- Maton API integration (explicitly excluded per project constraints)
- Changing profiler agent (separate agent, uses `profiler_model` = `openai/gpt-4o`)
- Calendar agent changes (only called after analysis succeeds)