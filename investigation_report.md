# Investigation Report: Admin Bootstrap Denial After Claim

**Date:** 2026-06-17
**Issue:** User runs `/admin claim <key>`, succeeds, removes ADMIN_SETUP_KEY, then denied admin status

---

## Issue Summary

**Severity:** HIGH (user-facing admin access failure)
**File:** `src/agents/admin_agent.py`, `src/services/privilege_service.py`, `src/main.py`

### User Report
> "I have run the admin claim setup with my User id (stored in env file as well as in hf secrets) as I continued as instructed and asked me to delete the bootstrap, it continues to deny me active admin status."

---

## Reproduction

### Scenario 1: Restart After Secret Change (Most Likely)
**Steps:**
1. User sets `ADMIN_SETUP_KEY` in HF Spaces secrets
2. User runs `/admin claim <key>` → succeeds, gets in-memory admin
3. User sets `ADMIN_USER_IDS` in HF Spaces secrets (or thinks they did)
4. User removes `ADMIN_SETUP_KEY` from HF Spaces secrets
5. HF Spaces restarts container (secret change triggers restart)
6. In-memory claim lost, `ADMIN_USER_IDS` not properly set → no admin access

**Test Script:** `scripts/repro_restart_after_claim.py`
```python
# Simulates: claim works, restart happens, ADMIN_USER_IDS missing
# Result: privilege_service.is_admin() returns False
```

### Scenario 2: Silent Settings Load Failure (Possible)
**Steps:**
1. `ADMIN_USER_IDS` set in env
2. Container starts
3. `privilege_service._ensure_settings_loaded()` fails silently (import error, pydantic error)
4. Falls back to empty `_env_admin_user_ids`
5. `privilege_service.is_admin()` returns False for env admins
6. AdminAgent._is_admin() still works (uses captured `_admin_user_ids`)
7. User can run `/admin` commands but fails rate limits/mod mode/news access in other agents

**Test Script:** `scripts/repro_silent_settings_failure.py`
```python
# Simulates: _ensure_settings_loaded() catches exception
# Result: AdminAgent works, other agents deny admin
```

---

## Root Cause Analysis

### Primary Root Cause: Dual Admin Check System with Divergent Data Sources

The system has **two independent admin verification paths** that can diverge:

| Check | Data Source | Used By |
|-------|-------------|---------|
| `AdminAgent._is_admin()` | `self._admin_user_ids` (init snapshot) + `privilege_service._claimed_admin_user_ids` | AdminAgent only (should_handle, command execution) |
| `privilege_service.is_admin()` | `_claimed_admin_user_ids` + `_env_admin_user_ids` (lazy from settings) | 15+ other agents (translation, mod mode, news, help, etc.) |

**Divergence triggers:**
1. **Process restart** - In-memory claim lost, `_env_admin_user_ids` depends on settings
2. **Settings load failure** - `_ensure_settings_loaded()` catches exception → empty list
3. **Module reload** - Captured `_admin_user_ids` stale, lazy load gets new settings

### Secondary Root Cause: Bootstrap Claim Not Persisted

The `/admin claim` flow:
1. Adds user to `AdminAgent._admin_user_ids` (list)
2. Adds user to `privilege_service._claimed_admin_user_ids` (set)
3. Sets `AdminAgent._claimed_admin_user_id` (single string)

**All in-memory only.** On container restart (HF Spaces), all lost. User MUST set `ADMIN_USER_IDS` in secrets before removing `ADMIN_SETUP_KEY` and restarting.

### Tertiary Root Cause: Silent Failure Masking

`privilege_service._ensure_settings_loaded()`:
```python
except Exception as e:
    logger.warning(f"⚠️ Failed to load privilege settings: {e}")
    self._env_admin_user_ids = []
```

Any exception (circular import, pydantic validation, attribute error) → empty admin list → silent admin denial in 15+ agents. Only WARNING log, no alert.

---

## Fix Design

### Fix 1: Unify Admin Check to Single Source (CRITICAL)
**Change:** Make `AdminAgent._is_admin()` delegate to `privilege_service.is_admin()`
**Files:** `src/agents/admin_agent.py:126-131`
**Lines to modify:**
```python
# REMOVE lines 126-131 (current _is_admin)
# REPLACE with:
def _is_admin(self, user_id: str | None) -> bool:
    return privilege_service.is_admin(user_id)
```
**Why:** Single source of truth. AdminAgent was created before privilege_service; privilege_service is now the central authority.

**Tests to add:**
- `test_admin_agent_uses_privilege_service_for_auth`
- `test_admin_check_consistent_across_agents`

