# Mounted Storage Path Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL:
> Use `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the new mounted storage volume the practical backing store
for local persistence by removing the remaining hardcoded local data
paths, while keeping the existing per-surface Hugging Face dataset model
intact.

**Architecture:** Keep the current separation of HF dataset repos for
conversation memory, document memory, history logs, and calendar. Add
explicit configuration for the two remaining hardcoded local
persistence paths: conversation memory cache/storage and review-agent
staff memory. Existing configurable paths for documents, logs,
calendar, and bot identity continue to point at the mounted volume
through environment variables.

**Tech Stack:** Python, FastAPI, Pydantic Settings, pytest, Hugging Face Hub CommitScheduler

---

## Goal and Non-Goals

### Goal

- Route all meaningful repo-local persistence surfaces to configurable
  mounted-storage paths, with minimal code churn and no behavior change
  to HF sync semantics.

### Non-Goals

- Do not consolidate all persistence into a single shared HF dataset repo.
- Do not redesign `scripts/hf_sync.py` to upload namespaced subfolders into one repo.
- Do not introduce a new persisted task/job store for APScheduler jobs;
  scheduled tasks remain runtime-only in this plan.
- Do not refactor document, calendar, log, or bot-identity storage
  logic beyond configuration/documentation needed to point them at the
  mount.

## File Responsibilities

### Modify

- `src/config.py`
  Adds first-class settings for conversation-memory local storage and review-agent staff-memory storage.
- `src/services/conversation_memory_service.py`
  Accepts and uses a configurable local storage path instead of
  hardcoding `./data/conversations`.
- `src/main.py`
  Wires new settings into conversation-memory initialization and `StaffMemoryService` construction.
- `tests/test_conversation_memory.py`
  Covers configurable storage path behavior for the conversation memory service.
- `tests/test_main.py`
  Covers startup wiring for the new storage settings.
- `docs/reference/environment.md`
  Documents the new environment variables and the recommended
  mounted-volume configuration.
- `docs/CONVERSATION_MEMORY.md`
  Documents the conversation-memory local storage path and mount usage.
- `workspace_non_critical_issues.json`
  Tracks the current external markdown-lint warning as non-critical.

### Leave Untouched

- `src/services/document_memory_service.py`
  Already accepts `storage_path`.
- `src/services/history_log_service.py`
  Already accepts `storage_path`.
- `src/services/calendar_service.py`
  Already accepts `local_storage_path` / `storage_path`.
- `src/services/scheduler_service.py`
  No persisted task store exists here; changing that is out of scope.
- `scripts/hf_sync.py`
  Separate HF repos remain the intended model for this plan.

## Ordered Tasks

### Task 1: Add configurable conversation-memory local storage path

**Depends on:** none

**Files:**

- Modify: `src/config.py`
- Modify: `src/services/conversation_memory_service.py`
- Test: `tests/test_conversation_memory.py`

- [ ] **Step 1: Write the failing tests**

Add these tests to `tests/test_conversation_memory.py`:

```python
from pathlib import Path


def test_service_uses_explicit_storage_path(tmp_path):
    storage_path = tmp_path / "conversations"

    service = ConversationMemoryService(
        storage_path=str(storage_path),
        max_messages=10,
        session_ttl_hours=24,
    )

    assert service.local_storage_path == storage_path


def test_init_conversation_memory_accepts_storage_path(tmp_path):
    storage_path = tmp_path / "conversation-cache"

    service = init_conversation_memory(storage_path=str(storage_path))

    assert service.local_storage_path == storage_path
```

- [ ] **Step 2: Run the narrow test target and confirm failure**

Run:

```bash
pytest tests/test_conversation_memory.py -k "storage_path" -v
```

Expected:

```text
FAIL because ConversationMemoryService.__init__ does not accept storage_path
```

- [ ] **Step 3: Implement the minimum production change**

Update `src/config.py` to add a new setting near the conversation-memory section:

```python
conversation_storage_path: str = Field(
    default="./data/conversations",
    description="Local directory for conversation memory persistence and HF sync cache.",
)
```

Update `src/services/conversation_memory_service.py` so the constructor
and initializer accept the new path and store it on the instance:

```python
def __init__(
    self,
    hf_token: Optional[str] = None,
    hf_repo_id: Optional[str] = None,
    max_messages: int = MAX_MESSAGES_PER_SESSION,
    session_ttl_hours: int = SESSION_TTL_HOURS,
    storage_path: str = "./data/conversations",
):
    self.local_storage_path = Path(storage_path)
    self._local_storage_path: Optional[Path] = None
```

Replace the hardcoded path in `_setup_hf_storage()` with:

```python
self._local_storage_path = self.local_storage_path
self._local_storage_path.mkdir(parents=True, exist_ok=True)
```

Update `init_conversation_memory()` to accept and forward `storage_path`:

```python
def init_conversation_memory(
    hf_token: Optional[str] = None,
    hf_repo_id: Optional[str] = None,
    storage_path: Optional[str] = None,
) -> ConversationMemoryService:
    conversation_memory_service = ConversationMemoryService(
        hf_token=hf_token,
        hf_repo_id=hf_repo_id,
        storage_path=storage_path or settings.conversation_storage_path,
    )
