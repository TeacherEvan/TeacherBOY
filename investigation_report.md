# Investigation Report - TeacherBOY (Ms. Green) Bot

**Date:** 2026-06-13
**Phase:** 3 - INVESTIGATE (Root Cause & Reproduction)

---

## Issue 1: ModMode Missing from Help System
**Severity:** CRITICAL
**File:** `src/agents/help_agent.py` 
**Lines:** 89-278 (`_get_command_categories`), 392-400 (`section_order`)

### Reproduction
```python
# Test: help_agent._resolve_help_topic("modmode", categories)
# Returns: "Moderator Mode" (via _topic_aliases)
# But categories.get("Moderator Mode") returns None
# Result: Empty help or fallback
```

### Root Cause
1. `_topic_aliases()` (lines 364-366) maps `"modmode"`, `"mod mode"`, `"moderator"` → `"Moderator Mode"`
2. `_get_command_categories()` (lines 89-278) defines categories but **no "Moderator Mode" entry**
3. `section_order` (lines 392-400) lists display order but **excludes "Moderator Mode"**
4. `_get_supported_sections()` filters by `section in categories` → "Moderator Mode" filtered out

### Fix Design
**Change:** Add "Moderator Mode" category in `_get_command_categories()`
```python
# After "Document Memory" category (around line 234)
"Moderator Mode": [
    {
        "command": "/modmode",
        "description": "Open moderator dashboard",
        "examples": ["/modmode"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode all",
        "description": "Activate mod mode: monitor all users for harmful content",
        "examples": ["/modmode all"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode special @user",
        "description": "Activate special mode: only admin + mentioned user can speak",
        "examples": ["/modmode special @user"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode off",
        "description": "Deactivate moderator mode",
        "examples": ["/modmode off"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode dashboard",
        "description": "Show moderator dashboard (Flex UI)",
        "examples": ["/modmode dashboard"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode kick",
        "description": "Kick user from group",
        "examples": ["/modmode kick @user"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode warn",
        "description": "Warn user (3 strikes = auto-ban)",
        "examples": ["/modmode warn @user reason"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode ban",
        "description": "Ban user from group",
        "examples": ["/modmode ban @user reason"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode unban",
        "description": "Remove user from ban list",
        "examples": ["/modmode unban @user"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode banlist",
        "description": "Show ban list",
        "examples": ["/modmode banlist"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
    {
        "command": "/modmode warnlist",
        "description": "Show warning list",
        "examples": ["/modmode warnlist"],
        "available": is_admin and chat_type in ["group chat", "room chat"],
    },
],
```

**Add to `section_order` (line 392-400):**
```python
section_order = [
    "Core Commands",
    "Translation",
    "AI & Search",
    "News & Information",
    "Calendar & Reminders",
    "Image Analysis",
    "Moderator Mode",      # ADD HERE
    "Admin Commands",
]
```

**Tests to add:** `tests/test_help_agent.py::test_help_modmode_category` and `test_help_modmode_topic_resolution`

**Migration needed:** No (additive only)

---

## Issue 2: Image HF Persistence Default Disabled
**Severity:** CRITICAL
**File:** `src/config.py`
**Line:** 646

### Reproduction
```bash
# Set IMAGES_HF_REPO_ID=EvilEvan/teacherboy-images
# Do NOT set IMAGES_HF_ENABLED
# Start bot
# Check logs: "🖼️ Image analysis HF persistence disabled"
# Images never sync to HF Hub
```

### Root Cause
```python
# config.py line 646
images_hf_enabled: bool = Field(
    default=False,  # Hardcoded False
    description="Enable image analysis persistence to HF Hub."
)

# main.py lines 274-279
if settings.images_hf_enabled and settings.images_hf_repo_id:
    # Only runs if BOTH are truthy
```