### Fix 2: Remove Silent Failure in privilege_service (CRITICAL)
**Change:** Fail fast on settings load error; initialize at startup
**Files:** `src/services/privilege_service.py:43-56`, `src/main.py`
**Lines to modify:**
```python
# In privilege_service.py - REMOVE try/except, let exception propagate
def _ensure_settings_loaded(self) -> None:
    if self._settings_loaded: return
    from src.config import settings
    self._env_admin_user_ids = settings.get_admin_user_ids()
    self._env_moderator_user_ids = settings.get_moderator_user_ids()
    self._settings_loaded = True

# In main.py lifespan - ADD explicit initialization
@asynccontextmanager
async def lifespan(app: FastAPI):
    privilege_service._ensure_settings_loaded()  # Fail fast at startup
    # ... rest of lifespan
```
**Why:** Catch misconfiguration at startup, not silently at first request.

**Tests to add:**
- `test_privilege_service_fails_fast_on_bad_settings`
- `test_privilege_service_initialized_at_startup`

### Fix 3: Add Startup Validation for ADMIN_USER_IDS Format (MEDIUM)
**Change:** Validate format at startup, warn on suspicious patterns
**Files:** `src/config.py` or `src/main.py`
**Add to Settings or main.py:**
```python
def _validate_admin_user_ids_format(self) -> None:
    if self.admin_user_ids:
        # Check for common mistakes
        if self.admin_user_ids.startswith("[") or self.admin_user_ids.startswith("{"):
            logger.warning("⚠️ ADMIN_USER_IDS appears to be JSON array, expected comma-separated")
        if '"' in self.admin_user_ids or "'" in self.admin_user_ids:
            logger.warning("⚠️ ADMIN_USER_IDS contains quotes, expected bare IDs")
```
**Why:** Prevents user errors like `ADMIN_USER_IDS="['U123']"` or `ADMIN_USER_IDS=" U123 "`.

### Fix 4: Document Bootstrap Limitation Clearly (MEDIUM)
**Change:** Update docs and claim response to emphasize ADMIN_USER_IDS requirement
**Files:** `docs/ADMIN_COMMANDS.md`, `src/agents/admin_agent.py:379-387`
**Lines to modify in claim response:**
```python
return (
    "✅ Admin claim successful (for THIS RUNNING INSTANCE ONLY).\n\n"
    f"Your LINE user ID: {user_id}\n"
    f"This chat ID: {chat_id}\n\n"
    "⚠️  THIS WILL BE LOST ON RESTART.\n\n"
    "To make it PERMANENT:\n"
    f"1. Set ADMIN_USER_IDS={user_id} in your HOST ENVIRONMENT/SECRETS\n"
    f"2. Restart the service\n"
    f"3. REMOVE ADMIN_SETUP_KEY afterwards\n\n"
    "On HF Spaces: Set ADMIN_USER_IDS in Space Settings → Secrets BEFORE removing ADMIN_SETUP_KEY."
)
```
**Why:** User's issue stems from not understanding claim is ephemeral.

### Fix 5: Consistent Claim Tracking (LOW)
**Change:** Remove `AdminAgent._claimed_admin_user_id`, use only `privilege_service._claimed_admin_user_ids`
**Files:** `src/agents/admin_agent.py:81, 367-371, 376`
**Lines to modify:**
```python
# REMOVE: self._claimed_admin_user_id: str | None = None (line 81)
# REMOVE: if self._claimed_admin_user_id and self._claimed_admin_user_id != user_id: (367-371)
# CHANGE: self._claimed_admin_user_id = user_id (376) → just rely on privilege_service
```
**Why:** Single source for claimed admins. AdminAgent check uses privilege_service anyway after Fix 1.

---

## Migration Needed

**Yes - Breaking change for AdminAgent internal state.**
- `AdminAgent._admin_user_ids` removed (replaced by privilege_service)
- `AdminAgent._claimed_admin_user_id` removed
- `AdminAgent._is_admin()` now delegates to privilege_service

**Impact:** Low - Only affects AdminAgent internals. External behavior unchanged (should be MORE consistent).

**Rollback:** Revert AdminAgent changes if issues.

---

## Verification Plan

1. **Unit tests:** All existing admin tests pass
2. **Integration test:** Full admin flow - claim → restart simulation → verify admin persists
3. **Cross-agent test:** Verify admin status consistent across AdminAgent, TranslationAgent, ModModeAgent, etc.
4. **HF Spaces simulation:** Set ADMIN_USER_IDS in env, restart process, verify admin works
5. **Error injection:** Corrupt settings, verify fail-fast at startup