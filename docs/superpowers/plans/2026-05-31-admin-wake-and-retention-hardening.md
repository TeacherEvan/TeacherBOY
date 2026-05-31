# Admin Wake And Retention Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add and verify regression coverage for admin wake resets, alias-based sleep handling, moderator parsing, and LINE user retention, applying minimal production fixes only where tests expose a real gap.

**Architecture:** Keep the current runtime structure intact. Work in narrow vertical slices: translation agent behavior, admin command parsing, and webhook persistence. Each slice starts with a failing test, then the smallest code fix if needed, then a focused rerun of that same check.

**Tech Stack:** Python, FastAPI, LINE Bot SDK v3, pytest, unittest.mock

---

### Task 1: Translation Sleep/Wake Regression Coverage

**Files:**
- Create: `tests/test_translation_agent_sleep_wake.py`
- Modify: `src/agents/translation_agent.py` (only if tests expose a gap)

- [ ] **Step 1: Write the failing tests**

Add targeted tests for:

```python
@pytest.mark.asyncio
async def test_admin_thai_message_wakes_sleeping_chat_and_starts_session():
    ...

@pytest.mark.asyncio
async def test_non_privileged_alias_stop_falls_through_to_translation():
    ...

def test_sleep_command_matches_all_identity_aliases():
    ...
```

Use a patched `session_manager`, a mocked translation service returning a deterministic translation, and a patched bot identity profile with aliases like `ms. green` and `ms green`.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_translation_agent_sleep_wake.py -q`

Expected: at least one failure if a regression gap exists; if all pass immediately, treat the task as coverage-only and continue without production code changes.

- [ ] **Step 3: Write the minimal implementation if a test failed**

Limit any production edit to `src/agents/translation_agent.py`, preserving the current routing order and privilege checks.

- [ ] **Step 4: Run tests to verify green**

Run: `pytest tests/test_translation_agent_sleep_wake.py -q`

Expected: all tests pass.

### Task 2: Admin Parsing Regression Coverage

**Files:**
- Modify: `tests/test_admin_agent.py`
- Modify: `src/agents/admin_agent.py` (only if tests expose a gap)

- [ ] **Step 1: Write the failing tests**

Add focused tests for:

```python
def test_parse_admin_command_accepts_assistant_add_with_whitespace_and_quotes():
    ...

@pytest.mark.asyncio
async def test_non_admin_assistant_add_is_not_handled():
    ...
```

The parser test should cover forms such as `Assistant add=U123`, `Assistant add = U123`, and `Assistant add = "U123"`.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_admin_agent.py -q -k "assistant_add or parse_admin_command"`

Expected: fail only if parsing or authorization behavior is incomplete.

- [ ] **Step 3: Write the minimal implementation if a test failed**

Keep the fix local to `src/agents/admin_agent.py` and preserve current public command formats.

- [ ] **Step 4: Run tests to verify green**

Run: `pytest tests/test_admin_agent.py -q -k "assistant_add or parse_admin_command"`

Expected: selected tests pass.

### Task 3: Webhook Persistence Coverage

**Files:**
- Modify: `tests/test_main.py`
- Modify: `src/main.py` (only if tests expose a gap)

- [ ] **Step 1: Write the failing tests**

Add focused tests for:

```python
def test_follow_event_upserts_known_line_user(client, mock_settings):
    ...

def test_routed_llm_text_message_records_interaction_and_user(client, mock_settings):
    ...
```

The follow-event test should assert `upsert_user` is awaited for a `FollowEvent`. The routed text test should assert both `record_interaction` and `upsert_user` are awaited after a handled text route.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_main.py -q -k "follow_event_upserts_known_line_user or routed_llm_text_message_records_interaction_and_user"`

Expected: fail only if the webhook persistence path is incomplete.

- [ ] **Step 3: Write the minimal implementation if a test failed**

Restrict fixes to `src/main.py`, preserving best-effort behavior and existing structured-record semantics.

- [ ] **Step 4: Run tests to verify green**

Run: `pytest tests/test_main.py -q -k "follow_event_upserts_known_line_user or routed_llm_text_message_records_interaction_and_user"`

Expected: selected tests pass.

### Task 4: Final Verification

**Files:**
- Verify: `tests/test_private_help.py`
- Verify: `tests/test_translation_agent_sleep_wake.py`
- Verify: `tests/test_admin_agent.py`
- Verify: `tests/test_main.py`

- [ ] **Step 1: Run the combined verification suite**

Run: `pytest tests/test_private_help.py tests/test_translation_agent_sleep_wake.py tests/test_admin_agent.py tests/test_main.py -q`

Expected: all selected tests pass.

- [ ] **Step 2: Review the resulting diff**

Run: `git --no-pager diff -- tests/test_translation_agent_sleep_wake.py tests/test_admin_agent.py tests/test_main.py src/agents/translation_agent.py src/agents/admin_agent.py src/main.py`

Expected: only the planned regression coverage and any minimal code fixes appear.