The validation at line 832 requires `evilevan/teacherboy-*` namespace, so `images_hf_repo_id` IS validated. But `images_hf_enabled` defaults to `False` independently.

### Fix Design
**Option A (Change Default):** Change `default=False` to `default=True` with validator that checks repo_id
**Option B (Computed Property):** Add property `is_images_hf_configured()` that returns `images_hf_enabled and images_hf_repo_id`
**Option C (Auto-enable):** In validator for `images_hf_repo_id`, auto-set `images_hf_enabled = True`

**Recommended: Option A with validator**
```python
# config.py - Change line 646
images_hf_enabled: bool = Field(
    default=True,  # Enable by default when repo configured
    description="Enable image analysis persistence to HF Hub."
)

# Add validator (after line 834)
@field_validator("images_hf_enabled", mode="before")
@classmethod
def auto_enable_images_hf(cls, v: Any, info: Any) -> Any:
    """Auto-enable images HF if repo_id is configured."""
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes", "on")
    # Check if repo_id is set in data
    repo_id = info.data.get("images_hf_repo_id") if hasattr(info, "data") else None
    return bool(repo_id and repo_id.strip())
```

**Alternative simpler fix (main.py line 274):**
```python
# Change condition from:
if settings.images_hf_enabled and settings.images_hf_repo_id:
# To:
if settings.images_hf_repo_id:  # Repo configured = enable persistence
```

**Tests to add:** Verify HF persistence initializes when only `IMAGES_HF_REPO_ID` set

**Migration needed:** No (behavior change: persistence now ON by default with repo)

---

## Issue 3: Image "Last" Option Not Persisted
**Severity:** HIGH
**File:** `src/services/image_analyzer_session_manager.py`
**Lines:** 95-96, 264-270, 307-313

### Reproduction
```python
# 1. User sends image, gets analyzed
# 2. Bot restarts (or session manager recreated)
# 3. User sends "analyze last" 
# 4. get_last_image() returns None
# 5. Bot says "no previous image found"
```

### Root Cause
```python
# Line 95-96: In-memory only
self._last_images: dict[str, str] = {}
self._last_images_timestamps: dict[str, datetime] = {}

# Line 264-270: Updated but NOT persisted
async with self._last_images_lock:
    self._last_images[chat_id] = image_data
    self._last_images_timestamps[chat_id] = datetime.now(UTC)

# Line 307-313: Reads from memory only
async def get_last_image(self, chat_id: str) -> str | None:
    async with self._sessions_lock:  # Wrong lock! Should be _last_images_lock
        session = self._sessions.get(chat_id)
        if not session:
            return None
        return session.last_image_data
```

**Additional Bug:** `get_last_image()` uses `_sessions_lock` but reads `_sessions[chat_id].last_image_data`, NOT `_last_images[chat_id]`. The session may be expired while `_last_images` still has the data.

### Fix Design
**Changes:**
1. Add local persistence for `_last_images` in `store_image()` and `_purge_oldest_last_images()`
2. Add `_load_last_images()` called in `__init__`
3. Fix `get_last_image()` to use `_last_images` with correct lock
4. Include in HF sync folder

```python
# Add to __init__ (after line 114)
self._last_images_path = self._images_local_path / "_last_images_index.json"
self._load_last_images()

# New method
def _load_last_images(self) -> None:
    if self._last_images_path.exists():
        try:
            data = json.loads(self._last_images_path.read_text(encoding="utf-8"))
            for chat_id, entry in data.items():
                self._last_images[chat_id] = entry["image_data"]
                self._last_images_timestamps[chat_id] = datetime.fromisoformat(entry["timestamp"])
            logger.info(f"🖼️ Loaded {len(self._last_images)} last images from local storage")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load last images index: {e}")

async def _save_last_images_index(self) -> None:
    try:
        data = {
            chat_id: {
                "image_data": img_data,
                "timestamp": ts.isoformat()
            }
            for chat_id, img_data in self._last_images.items()
            for ts in [self._last_images_timestamps[chat_id]]
        }
        temp_path = self._last_images_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        temp_path.rename(self._last_images_path)
    except Exception as e:
        logger.error(f"❌ Failed to save last images index: {e}")

# Modify store_image() - after line 270:
await self._save_last_images_index()

# Modify get_last_image() - line 307-313:
async def get_last_image(self, chat_id: str) -> str | None:
    async with self._last_images_lock:  # FIX: Use correct lock
        return self._last_images.get(chat_id)

# Modify _purge_oldest_last_images() - after line 440:
await self._save_last_images_index()
```

