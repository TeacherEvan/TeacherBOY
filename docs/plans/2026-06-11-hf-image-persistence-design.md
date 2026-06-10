# Design: HF Image Persistence + Namespace Enforcement

## Overview
Add Hugging Face Hub persistence for image analysis data (images, prompts, responses) following the existing CommitScheduler pattern used by ConversationMemoryService, DocumentMemoryService, HistoryLogService, and CalendarService. Enforce `EvilEvan/teacherboy-*` repo naming convention.

## Scope
**In scope:**
- New `images_hf_repo_id` config + `images_hf_enabled` flag
- `ImageAnalyzerSessionManager` / `ImageAnalyzerAgent` persist base64 images + metadata to HF
- Config validators for all `*_hf_repo_id` fields enforcing `EvilEvan/teacherboy-*` prefix
- Local file storage mirror → CommitScheduler sync (5 min interval)

**Out of scope:**
- Unified admin query API (separate feature)
- History log schema extension (separate feature)
- Unified timestamp index (separate feature)

## Architecture

```
ImageAnalyzerAgent._handle_image()
    → download image → base64 → store in ImageAnalyzerSessionManager (existing)
    → NEW: write {image_base64, prompt, response, metadata} to local JSON
    → CommitScheduler syncs to HF Hub: EvilEvan/teacherboy-images

ImageAnalyzerAgent._handle_question()
    → vision API call
    → NEW: append response + duration_ms to local JSON
    → CommitScheduler syncs update
```

## Data Model

Local file: `{local_storage_path}/images/{hashed_chat_id}/{image_id}.json`
```json
{
  "id": "sha256_hex",
  "chat_id": "group_123",
  "user_id": "user_456",
  "timestamp": "2026-06-11T10:30:00Z",
  "image_base64": "data:image/jpeg;base64,/9j/4AAQ...",
  "prompt": "What is this?",
  "response": "This is a menu...",
  "analysis_mode": "standard",
  "duration_ms": 1250,
  "image_size_bytes": 245823,
  "model_used": "openai/gpt-4o"
}
```

HF Hub repo: `EvilEvan/teacherboy-images` (private dataset)
- One JSON per image, organized by hashed chat_id subdirectories
- CommitScheduler handles sync, squashes history

## Config Changes (`src/config.py`)

```python
# New fields
images_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo)
images_hf_enabled: bool = Field(default=False)

# Validator for all HF repo IDs
def _validate_evilevan_repo(cls, v: str | None) -> str | None:
    if v and not v.startswith("EvilEvan/teacherboy-"):
        raise ValueError("HF repo must be in EvilEvan/teacherboy-* namespace")
    return v

hf_memory_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo)
document_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo)
history_log_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo)
calendar_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo)
images_hf_repo_id: str | None = Field(default=None, validate=_validate_evilevan_repo)
```

## Implementation Tasks

1. **Config** — Add `images_hf_repo_id`, `images_hf_enabled`, validators
2. **ImageAnalyzerSessionManager** — Add `_hf_enabled`, `_setup_hf_storage()`, `_save_image_metadata()`
3. **ImageAnalyzerAgent** — Call save after vision response
4. **main.py** — Initialize image HF storage in lifespan
5. **Tests** — Unit tests for new persistence logic

## Error Handling
- HF init failures → log warning, fall back to local-only
- Sync failures → CommitScheduler retries; local files persist
- Image size limit (10MB) already enforced in `_download_image`

## Testing Strategy
- Mock `huggingface_hub` CommitScheduler
- Test local file write + read round-trip
- Test HF sync trigger (5 min interval)
- Test validator rejects non-EvilEvan repo names