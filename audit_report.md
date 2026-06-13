# Audit Report - TeacherBOY (Ms. Green) Bot

**Date:** 2026-06-13
**Scope:** Full codebase audit focusing on reported issues:
1. Image analysis not working
2. Images not being stored
3. Chats not being stored
4. ModMode not present on help feature
5. HuggingFace not synced

---

## 1. File Inventory

### Python Files (src/)
| File | Lines | Purpose |
|------|-------|---------|
| src/agents/image_analyzer_agent.py | 1,589 | General image Q&A agent |
| src/agents/help_agent.py | 771 | Help system with Flex UI |
| src/agents/mod_mode_agent.py | 303 | Moderator mode agent (priority 4) |
| src/services/image_analyzer_session_manager.py | 547 | Session management for image analysis |
| src/services/conversation_memory_service.py | 657 | Chat history with HF persistence |
| src/services/document_memory_service.py | 631 | PDF/DOCX storage with HF persistence |
| src/services/hf_storage_mixin.py | 254 | Shared HF Hub persistence logic |
| src/config.py | 1,104 | Pydantic Settings configuration |
| src/main.py | 1,297 | FastAPI app + lifespan initialization |

### TypeScript Files (convex/)
| File | Lines | Purpose |
|------|-------|---------|
| convex/modModeState.ts | ~100 | Mod mode state per group |
| convex/banList.ts | ~100 | Ban list per group |
| convex/userWarnings.ts | ~100 | 3-strike warnings per group |

### Test Summary
- **Total tests:** 838 (837 passed, 1 skipped)
- **Lint:** ruff check passed (0 errors)

---

## 2. Dependency Graph (Key Services)

```
main.py (lifespan)
├── conversation_memory_service (HFStorageMixin + CommitScheduler)
├── document_memory_service (HFStorageMixin + CommitScheduler)
├── history_log_service (HFStorageMixin + CommitScheduler)
├── image_analyzer_session_manager (Custom HF persistence)
├── mod_mode_service (Convex)
├── ban_list_service (Convex)
├── warning_service (Convex)
├── calendar_service (HF sync)
└── AgentRouter
    ├── HelpAgent (priority 5)
    ├── AdminAgent (priority 5)
    ├── ModModeAgent (priority 4)
    ├── ImageAnalyzerAgent (priority 7)
    └── ... other agents
```

---

## 3. Issues Found (Phase 1 Audit)

### Issue 1: ModMode Missing from Help System ⚠️ **HIGH**
**Location:** `src/agents/help_agent.py` (lines 89-278, 392-400)

**Finding:**
- `_topic_aliases()` maps `"modmode"`, `"mod mode"`, `"moderator"` → `"Moderator Mode"` (lines 364-366)
- `_get_command_categories()` does NOT define a `"Moderator Mode"` category
- `section_order` (line 392-400) does NOT include `"Moderator Mode"`
- Result: Help topic resolves to "Moderator Mode" but no commands are displayed

**Root Cause:** Feature added to topic aliases but category implementation missing.

---

### Issue 2: Image Analysis HF Persistence Disabled by Default ⚠️ **HIGH**
**Location:** `src/config.py` (line 646), `src/main.py` (lines 274-279)

**Finding:**
- `images_hf_enabled: bool = Field(default=False, ...)` (config.py:646)
- `main.py` only initializes image HF storage if `settings.images_hf_enabled AND settings.images_hf_repo_id`
- Default `False` means images NEVER sync to HF Hub unless explicitly enabled

**Related:** `ImageAnalyzerSessionManager` has custom HF persistence (not using `HFStorageMixin`):
- `_setup_images_hf_storage()` creates CommitScheduler for `./data/images`
- `save_image_metadata()` writes JSON files to local path
- But CommitScheduler only starts if HF token/repo_id are set at init OR `main.py` sets them later

**Root Cause:** Configuration default is `False`; separate persistence implementation not integrated with main HF storage pattern.

---