**Tests to add:** `tests/services/test_image_analyzer_session_manager.py::test_last_image_persistence_across_restart`

**Migration needed:** No (additive persistence layer)

---

## Issue 4: Incomplete Vision Provider Check
**Severity:** HIGH
**File:** `src/agents/image_analyzer_agent.py`
**Line:** 325

### Reproduction
```python
# Configure only: GEMINI_API_KEY, HF_INFERENCE_API_KEY
# Do NOT configure: HERMES, OPENROUTER, GITHUB_MODELS
# Send image to bot
# should_handle() returns False (line 325 check fails)
# Image analysis never triggers
```

### Root Cause
```python
# Line 325
if not (hermes_service.is_configured() or openrouter_service.is_configured() or github_models_service.is_configured()):
    return False

# But gemini_service and hf_inference_service also support vision!
# settings.get_fallback_llm_providers() returns: github, openrouter, hermes, gemini
```

### Fix Design
**Change line 325 to use settings method or check all vision providers:**
```python
# Option 1: Use settings method (recommended)
from src.config import settings
vision_providers = [
    hermes_service.is_configured(),
    openrouter_service.is_configured(),
    github_models_service.is_configured(),
    gemini_service.is_configured(),
    hf_inference_service.is_configured(),
]
if not any(vision_providers):
    return False

# Option 2: Check settings fallback providers (more maintainable)
if not settings.get_fallback_llm_providers():
    return False
# But need to check which support vision... 

# Option 3: Check each service's vision capability explicitly
vision_configured = (
    hermes_service.is_configured() or
    openrouter_service.is_configured() or
    github_models_service.is_configured() or
    gemini_service.is_configured() or
    hf_inference_service.is_configured()
)
if not vision_configured:
    return False
```

**Recommended: Option 3** (explicit, clear, matches provider capabilities)

**Tests to add:** `tests/test_image_analyzer_agent.py::test_should_handle_with_gemini_only` and `test_should_handle_with_hf_inference_only`

**Migration needed:** No (fixes false negative)

---

## Issue 5: Private Attribute Access in Main.py
**Severity:** MEDIUM
**File:** `src/main.py`
**Lines:** 274-281

### Root Cause
```python
# Direct access to private attributes
image_analyzer_session_manager._images_hf_token = settings.hf_memory_token
image_analyzer_session_manager._images_hf_repo_id = settings.images_hf_repo_id
image_analyzer_session_manager._setup_images_hf_storage()
```

### Fix Design
**Add public configure method to `ImageAnalyzerSessionManager`:**
```python
# In image_analyzer_session_manager.py (after line 114)
def configure_hf_storage(self, token: str, repo_id: str) -> None:
    """Configure HF storage after initialization."""
    self._images_hf_token = token
    self._images_hf_repo_id = repo_id
    if not self._images_hf_enabled:
        self._setup_images_hf_storage()

# In main.py (line 274-281):
if settings.images_hf_repo_id:  # Simplified condition
    image_analyzer_session_manager.configure_hf_storage(
        settings.hf_memory_token,
        settings.images_hf_repo_id
    )
    logger.info(f"🖼️ Image analysis HF persistence enabled: {settings.images_hf_repo_id}")
```

**Tests to add:** Verify `configure_hf_storage()` works when called after init

