# Admin Safety and Calendar Batch Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL:
> Use `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Design basis:** This plan is based on the admin-safety and calendar-batch
> design approved in chat on 2026-05-31. No separate design-spec file was
> written before planning, so this document is the execution handoff.

**Goal:** Harden destructive admin flows so they can only be armed and confirmed
through the requesting admin's DM, add a DM-first clickable admin dashboard for
safe operations, and upgrade calendar batch flows so remove and scrape-add use
explicit selection, preview, expiry, and owner-bound confirmation.

**Architecture:** Keep `AdminAgent` as the command router, but move destructive
admin preview/confirm logic into focused helper modules so the large agent file
stops accumulating safety policy inline. Reuse the existing process-local
`AdminConfirmationService` as the pending-action registry, extending it with
source/target binding, dedupe, expiry metadata, and delivery/arming semantics.
Keep the existing `ADMIN_ACTION` audit event path in `HistoryLogService` and add
metadata instead of introducing a new logging backend. For calendar, extend
`CalendarSessionManager` with explicit selection and revision state so
`RemoveFlow` and `ScrapeFlow` can reject stale or ambiguous input instead of
executing guessed intent.

**Tech Stack:** Python, FastAPI runtime, LINE Bot SDK v3, pytest, existing
history-log and rate-limiter services, existing FlexMessage support.

---

## Goal and Non-Goals

### Goal

- Prevent destructive admin actions from being armed or confirmed in groups or
  rooms.
- Remove any fallback that can leak confirmation capability or target details in
  a group.
- Require exact-target preview, cancel, expiry, ownership, and audit logging for
  `leave`, `purge`, and `reset`.
- Add a DM-first admin dashboard with safe direct actions and risky preview-only
  actions.
- Upgrade calendar remove and scrape-add flows to use explicit batch selection,
  preview, and stale-session rejection.

### Non-Goals

- Do not implement live runtime switching of `PERSISTENCE_BACKEND`.
  The dashboard may display current backend state, but it must not hot-switch
  local/convex in this plan.
- Do not add a LIFF app, web dashboard, or browser-deep-link workflow for admin
  controls.
- Do not add cross-process or database-backed persistence for admin pending
  actions; they remain process-local in this plan.
- Do not redesign unrelated admin commands such as `status`, `wake`, `sleep`,
  `sessions`, `send`, `llm_send`, or `send_weather` beyond dashboard wiring.
- Do not refactor calendar CRUD storage or reminder delivery beyond the batch UX
  and session safety needed for remove/scrape-add.

## File Responsibilities

### Create

- `src/agents/admin/__init__.py`
  Package marker for extracted admin helper modules.
- `src/agents/admin/destructive_action_flow.py`
  Owns destructive admin request/preview/confirm/cancel orchestration,
  including DM-only arming, target echo, rate-limit checks, and audit metadata.
- `src/agents/admin/dashboard_builder.py`
  Builds FlexMessages for the DM-first admin dashboard and the group-safe
  "check your DM" handoff.
- `tests/test_admin_confirmation_service.py`
  Covers pending-action ownership, expiry, target binding, and dedupe behavior.
- `tests/test_calendar_remove_flow.py`
  Covers remove-flow selection parsing, `all`/`none`/`done`, preview text, and
  stale-session rejection.

### Modify

- `src/services/admin_confirmation_service.py`
  Extend pending actions from token-only records to bound pending actions with
  exact preview metadata, dedupe, and delivery-aware arming semantics.
- `src/services/rate_limiter.py`
  Add a small admin-destructive limiter surface, or a dedicated limiter section,
  for per-admin and per-target throttling.
- `src/agents/admin_agent.py`
  Keep routing here, but delegate destructive actions and dashboard generation to
  the new admin helpers.
- `src/services/calendar_session_manager.py`
  Add explicit batch-selection state for remove and scrape-add, revision fields,
  and helpers to reject stale confirms.
- `src/agents/calendar/remove_flow.py`
  Replace loose yes/no deletion flow with selection, preview, and explicit final
  delete/cancel actions.
- `src/agents/calendar/scrape_flow.py`
  Replace one-by-one scrape review with numbered batch selection, preview, and a
  single shared reminder choice for the selected batch in v1.
- `tests/test_admin_agent.py`
  Add end-to-end admin request/confirm/dashboard safety tests.
- `tests/test_calendar_agent.py`
  Add routing and stale-session regressions for remove flow.
- `tests/test_calendar_scrape.py`
  Add session-manager and flow tests for scrape batch selection.
- `docs/ADMIN_COMMANDS.md`
  Document DM-only destructive actions, `/admin dashboard`, and the fact that
  group requests open private previews rather than executing directly.
- `docs/ADMIN_QUICK_START.md`
  Add operator-facing usage notes for the new DM confirmation model and dashboard.
- `docs/CALENDAR_REMINDERS.md`
  Document remove-flow `all`/`none`/`done` semantics and scrape batch selection.

### Leave Untouched

- `src/config.py`
  Existing `persistence_backend` setting is display-only in this plan; no new
  runtime-switch setting is added.
- `src/main.py`
  No startup wiring change is required for this plan.
- `src/services/calendar_service.py`
  CRUD behavior remains unchanged; only callers and session state change.
- `src/services/history_log_service.py`
  Reuse existing `ADMIN_ACTION` and calendar event logging surfaces; do not add a
  new storage backend.

## Ordered Tasks

### Task 1: Harden the pending-action registry for destructive admin flows

**Depends on:** none

**Files:**

- Create: `tests/test_admin_confirmation_service.py`
- Modify: `src/services/admin_confirmation_service.py`

- [ ] **Step 1: Write the failing unit tests**

Add focused tests to `tests/test_admin_confirmation_service.py` for these exact
behaviors:

- `test_create_records_source_target_action_and_preview_metadata`
- `test_confirm_rejects_wrong_user`
- `test_confirm_rejects_expired_pending_action`
- `test_create_replaces_or_rejects_duplicate_pending_action_for_same_user_target_and_action`
- `test_cancel_removes_only_matching_users_pending_action`

The test fixture should instantiate a fresh `AdminConfirmationService()` for
isolation and assert the pending action captures:

- `action`
- `requested_by_user_id`
- `requested_from_chat_id`
- target chat or target kind/id in `payload`
- human-readable preview text or preview fields
- expiry timestamp
- a revision/nonce used to distinguish stale confirmations

- [ ] **Step 2: Run the narrow unit-test slice and confirm failure**

Run:

```bash
pytest tests/test_admin_confirmation_service.py -v
```

Expected:

```text
FAIL because the service only stores token/action/payload and does not yet enforce
preview metadata, dedupe, or richer pending-action validation.
```

- [ ] **Step 3: Implement the minimum registry changes**

Update `src/services/admin_confirmation_service.py` so `PendingAdminAction`
tracks the following execution-bound fields:

- requesting admin user id
- source chat id
- action type
- payload with exact target
- preview text or structured preview fields
- created/expires timestamps
- revision/nonce

Add service methods or method parameters so callers can:

- create a pending action with exact target/preview metadata
- check for an existing pending destructive action for the same user + target + action
- cancel only the requesting admin's pending action
- confirm only when the action is not expired and the requesting user matches

Do not add persistence beyond the existing process-local store.

- [ ] **Step 4: Re-run the same unit-test slice and confirm pass**

Run:

```bash
pytest tests/test_admin_confirmation_service.py -v
```

Expected:

```text
PASS for all pending-action registry tests.
```

- [ ] **Step 5: Commit the focused slice**

```bash
git add src/services/admin_confirmation_service.py tests/test_admin_confirmation_service.py
git commit -m "feat: harden admin pending action registry"
```

### Task 2: Enforce DM-only arming and confirmation for `leave`, `purge`, and `reset`

**Depends on:** Task 1

**Files:**

- Create: `src/agents/admin/destructive_action_flow.py`
- Modify: `src/agents/admin_agent.py`
- Modify: `src/services/rate_limiter.py`
- Modify: `tests/test_admin_agent.py`

- [ ] **Step 1: Write the failing admin-flow tests**

Add or update tests in `tests/test_admin_agent.py` for these exact behaviors:

- `test_reset_requests_private_confirmation_instead_of_executing_immediately`
- `test_group_leave_request_replies_neutrally_and_sends_preview_to_dm`
- `test_group_purge_request_does_not_echo_token_or_target_in_group_reply`
- `test_push_failure_does_not_arm_destructive_action`
- `test_confirm_in_group_is_rejected_and_does_not_execute`
- `test_confirm_in_private_chat_executes_matching_reset_action`
- `test_second_destructive_request_hits_admin_rate_limit`

Test details:

- For group/room requests, assert the reply text does **not** include a token,
  `/admin confirm`, or the exact target id.
- For DM preview delivery, assert `push_message` is called with the exact target
  and effect summary.
- For push failure, assert the group reply says the private preview could not be
  opened and that no pending action remains armed.
- For `reset`, assert `session_manager.end_session` and
  `session_manager.clear_message_history` are **not** called during the request
  step, only during the confirmed DM step.
- For the limiter test, assert the second destructive request returns a rate
  limit response without creating a second pending action.

- [ ] **Step 2: Run the narrow admin-flow slice and confirm failure**

Run:

```bash
pytest tests/test_admin_agent.py -k "reset_requests_private_confirmation or group_leave_request_replies_neutrally or group_purge_request_does_not_echo or push_failure_does_not_arm or confirm_in_group_is_rejected or matching_reset_action or destructive_request_hits_admin_rate_limit" -v
```

Expected:

```text
FAIL because `/admin reset` still executes immediately, destructive requests can
fallback to in-chat confirm text, and no admin-destructive rate limiter exists.
```

- [ ] **Step 3: Implement the destructive-action coordinator**

Create `src/agents/admin/destructive_action_flow.py` and move the following
policy there:

- destructive action classification for `leave`, `purge`, and `reset`
- exact preview text generation
- DM-only arming semantics: a destructive action is considered pending only if
  the DM preview delivery succeeds
- neutral group reply text that reveals no token or target id
- revalidation before execution: same admin, same action, same target, not expired
- audit logging through existing `ADMIN_ACTION` events and metadata
- rate-limit checks per admin and per target

Update `src/agents/admin_agent.py` to:

- delegate `leave`, `purge`, `reset`, `confirm`, and `cancel`
- stop constructing fallback confirm text that leaks execution capability
- keep actual destructive side effects in one execution path used only after
  successful DM confirmation

Extend `src/services/rate_limiter.py` with a minimal admin-destructive limiter.
Recommended initial limits:

- per admin: 3 destructive requests per 10 minutes
- per target chat: 1 active destructive request at a time

- [ ] **Step 4: Re-run the same narrow admin-flow slice and confirm pass**

Run:

```bash
pytest tests/test_admin_agent.py -k "reset_requests_private_confirmation or group_leave_request_replies_neutrally or group_purge_request_does_not_echo or push_failure_does_not_arm or confirm_in_group_is_rejected or matching_reset_action or destructive_request_hits_admin_rate_limit" -v
```

Expected:

```text
PASS for all destructive admin safety tests.
```

- [ ] **Step 5: Run the broader admin regression slice**

Run:

```bash
pytest tests/test_admin_agent.py -v
```

Expected:

```text
PASS with existing non-destructive admin commands unchanged.
```

- [ ] **Step 6: Commit the focused slice**

```bash
git add src/agents/admin/__init__.py src/agents/admin/destructive_action_flow.py src/agents/admin_agent.py src/services/rate_limiter.py tests/test_admin_agent.py
git commit -m "feat: require private confirmation for destructive admin actions"
```

### Task 3: Add the DM-first admin dashboard

**Depends on:** Task 2

**Files:**

- Create: `src/agents/admin/dashboard_builder.py`
- Modify: `src/agents/admin_agent.py`
- Modify: `tests/test_admin_agent.py`
- Modify: `docs/ADMIN_COMMANDS.md`
- Modify: `docs/ADMIN_QUICK_START.md`

- [ ] **Step 1: Write the failing dashboard tests**

Add tests to `tests/test_admin_agent.py` for these exact behaviors:

- `test_dashboard_in_private_chat_returns_flex_message`
- `test_dashboard_in_group_pushes_private_dashboard_and_replies_neutrally`
- `test_dashboard_safe_actions_are_direct_buttons`
- `test_dashboard_risky_actions_open_preview_only_commands`
- `test_dashboard_displays_current_persistence_backend_without_switch_control`

Test details:

- The DM dashboard must contain buttons for:
  - View status
  - Toggle sleep/wake
  - Open confirmations
  - View sessions
- Risky buttons must not directly execute destructive actions; they should emit
  a text command or handler entry that opens a preview flow.
- The dashboard should display the current backend mode from existing settings,
  but no button should mutate backend mode.
- The group path should push the dashboard to the admin's DM and reply in-group
  with a neutral message such as "I sent your admin panel privately.".

- [ ] **Step 2: Run the narrow dashboard slice and confirm failure**

Run:

```bash
pytest tests/test_admin_agent.py -k "dashboard" -v
```

Expected:

```text
FAIL because `/admin dashboard` is not implemented and no dashboard builder exists.
```

- [ ] **Step 3: Implement the dashboard builder and route**

Create `src/agents/admin/dashboard_builder.py` to build:

- a private-dashboard FlexMessage for DM use
- a small neutral handoff response for group/room invocation

Update `src/agents/admin_agent.py` to add `/admin dashboard` routing with this
behavior:

- private chat: reply with the dashboard FlexMessage
- group or room: push the dashboard to the admin's DM and reply neutrally
- if DM push fails: reply that the private dashboard could not be delivered and
  do not fall back to posting the dashboard in the group

Do not implement backend switching in this task.

- [ ] **Step 4: Re-run the same narrow dashboard slice and confirm pass**

Run:

```bash
pytest tests/test_admin_agent.py -k "dashboard" -v
```

Expected:

```text
PASS for all dashboard tests.
```

- [ ] **Step 5: Update the operator docs**

Update `docs/ADMIN_COMMANDS.md` and `docs/ADMIN_QUICK_START.md` to document:

- `/admin dashboard`
- DM-only destructive previews
- neutral group replies for risky commands
- lack of live backend switching in this release

- [ ] **Step 6: Commit the focused slice**

```bash
git add src/agents/admin/dashboard_builder.py src/agents/admin_agent.py tests/test_admin_agent.py docs/ADMIN_COMMANDS.md docs/ADMIN_QUICK_START.md
git commit -m "feat: add dm-first admin dashboard"
```

### Task 4: Replace calendar remove yes/no deletion with explicit selection and preview

**Depends on:** Task 2

**Files:**

- Create: `tests/test_calendar_remove_flow.py`
- Modify: `src/services/calendar_session_manager.py`
- Modify: `src/agents/calendar/remove_flow.py`
- Modify: `src/agents/calendar_agent.py`
- Modify: `tests/test_calendar_agent.py`
- Modify: `docs/CALENDAR_REMINDERS.md`

- [ ] **Step 1: Write the failing remove-flow tests**

Add flow and routing tests covering these exact behaviors:

In `tests/test_calendar_remove_flow.py`:

- `test_number_input_toggles_selected_events`
- `test_all_selects_every_visible_event`
- `test_none_clears_selection`
- `test_done_without_selection_is_rejected`
- `test_done_shows_exact_preview_before_delete`
- `test_ambiguous_input_is_rejected_without_partial_selection`

In `tests/test_calendar_agent.py`:

- `test_remove_confirmation_rejects_stale_session_revision`
- `test_remove_confirmation_rejects_non_owner_even_if_chat_has_session`
- `test_remove_confirmation_calls_service_only_after_preview_confirm`

Implementation target:

- `all`, `none`, `done`, and `cancel` must be recognized as exact commands.
- Comma-number input such as `1,3,5` must toggle or set selection deterministically.
- Inputs that mix unsupported text and numbers must be rejected, not partially guessed.
- `done` must show a preview that lists the exact selected titles and dates before
  the final delete/cancel step.

- [ ] **Step 2: Run the narrow remove-flow slices and confirm failure**

Run:

```bash
pytest tests/test_calendar_remove_flow.py -v
pytest tests/test_calendar_agent.py -k "remove_confirmation" -v
```

Expected:

```text
FAIL because remove flow currently jumps from freeform selection to yes/no delete
without `all`/`none`/`done`, explicit preview text, or stale-session revision checks.
```

- [ ] **Step 3: Implement the remove-flow state changes**

Update `src/services/calendar_session_manager.py` to add remove-flow fields and
helpers for:

- current selected event ids
- remove-flow revision/nonce
- preview-ready state transition from selection to final confirm
- stale-session rejection when revision or owner does not match

Update `src/agents/calendar/remove_flow.py` to:

- support `all`, `none`, `done`, `cancel`, and comma-number selection
- render the current selection count and exact titles/dates in the preview
- require explicit final `delete`/`cancel` style confirmation rather than loose
  yes/no wording
- fail closed when the session is expired, mismatched, or empty

Update `src/agents/calendar_agent.py` only as needed to route the new remove
states without broadening scope.

- [ ] **Step 4: Re-run the same narrow slices and confirm pass**

Run:

```bash
pytest tests/test_calendar_remove_flow.py -v
pytest tests/test_calendar_agent.py -k "remove_confirmation" -v
```

Expected:

```text
PASS for remove-flow selection, preview, and stale-session tests.
```

- [ ] **Step 5: Run the broader calendar remove/security regression slice**

Run:

```bash
pytest tests/test_calendar_agent.py tests/test_calendar_security.py -v
```

Expected:

```text
PASS with existing chat scoping and ownership protections preserved.
```

- [ ] **Step 6: Update calendar docs and commit**

Update `docs/CALENDAR_REMINDERS.md` to describe the new remove-flow commands.

```bash
git add src/services/calendar_session_manager.py src/agents/calendar/remove_flow.py src/agents/calendar_agent.py tests/test_calendar_remove_flow.py tests/test_calendar_agent.py docs/CALENDAR_REMINDERS.md
git commit -m "feat: add preview-based calendar removal flow"
```

### Task 5: Replace scrape one-by-one review with batch selection and shared reminder choice

**Depends on:** Task 2

**Files:**

- Modify: `src/services/calendar_session_manager.py`
- Modify: `src/agents/calendar/scrape_flow.py`
- Modify: `tests/test_calendar_scrape.py`
- Modify: `docs/CALENDAR_REMINDERS.md`

- [ ] **Step 1: Write the failing scrape-batch tests**

Add or update tests in `tests/test_calendar_scrape.py` for these exact behaviors:

- `test_set_scraped_events_enters_selecting_state_with_empty_selection`
- `test_toggle_scraped_candidates_by_number`
- `test_scrape_all_selects_every_candidate`
- `test_scrape_none_clears_selection`
- `test_scrape_done_without_selection_is_rejected`
- `test_scrape_done_shows_exact_preview_of_selected_events`
- `test_shared_reminder_choice_adds_only_selected_events`
- `test_stale_or_non_owner_scrape_session_cannot_confirm_batch_add`

Implementation target:

- When extraction completes, the session should enter `SCRAPE_SELECTING`, using
  the existing enum instead of staying in one-by-one `SCRAPE_REVIEWING`.
- Selection defaults to empty for safety.
- The prompt must show numbered candidates and quick replies for `All`, `None`,
  `Done`, and `Cancel`.
- `Done` must lead to a preview of only the selected items.
- The reminder prompt uses one shared reminder profile for the selected batch in
  this release.

- [ ] **Step 2: Run the narrow scrape-batch slice and confirm failure**

Run:

```bash
pytest tests/test_calendar_scrape.py -k "SCRAPE_SELECTING or selected_events or shared_reminder or stale_or_non_owner" -v
```

Expected:

```text
FAIL because scrape flow still processes one event at a time and does not yet
use explicit batch selection or batch preview.
```

- [ ] **Step 3: Implement the scrape-batch session and flow changes**

Update `src/services/calendar_session_manager.py` to add scrape-batch helpers for:

- selected scraped-event indices or ids
- scrape-batch revision/nonce
- transition from extraction to `SCRAPE_SELECTING`
- preview-ready state before the shared reminder prompt

Update `src/agents/calendar/scrape_flow.py` to:

- render numbered scrape candidates
- accept exact commands `all`, `none`, `done`, `cancel`, and comma-number selection
- reject ambiguous input without partial selection
- show a preview of selected events before asking for one reminder profile
- add only the selected events after the reminder choice
- fail closed when session ownership or revision validation fails

Do not reintroduce the old one-by-one add flow in parallel.

- [ ] **Step 4: Re-run the same narrow scrape-batch slice and confirm pass**

Run:

```bash
pytest tests/test_calendar_scrape.py -k "SCRAPE_SELECTING or selected_events or shared_reminder or stale_or_non_owner" -v
```

Expected:

```text
PASS for scrape batch-selection and shared reminder tests.
```

- [ ] **Step 5: Run the broader scrape regression slice**

Run:

```bash
pytest tests/test_calendar_scrape.py -v
```

Expected:

```text
PASS with existing extraction behavior and discrete-DM scrape delivery preserved.
```

- [ ] **Step 6: Update calendar docs and commit**

Update `docs/CALENDAR_REMINDERS.md` to describe scrape batch selection and the
shared reminder choice.

```bash
git add src/services/calendar_session_manager.py src/agents/calendar/scrape_flow.py tests/test_calendar_scrape.py docs/CALENDAR_REMINDERS.md
git commit -m "feat: add batch selection for scraped calendar events"
```

## Review and Verification Steps

After Tasks 1 through 5 are complete, run the full targeted verification set:

```bash
pytest tests/test_admin_confirmation_service.py tests/test_admin_agent.py tests/test_calendar_remove_flow.py tests/test_calendar_agent.py tests/test_calendar_scrape.py tests/test_calendar_security.py -v
```

Expected:

```text
PASS for all admin-safety, calendar-batch, and calendar-security regression tests.
```

Then run one broader sanity check if the targeted suite is green:

```bash
pytest -k "admin or calendar" -v
```

Expected:

```text
PASS for the broader admin/calendar slice, or any unrelated pre-existing failure
must be identified explicitly before claiming completion.
```

## Manual Review Steps

Before merging, manually review the diff against these questions:

- Does any group or room reply include a destructive confirmation token, exact
  confirm command, or target id?
- Does a failed DM push leave any destructive action armed?
- Does `/admin reset` now require DM confirmation before any session/history
  mutation occurs?
- Does the dashboard show current backend mode without offering a live switch?
- Do calendar remove and scrape flows reject ambiguous or stale input instead of
  guessing?
- Are docs aligned with DM-first admin behavior and `all`/`none`/`done`
  calendar semantics?

## Deployment Steps

No schema migration or new environment variable is required.

After merge:

1. Restart the bot process normally.
2. In a staging or controlled admin account, verify these live behaviors:
   - From a group, send `/admin leave` and confirm the group reply is neutral.
   - Confirm the DM preview contains the exact target and cancel button/action.
   - Send `/admin dashboard` from a group and confirm the dashboard arrives only
     in DM.
   - In a DM, use the dashboard safe actions and confirm they still work.
   - In calendar remove flow, verify `all`, `none`, `done`, and final delete.
   - In scrape flow, verify numbered selection, preview, and shared reminder.
3. If any destructive admin preview appears in-group, roll back before further
   testing.

## Self-Review Checklist

- [ ] Every approved design requirement maps to a task in this plan.
- [ ] Each behavior-changing task starts with failing tests.
- [ ] Exact file paths, commands, and expected outcomes are specified.
- [ ] Scope excludes backend hot-switching and unrelated refactors.
- [ ] Verification includes both targeted pytest slices and live LINE sanity checks.