```

- [ ] **Step 4: Run the same narrow test target and confirm pass**

Run:

```bash
pytest tests/test_conversation_memory.py -k "storage_path" -v
```

Expected:

```text
PASS for both storage_path tests
```

- [ ] **Step 5: Run the broader conversation-memory regression slice**

Run:

```bash
pytest tests/test_conversation_memory.py -v
```

Expected:

```text
PASS with existing conversation-memory behavior unchanged
```

- [ ] **Step 6: Commit**

```bash
git add src/config.py src/services/conversation_memory_service.py tests/test_conversation_memory.py
git commit -m "feat: make conversation memory storage path configurable"
```

### Task 2: Add configurable staff-memory storage path for the review agent

**Depends on:** Task 1

**Files:**

- Modify: `src/config.py`
- Modify: `src/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing startup-wiring test**

Add a targeted startup test to `tests/test_main.py` that patches
`src.main.StaffMemoryService` and asserts it receives the configured
path:

```python
def test_lifespan_uses_configured_staff_memory_storage_path(
    readiness_lifespan_environment,
    mock_settings,
):
    app, _, _, _, _ = readiness_lifespan_environment
    mock_settings.staff_memory_storage_path = "./data/test_staff_memory/staff_memory.json"

    with patch("src.main.StaffMemoryService") as staff_memory_cls:
        with TestClient(app):
            pass

    staff_memory_cls.assert_called_once()
    storage_path = staff_memory_cls.call_args.args[0]
    assert str(storage_path) == "data/test_staff_memory/staff_memory.json"
```

- [ ] **Step 2: Run the narrow startup test and confirm failure**

Run:

```bash
pytest tests/test_main.py -k "staff_memory_storage_path" -v
```

Expected:

```text
FAIL because settings has no staff_memory_storage_path and main.py still hardcodes ./data/staff_memory/staff_memory.json
```

- [ ] **Step 3: Implement the minimum wiring change**

Add a new setting to `src/config.py`:

```python
staff_memory_storage_path: str = Field(
    default="./data/staff_memory/staff_memory.json",
    description="Local JSON storage path for review-agent staff memory.",
)
```

Update `src/main.py` to replace the hardcoded path:

```python
staff_memory_service = StaffMemoryService(
    Path(settings.staff_memory_storage_path)
)
```

Update the `mock_settings` fixture in `tests/test_main.py` so startup has a default value:

```python
mock_settings.staff_memory_storage_path = "./data/test_staff_memory/staff_memory.json"
```

- [ ] **Step 4: Re-run the narrow startup test and confirm pass**

Run:

```bash
pytest tests/test_main.py -k "staff_memory_storage_path" -v
```

Expected:

```text
PASS with StaffMemoryService receiving the configured path
```

- [ ] **Step 5: Run the broader startup regression slice**

Run:

```bash
pytest tests/test_main.py -k "readiness or staff_memory_storage_path" -v
```

Expected:

```text
PASS for readiness coverage plus the new storage-path assertion
```

- [ ] **Step 6: Commit**

```bash
git add src/config.py src/main.py tests/test_main.py
git commit -m "feat: configure review staff memory storage path"
```

### Task 3: Document mounted-volume deployment and keep HF repo separation explicit

**Depends on:** Task 2

**Files:**

- Modify: `docs/reference/environment.md`
- Modify: `docs/CONVERSATION_MEMORY.md`

- [ ] **Step 1: Write the documentation assertions as reviewer checks**

The docs update must explicitly state all of the following:

```text
1. HF repo separation stays in place: HF_MEMORY_REPO_ID, DOCUMENT_HF_REPO_ID, HISTORY_LOG_HF_REPO_ID, CALENDAR_HF_REPO_ID
2. The mounted volume should back local paths, not replace repo IDs
3. Conversation memory now has CONVERSATION_STORAGE_PATH
4. Review agent staff memory now has STAFF_MEMORY_STORAGE_PATH
5. There is no persisted APScheduler task store in this implementation
```

- [ ] **Step 2: Update the environment reference**

Add the new variables to `docs/reference/environment.md` and include a mounted-volume example like:

```env
CONVERSATION_STORAGE_PATH=/data/ms-sunshine/conversations
DOCUMENT_STORAGE_PATH=/data/ms-sunshine/documents
HISTORY_LOG_PATH=/data/ms-sunshine/logs
CALENDAR_DATA_PATH=/data/ms-sunshine/calendar
BOT_IDENTITY_STORAGE_PATH=/data/ms-sunshine/bot_identity/profile.json
STAFF_MEMORY_STORAGE_PATH=/data/ms-sunshine/staff_memory/staff_memory.json
```