**Migration needed:** No (refactor only)

---

## Issue 6: Missing Images Sync in HF Sync Script
**Severity:** LOW
**File:** `scripts/hf_sync.py`

### Fix Design
**Add `--images` argument and logic (after line 234):**
```python
parser.add_argument(
    "--images",
    action="store_true",
    help="Sync image analysis folder (data/images).",
)
parser.add_argument(
    "--images-repo",
    type=str,
    default=None,
    help="HF dataset repo id for images (e.g. 'username/teacherboy-images'). Defaults to IMAGES_HF_REPO_ID env var.",
)

# In main():
do_images = args.images
...
if do_images:
    repo_id = (args.images_repo or os.getenv("IMAGES_HF_REPO_ID") or "").strip()
    if not repo_id:
        print("⚠️  Skipping images sync: No IMAGES_HF_REPO_ID provided")
    else:
        folder = root / "data" / "images"
        _ensure_folder(folder)
        _ensure_nonempty(folder, marker_name=".hf_sync_marker.txt")
        _sync_folder(
            token=token,
            repo_id=repo_id,
            local_folder=folder,
            commit_message=f"Sync images ({datetime.now(UTC).date().isoformat()})",
        )
        print(f"✅ Synced images to hf://datasets/{repo_id}")
```

**Also add to default sync (line 170-174):**
```python
if not do_memory and not do_logs and not do_calendar and not do_documents and not do_images:
    do_memory = True
    do_logs = True
    do_calendar = True
    do_documents = True
    do_images = True  # ADD
```

**Tests to add:** Manual verification only (script)

**Migration needed:** No (new feature)

---

## Issue 7: CommitScheduler Reliability (Cross-Cutting)
**Severity:** MEDIUM
**File:** `src/services/hf_storage_mixin.py`

### Root Cause
1. `squash_history=True` - rewrites history, loses audit trail
2. No verification commits succeed
3. No health check endpoint
4. Network failures not retried explicitly (CommitScheduler handles some)

### Fix Design
**Option 1 (Quick):** Change `squash_history=False` for audit trail, add health check
**Option 2 (Comprehensive):** Wrap CommitScheduler with retry/verification

**Recommended: Option 1 first, then Option 2 if issues persist**
```python
# In HFStorageMixin._setup_hf_storage() line 101:
squash_history=False,  # Changed from True
```

**Add health check method:**
```python
def check_hf_sync_health(self) -> dict[str, Any]:
    """Verify HF sync is working."""
    return {
        "enabled": self._hf_enabled,
        "repo_id": self.hf_repo_id,
        "local_folder_exists": self._hf_sync_folder.exists() if self._hf_sync_folder else False,
        "pending_files": len(list(self._hf_sync_folder.glob("*.json"))) if self._hf_sync_folder else 0,
        "scheduler_running": self._commit_scheduler is not None,
    }
```

**Tests to add:** Integration test with real HF token (manual/CI)

**Migration needed:** `squash_history=False` changes commit history style (additive commits instead of squashed)

---

## Summary: Fix Priority & Effort

| Issue | Priority | Effort | Risk |
|-------|----------|--------|------|
| 1. Help ModMode Category | CRITICAL | Low (50 lines) | None |
| 2. Image HF Default Enabled | CRITICAL | Low (config + main) | Low |
| 3. Last Image Persistence | HIGH | Medium (session manager) | Low |
| 4. Vision Provider Check | HIGH | Low (5 lines) | None |
| 5. Public HF Configure API | MEDIUM | Low (refactor) | None |
| 6. HF Sync Script Images | LOW | Low (script) | None |
| 7. CommitScheduler squash | MEDIUM | Low (1 line) | Medium (history style) |

---

## Gate Decision

**All HIGH/CRITICAL issues investigated. Fix designs approved.**

**Ready for Phase 4: FIX (Implementation & Validation)**

Shall I implement fixes in priority order?