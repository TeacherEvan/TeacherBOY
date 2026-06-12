# Implementation Plan: Admin-Only Features

## Overview
Restrict NewsAgent, CalendarAgent, ImageAnalyzerAgent, ProfilerAgent to privileged users (admins + moderators) only. Non-privileged users get silent ignore.

## Tasks

### Task 1: NewsAgent - Add privilege check in should_handle
**File:** `src/agents/news_agent.py`
**Test:** `tests/test_news_agent.py`

Steps:
1. Add `privilege_service` import (already imported)
2. In `should_handle()`: after trigger detection, check `privilege_service.is_privileged(user_id)` for group chats
3. For private chats: also require privilege (currently allows everyone)
4. Write test: privileged user can trigger, non-privileged cannot

### Task 2: CalendarAgent - Add privilege check in should_handle
**File:** `src/agents/calendar_agent.py`
**Test:** `tests/test_calendar_agent.py`

Steps:
1. Add `privilege_service` import
2. In `should_handle()`: before trigger check, verify user is privileged
3. Apply to all trigger types (view, add, remove, scrape, discrete scrape, inline add)
4. Write test: privileged user can trigger all calendar features, non-privileged cannot

### Task 3: ImageAnalyzerAgent - Add privilege check in should_handle
**File:** `src/agents/image_analyzer_agent.py`
**Test:** `tests/test_image_analyzer_agent.py` (or similar)

Steps:
1. Add `privilege_service` import (already imported)
2. In `should_handle()`: check privilege for all trigger cases (text trigger, image with session, etc.)
3. Write test: privileged user can start analysis session, non-privileged cannot

### Task 4: ProfilerAgent - Add privilege check in should_handle
**File:** `src/agents/profiler_agent.py`
**Test:** `tests/test_profiler_agent.py`

Steps:
1. Add `privilege_service` import (already imported)
2. In `should_handle()`: check privilege for text triggers and image with active session
3. Write test: privileged user can trigger profiling, non-privileged cannot

### Task 5: Run full test suite and verify
**Command:** `pytest tests/ -v --tb=short`

## Task Details

### Task 1: NewsAgent
**File:** `src/agents/news_agent.py`
- Line ~147: `should_handle()` method
- Current logic: allows private chat users, group chat triggers
- New logic: require `privilege_service.is_privileged(user_id)` for ALL contexts

### Task 2: CalendarAgent
**File:** `src/agents/calendar_agent.py`
- Line ~470: `should_handle()` method
- Current logic: checks triggers, active sessions, inline add
- New logic: at start of method, get `user_id`, check `privilege_service.is_privileged(user_id)`, return `False` if not

### Task 3: ImageAnalyzerAgent
**File:** `src/agents/image_analyzer_agent.py`
- Line ~315: `should_handle()` method
- Current logic: checks triggers, active sessions (waiting for image, question, analysis choice, calendar confirmation)
- New logic: at start of method, check privilege before any trigger logic

### Task 4: ProfilerAgent
**File:** `src/agents/profiler_agent.py`
- Line ~97: `should_handle()` method
- Current logic: checks profiler enabled, vision providers, triggers, active sessions
- New logic: at start of method, check privilege before trigger logic

## Test Examples

```python
# For each agent test:
async def test_privileged_user_can_trigger(agent, event, line_bot_api):
    with patch.object(privilege_service, 'is_privileged', return_value=True):
        assert await agent.should_handle(event, "news") is True

async def test_non_privileged_user_cannot_trigger(agent, event, line_bot_api):
    with patch.object(privilege_service, 'is_privileged', return_value=False):
        assert await agent.should_handle(event, "news") is False
```

## Acceptance Criteria
- [ ] All 4 agents reject non-privileged users in `should_handle`
- [ ] All 4 agents allow privileged users (existing behavior)
- [ ] All existing tests pass
- [ ] New tests added for privilege checks
- [ ] Full test suite passes (771+ tests)