Add a note that these paths complement, not replace, the existing HF repo IDs.

- [ ] **Step 3: Update the conversation-memory guide**

Add a section to `docs/CONVERSATION_MEMORY.md` showing both the HF config and the mounted-local path config:

```env
HF_MEMORY_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
HF_MEMORY_REPO_ID=your-username/zeus-memory
CONVERSATION_STORAGE_PATH=/data/ms-sunshine/conversations
```

Also state that mounted storage improves local persistence/caching,
while long-term HF sync still uses the configured dataset repo.

- [ ] **Step 4: Run a structural validation pass**

Run:

```bash
rg -n "CONVERSATION_STORAGE_PATH|STAFF_MEMORY_STORAGE_PATH|HF_MEMORY_REPO_ID|DOCUMENT_HF_REPO_ID|HISTORY_LOG_HF_REPO_ID|CALENDAR_HF_REPO_ID" docs/reference/environment.md docs/CONVERSATION_MEMORY.md
```

Expected:

```text
Matches for both new path variables and the existing HF repo variables
```

- [ ] **Step 5: Commit**

```bash
git add docs/reference/environment.md docs/CONVERSATION_MEMORY.md
git commit -m "docs: describe mounted storage paths for persistent data"
```

### Task 4: Final verification and deployment rollout

**Depends on:** Task 3

**Files:**

- No new production files
- Verify: `src/config.py`, `src/services/conversation_memory_service.py`,
  `src/main.py`, `tests/test_conversation_memory.py`,
  `tests/test_main.py`, `docs/reference/environment.md`, and
  `docs/CONVERSATION_MEMORY.md`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
pytest tests/test_conversation_memory.py tests/test_main.py tests/test_review_agent.py tests/test_staff_memory_service.py tests/test_startup_data_loader.py -v
```

Expected:

```text
PASS with no regressions in startup wiring, review-agent behavior, or conversation memory
```

- [ ] **Step 2: Run repository diagnostics for touched files**

Run:

```bash
python -m pytest tests/test_conversation_memory.py tests/test_main.py -q
```

Expected:

```text
Short PASS summary for the edited test slices
```

- [ ] **Step 3: Review the diff for scope control**

Run:

```bash
git --no-pager diff -- src/config.py src/services/conversation_memory_service.py src/main.py tests/test_conversation_memory.py tests/test_main.py docs/reference/environment.md docs/CONVERSATION_MEMORY.md
```

Expected:

```text
Only storage-path configuration, startup wiring, tests, and docs updates
```

- [ ] **Step 4: Deploy the mount-backed configuration**

Set these environment variables in the HF Space or deployment target:

```env
CONVERSATION_STORAGE_PATH=/data/ms-sunshine/conversations
DOCUMENT_STORAGE_PATH=/data/ms-sunshine/documents
HISTORY_LOG_PATH=/data/ms-sunshine/logs
CALENDAR_DATA_PATH=/data/ms-sunshine/calendar
BOT_IDENTITY_STORAGE_PATH=/data/ms-sunshine/bot_identity/profile.json
STAFF_MEMORY_STORAGE_PATH=/data/ms-sunshine/staff_memory/staff_memory.json
```

Keep the existing repo IDs unchanged:

```env
HF_MEMORY_REPO_ID=...
DOCUMENT_HF_REPO_ID=...
HISTORY_LOG_HF_REPO_ID=...
CALENDAR_HF_REPO_ID=...
```

- [ ] **Step 5: Smoke test after deploy**

Run these checks manually in the deployed environment:

```text
1. Send a normal LLM conversation and confirm context still works
2. Trigger a review flow and confirm staff memory writes succeed
3. Verify calendar, logs, and document uploads still work using their existing paths
4. Restart the service and confirm mounted-path files remain present
```

- [ ] **Step 6: Final commit**

```bash
git add src/config.py src/services/conversation_memory_service.py src/main.py tests/test_conversation_memory.py tests/test_main.py docs/reference/environment.md docs/CONVERSATION_MEMORY.md
git commit -m "feat: support mounted storage paths for persistent data"
```

## Review Notes

- The most practical outcome is **not** a shared HF dataset repo
  migration. That path requires repo namespacing, preload filtering,
  and sync redesign across multiple services.
- The only hardcoded local paths that currently block full mount adoption are conversation memory and staff memory.
- APScheduler jobs remain runtime constructs; if task persistence is
  later required, that should be planned as a separate feature.

## Self-Review

- Spec coverage: covers the practical mounted-storage approach, leaves
  shared-repo consolidation out of scope, and explicitly calls out the
  lack of persisted task storage.
- Placeholder scan: no TODO/TBD markers remain.
- Type consistency: the plan uses `conversation_storage_path` and
  `staff_memory_storage_path` consistently across config, startup
  wiring, tests, and docs.
