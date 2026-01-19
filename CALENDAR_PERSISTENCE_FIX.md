# Calendar Persistence Fix - HF Spaces Compatibility

**Date:** 2026-01-10  
**Severity:** CRITICAL - Data loss on restart  
**Status:** FIXED ✅

## Problem Summary

Calendar events were being **erased on every restart** when running on Hugging Face Spaces, causing data loss.

## Root Causes Identified

### 1. **Async Loading Race Condition** ❌
**File:** `src/services/calendar_service.py:278`

```python
# BEFORE (BROKEN):
asyncio.create_task(self._load_from_hub())  # Async task may not complete before events added
```

- Used `asyncio.create_task()` during `__init__` (sync context)
- Task may fail silently if event loop not running
- HF Hub download happened **asynchronously** after startup completed
- Users could add events **before** HF data loaded, causing overwrites

### 2. **Double Load in configure()** ❌
**File:** `src/services/calendar_service.py:751`

```python
# BEFORE (BROKEN):
if storage_path:
    self.local_storage_path = Path(storage_path)
    self.local_storage_path.mkdir(parents=True, exist_ok=True)
    self._load_from_local_storage()  # ← Reloads from EMPTY filesystem on HF Spaces!
```

- Called `_load_from_local_storage()` in `configure()` method
- On HF Spaces, filesystem is **ephemeral** - deleted on restart
- File doesn't exist → returns with "starting fresh" → **data lost**
- Even if HF Hub configured, local load happened **before** HF download

### 3. **No Event Clearing Before Load** ⚠️
**File:** `src/services/calendar_service.py:310-314`

```python
# BEFORE (POTENTIAL DUPLICATES):
events_data = data.get("events", [])
for event_dict in events_data:
    event = CalendarEvent.from_dict(event_dict)
    self._events[event.event_id] = event  # ← Appends to existing dict
```

- Didn't clear `self._events` before loading from HF Hub
- Could cause duplicate events if method called multiple times

## The Fix

### 1. Synchronous HF Hub Loading ✅

**Added:** `_load_from_hub_sync()` method (line 289-326)

```python
def _load_from_hub_sync(self):
    """Load events from HF Hub synchronously during startup."""
    logger.info(f"📥 Downloading calendar from HF Hub: {self.hf_repo_id}")
    
    local_file = hf_hub_download(
        repo_id=self.hf_repo_id,
        filename=CALENDAR_FILENAME,
        repo_type="dataset",
        token=self.hf_token,
        local_dir=str(self.local_storage_path),
    )
    
    # Clear existing events before loading from HF Hub
    self._events.clear()
    
    # Load events...
    logger.info(f"✅ Loaded {len(self._events)} events from HF Hub")
```

**Benefits:**
- Blocks during startup until HF data fully loaded
- No race conditions
- Better error messages for debugging
- Clears events before loading (no duplicates)

### 2. Fixed configure() Logic ✅

**File:** `src/services/calendar_service.py:746-762`

```python
# Update storage path if provided
if storage_path:
    self.local_storage_path = Path(storage_path)
    self.local_storage_path.mkdir(parents=True, exist_ok=True)
    # ← Removed: self._load_from_local_storage()

# Update HF Hub configuration
if hf_token and hf_repo_id:
    self.hf_token = hf_token
    self.hf_repo_id = hf_repo_id
    self._hf_enabled = True
    self._setup_hf_storage()  # ← This calls _load_from_hub_sync()
    logger.info(f"📅 Calendar service configured with HF Hub: {hf_repo_id}")
else:
    # Only reload from local if NOT using HF Hub
    self._load_from_local_storage()  # ← Moved here (local-only mode)
    self._hf_enabled = False
    logger.info("📅 Calendar service configured (local storage only)")
```

**Benefits:**
- Doesn't reload from empty filesystem when HF Hub enabled
- HF Hub loading handled by `_setup_hf_storage()` → `_load_from_hub_sync()`
- Local loading only happens in local-only mode

### 3. Event Clearing Before Load ✅

**File:** `src/services/calendar_service.py:349` (async version)

```python
# Clear existing events before loading from HF Hub
self._events.clear()
```

Added to both sync and async versions to prevent duplicates.

## How It Works Now (HF Spaces)

### Startup Flow:
1. **Module import**: Line 803 creates singleton
   ```python
   calendar_service = CalendarService(
       local_storage_path=settings.calendar_data_path,
       encryption_key=settings.calendar_encryption_key,
   )
   ```
   - Creates empty `self._events = OrderedDict()`
   - Calls `_load_from_local_storage()` (file won't exist on HF Spaces → empty)

2. **main.py lifespan**: Line 228 calls `configure()`
   ```python
   calendar_service.configure(
       storage_path=settings.calendar_data_path,
       hf_token=settings.hf_memory_token,
       hf_repo_id=settings.calendar_hf_repo_id,
   )
   ```
   - Detects HF Hub configured
   - Calls `_setup_hf_storage()`
   - Calls `_load_from_hub_sync()` **synchronously**
   - Downloads `calendar_events.json` from HF Hub
   - Clears `self._events` and loads from HF Hub
   - **Bot is ready with full calendar data** ✅

### Save Flow:
1. User adds event → `add_event()` called
2. Event added to `self._events`
3. Calls `_save_to_local_storage()` → saves to `/app/data/calendar/calendar_events.json`
4. **CommitScheduler** auto-syncs to HF Hub every 5 minutes
5. Data persisted to cloud ✅

## Environment Variables Required (HF Spaces)

```bash
# Required for HF Hub persistence:
HF_MEMORY_TOKEN=hf_xxxxxxxxxxxxx      # HF token with 'write' scope
CALENDAR_HF_REPO_ID=username/zeus-calendar  # Your HF dataset repo

# Calendar settings:
CALENDAR_ENABLED=true
CALENDAR_DATA_PATH=/app/data/calendar  # Ephemeral (synced to HF Hub)
```

## Testing Checklist

- [x] Fix applied to `calendar_service.py`
- [ ] Test on HF Spaces with existing calendar repo
- [ ] Test on HF Spaces with new/empty repo
- [ ] Test restart with events → verify events persist
- [ ] Test local mode (no HF Hub) still works
- [ ] Check logs for "✅ Loaded X events from HF Hub"

## Files Modified

- `src/services/calendar_service.py` (3 changes):
  - Added `_load_from_hub_sync()` method
  - Updated `_setup_hf_storage()` to call sync version
  - Fixed `configure()` to not reload from empty filesystem
  - Added `self._events.clear()` in both load methods

## Migration Notes

No migration needed - fix is backward compatible:
- Existing local deployments: Still work with local storage
- HF Spaces with HF Hub: Now properly loads from cloud
- First-time HF Hub: Creates repo and syncs on first save

## Logs to Watch For

**SUCCESS (HF Hub):**
```
📥 Downloading calendar from HF Hub: username/zeus-calendar
✅ Loaded 5 events from HF Hub
📅 Calendar service configured with HF Hub: username/zeus-calendar
```

**SUCCESS (Local only):**
```
📅 Loaded 5 events from local storage
📅 Calendar service configured (local storage only)
```

**WARNING (Empty HF repo):**
```
⚠️ Could not load events from HF Hub (repo may be empty): ...
📅 Starting with empty calendar - will sync to HF Hub on first save
```

## Related Issues

- HF Spaces ephemeral filesystem
- CommitScheduler auto-sync pattern
- Race conditions in async initialization
- See: `CALENDAR_AND_MEMORY_ENHANCEMENTS.md`, `CALENDAR_DUPLICATE_PREVENTION.md`
