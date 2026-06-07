# Ms. Green Feature Toggles — Design Document

**Date:** 2026-06-08  
**Feature:** `/admin features` — Interactive agent enable/disable panel  
**Branch:** `feature/ms-green-features`

---

## 1. Architecture Overview

### Approach: Extend AdminAgent (Approach 1)

Add `/admin features` command to existing `AdminAgent` (`src/agents/admin_agent.py`). Reuse:
- Admin privilege checks (`_is_admin()`)
- Confirmation flow patterns
- Flex Message builder utilities
- Postback handling (`handle_postback`)

### New Service: `FeatureFlagsService` (`src/services/feature_flags_service.py`)

Singleton service managing toggle state:
- In-memory cache: `Dict[str, bool]` (agent_name → enabled)
- Async persistence to HuggingFace Hub (JSON file in repo)
- API: `get_flag(name)`, `set_flag(name, value)`, `get_all_flags()`, `reload()`

### Integration Point: `AgentFactory` (`src/agents/agent_factory.py`)

Modify lazy-loading `__import_*_agent()` functions:
```python
async def __import_translation_agent():
    if not await feature_flags.get_flag("translation"):
        return None
    # ... existing import logic
```

Disabled agents return `None` → skipped by `AgentRouter`.

---

## 2. Components & Responsibilities

| Component | Responsibility |
|-----------|----------------|
| `FeatureFlagsService` | Load/save flags from HF Hub; in-memory cache; thread-safe access |
| `AdminAgent._handle_features_command()` | Build Flex Message panel; list toggleable agents with 🟢/🔴 buttons |
| `AdminAgent.handle_postback()` | Handle `admin:feature:toggle:<name>` actions; call `set_flag()` |
| `AgentFactory` | Check flag before instantiating each agent; return `None` if disabled |
| `AgentRouter` | Unchanged — receives filtered agent list from Factory |

### Toggleable Agents (v1)

Configurable list in `config.py` → `TOGGLABLE_AGENTS = ["translation", "calendar", "news", "special_news", "llm", "search", "profiler", "image_analyzer"]`

Excluded: `help`, `admin` (core), `hannibal_profile` (depends on profiler).

---

## 3. Data Flow

### 1. Startup / Initialization

```
Bot starts
  → FeatureFlagsService.__init__()
    → Async load from HF Hub (hf_hub_download or hf_hub_upload metadata)
    → If success: populate cache
    → If fail: log warning, default all=True
  → Application ready
```

### 2. First Message After Startup

```
Message arrives
  → AgentRouter.route_message()
  → AgentFactory.get_all_agents() triggers lazy instantiation
  → Each __import_*_agent() calls FeatureFlagsService.get_flag(agent_name)
  → flag=True → returns agent instance; flag=False → returns None (skipped)
  → Router tries enabled agents in priority order
```

### 3. Admin Toggles Feature

```
Admin sends "/admin features"
  → AdminAgent._handle_features_command() fetches all flags
  → Builds Flex Message with buttons (action data: "admin:feature:toggle:<name>")
  → Admin taps 🟢/🔴 button
  → LINE sends postback to webhook
  → AdminAgent handles postback, calls FeatureFlagsService.set_flag(name, new_state)
  → FeatureFlagsService updates in-memory cache + async persist to HF Hub
  → Next message: AgentFactory re-instantiates (lazy), picks up new flag
```

---

## 4. Error Handling

| Scenario | Handling |
|----------|----------|
| HF Hub unavailable at startup | Log warning, start with in-memory defaults (all ON); queue sync for later |
| HF sync fails on toggle | Retry 3× with exponential backoff; keep local state; log error |
| Admin toggles unknown agent | Ignore; return "Unknown feature" in Flex Message |
| AgentFactory import fails | Log error, skip agent, continue with others (existing behavior) |
| Concurrent toggles | In-memory dict is thread-safe for reads; writes serialized via asyncio.Lock |

---

## 5. Testing Strategy

### Unit Tests (`tests/services/test_feature_flags_service.py`)

- Flags load from HF on init
- Flags persist to HF on change
- In-memory cache returns correct values
- Default all-ON when HF unavailable

### Integration Tests (`tests/agents/test_admin_features.py`)

- `/admin features` shows correct panel
- Button postback toggles flag
- Next message respects new flag (agent disabled/enabled)

### E2E Test (manual)

- Start bot, verify translation works
- Admin disables translation via panel
- Send Thai text → no translation response
- Admin re-enables → translation works again

---

## Implementation Plan Reference

See `docs/plans/2026-06-08-ms-green-features-implementation.md` (to be created in writing-plans phase).