### Issue 3: Conversation Memory HF Sync May Not Commit ⚠️ **MEDIUM**
**Location:** `src/services/conversation_memory_service.py`, `src/services/hf_storage_mixin.py`

**Finding:**
- `ConversationMemoryService` extends `HFStorageMixin`
- `_save_to_local_storage()` writes to local folder for CommitScheduler
- `CommitScheduler` commits every 5 minutes (`hf_sync_interval`)
- **Potential Issue:** `squash_history=True` (line 127) + `path_in_repo="conversations"` may cause conflicts
- No verification that CommitScheduler is actually running/committing in tests

**Evidence:** Tests mock external APIs; no integration test verifies HF commits.

---

### Issue 4: Image Analysis Session Manager - Image Storage ⚠️ **MEDIUM**
**Location:** `src/services/image_analyzer_session_manager.py`

**Finding:**
- `store_image()` saves to in-memory `_last_images` dict only (TTL: 1 hour)
- `save_image_metadata()` saves full analysis to `./data/images/` for HF sync
- **But:** `_last_images` (recent images for "Last" option) NOT persisted to HF
- If bot restarts, "Last analyzed image" feature loses data
- `_last_images` only in memory, no local/HF persistence

---

### Issue 5: HuggingFace Sync Script Missing Image Folder ⚠️ **LOW**
**Location:** `scripts/hf_sync.py`

**Finding:**
- Script syncs: conversations, logs, calendar, documents
- **Missing:** `--images` flag for `data/images` folder
- Users cannot force-sync image analysis history manually

---

### Issue 6: Image Analyzer Agent - Vision Provider Check ⚠️ **LOW**
**Location:** `src/agents/image_analyzer_agent.py` (line 325)

**Finding:**
```python
if not (hermes_service.is_configured() or openrouter_service.is_configured() or github_models_service.is_configured()):
    return False
```
- Does NOT check `gemini_service.is_configured()` or `hf_inference_service.is_configured()`
- If only Gemini/HF Inference configured, image analysis won't trigger
- Other agents use `settings.get_fallback_llm_providers()` which includes all providers

---

## 4. Test Coverage Gaps

| Area | Tests | Missing |
|------|-------|---------|
| Image Analyzer HF persistence | 0 | No test for `save_image_metadata` + HF sync |
| Conversation Memory HF commit | 0 | No integration test for CommitScheduler |
| Help Agent ModMode category | 0 | No test for "help modmode" |
| ModModeAgent dashboard | Partial | Dashboard builder tested, but not full flow |
| Image "Last" option persistence | 0 | In-memory only, no restart test |

---

## 5. TODOs/FIXMEs Found

```bash
# From codebase search:
src/config.py:96  # TODO: translation_cache_ttl_seconds
src/config.py:138 # DEPRECATED: NewsAPI.org key
```

---

## 6. Gate Decision

**DO NOT PROCEED to Phase 2 until user confirms scope.**

**Critical Issues to Fix (Priority Order):**
1. **ModMode Help Category** - Add "Moderator Mode" category to HelpAgent
2. **Image HF Persistence** - Enable by default or fix configuration; unify with HFStorageMixin
3. **Conversation Memory HF Verification** - Add integration test or verify CommitScheduler works
4. **Image "Last" Option Persistence** - Persist `_last_images` to local/HF
5. **HF Sync Script** - Add `--images` flag
6. **Vision Provider Check** - Include all vision-capable providers

---

## 7. Recommended Fixes Summary

| Issue | Fix Approach |
|-------|--------------|
| ModMode Help | Add category in `_get_command_categories()` with `/modmode` commands; add to `section_order` |
| Image HF Enable | Change `images_hf_enabled` default to `True` if repo_id set; or unify with HFStorageMixin |
| Image Last Persist | Save `_last_images` to local JSON; load on startup; include in HF sync |
| Conversation HF | Verify CommitScheduler commits; add health check endpoint |
| HF Sync Script | Add `--images` argument and logic |
| Vision Providers | Use `settings.get_fallback_llm_providers()` or check all vision providers |

---

*End of Audit Report*