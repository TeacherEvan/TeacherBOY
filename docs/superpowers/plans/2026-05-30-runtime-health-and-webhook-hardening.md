# Runtime Health and Webhook Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make FastAPI operational endpoints truthful and cheap, stop leaking
internal webhook exceptions to callers, and lock the new contract in with
focused tests and docs.

**Architecture:** Keep the change localized to the FastAPI entrypoint and the
startup readiness helper. `src/main.py` owns HTTP contract behavior for
`/health`, `/readiness`, and `/webhook`; `src/services/startup_data_loader.py`
owns whether startup prerequisites are actually satisfied. Add regression tests
in `tests/test_main.py` and a new narrow unit test file for startup readiness
semantics, then update the docs that already mention these endpoints.

**Tech Stack:** Python 3.12, FastAPI, pytest, unittest.mock, existing repo
services

---

## Goals

- Make `/readiness` reflect actual startup state and return `503` until the app
  is ready.
- Make `/health` a cheap liveness endpoint with no external provider calls.
- Replace raw webhook exception leakage with a generic `500` response body.
- Add regression tests for readiness, health, and webhook error handling.
- Update endpoint documentation in the existing docs tree.

## Non-Goals

- Do not perform the broader agent dependency-injection refactor.
- Do not attempt a repo-wide coverage uplift to the documented 94% floor in
  this plan.
- Do not change agent routing priority, message behavior, or translation
  provider logic beyond probe semantics.
- Do not add new infrastructure endpoints beyond the existing `/health` and
  `/readiness` paths.

## File Responsibilities

### Modify

- `src/main.py`
  - Own the public HTTP contract for `/health`, `/readiness`, and `/webhook`.
  - Remove expensive external dependency probes from `/health`.
  - Return `503` from `/readiness` until startup data is ready and at least one
    agent is registered.
  - Return a generic `500` payload from webhook unexpected-error paths.
- `src/services/startup_data_loader.py`
  - Make readiness mean “all required startup-backed services finished loading
    or were not required”.
  - Keep backup creation as disaster recovery only, not as a readiness
    shortcut.
- `tests/test_main.py`
  - Add endpoint contract regression tests for health, readiness, and generic
    webhook failures.
- `docs/architecture/overview.md`
  - Document `/health` as liveness and `/readiness` as startup/dependency
    readiness.
- `docs/guides/quickstart.md`
  - Clarify expected behavior of the two operational endpoints during local
    startup.

### Create

- `tests/test_startup_data_loader.py`
  - Unit-test `StartupDataLoader.is_ready()` semantics independently from
    FastAPI.

### Leave Untouched

- `src/agents/**`
- `src/services/translation_service.py`
- `src/services/google_translation.py`
- `src/config.py`
- `tests/test_*` files outside the two targeted test modules unless a failing
  dependency forces a local follow-up

## Environment Setup

- [ ] **Step 0: Create an isolated Python environment**

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
```

Expected: `.venv` exists, dependencies install successfully, `pytest --version`
prints `pytest 7.4.3`.

---

### Task 1: Make Startup Readiness Truthful

**Files:**

- Modify: `src/services/startup_data_loader.py`
- Create: `tests/test_startup_data_loader.py`

- [ ] **Step 1: Write failing unit tests for readiness semantics**

Create `tests/test_startup_data_loader.py` with these tests:

```python
from src.services.startup_data_loader import StartupDataLoader


def test_is_ready_true_when_no_services_are_required():
    loader = StartupDataLoader()

    assert loader.is_ready() is True


def test_is_ready_false_when_calendar_is_required_but_not_loaded():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._calendar_loaded = False

    assert loader.is_ready() is False


def test_is_ready_true_when_all_required_services_are_loaded():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._calendar_loaded = True
    loader._memory_required = True
    loader._memory_loaded = True
    loader._documents_required = True
    loader._documents_loaded = True
    loader._logs_required = True
    loader._logs_loaded = True

    assert loader.is_ready() is True


def test_backup_creation_does_not_make_loader_ready_by_itself():
    loader = StartupDataLoader()
    loader._calendar_required = True
    loader._calendar_loaded = False
    loader._backup_created = True

    assert loader.is_ready() is False
```

- [ ] **Step 2: Run the new unit tests and confirm they fail**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_startup_data_loader.py
```

Expected: at least one failure because `StartupDataLoader` does not yet track
required-service flags and currently treats backup creation as sufficient
readiness.

- [ ] **Step 3: Implement required-service tracking in
  `src/services/startup_data_loader.py`**

Update the initializer and readiness logic to track which services are
required:

```python
class StartupDataLoader:
    """Ensures all persistent data is loaded before app serves traffic."""

    def __init__(self):
        self._calendar_required = False
        self._memory_required = False
        self._documents_required = False
        self._logs_required = False

        self._calendar_loaded = False
        self._memory_loaded = False
        self._documents_loaded = False
        self._logs_loaded = False
        self._backup_created = False
```

Inside `ensure_data_loaded(...)`, set the required flags before loading each
service and default non-required results to `True`:

```python
        self._calendar_required = bool(
            calendar_service and hasattr(calendar_service, "_hf_enabled") and calendar_service._hf_enabled
        )
        self._memory_required = bool(
            memory_service and hasattr(memory_service, "_hf_enabled") and memory_service._hf_enabled
        )
        self._documents_required = bool(
            document_service and hasattr(document_service, "_hf_enabled") and document_service._hf_enabled
        )
        self._logs_required = bool(
            history_log and hasattr(history_log, "_hf_enabled") and history_log._hf_enabled
        )

        results = {
            "calendar": not self._calendar_required,
            "memory": not self._memory_required,
            "documents": not self._documents_required,
            "logs": not self._logs_required,
            "backup_created": False,
        }
```

Replace `is_ready()` with this implementation:

```python
    def is_ready(self) -> bool:
        """Check if all required data is loaded."""
        if self._calendar_required and not self._calendar_loaded:
            return False
        if self._memory_required and not self._memory_loaded:
            return False
        if self._documents_required and not self._documents_loaded:
            return False
        if self._logs_required and not self._logs_loaded:
            return False
        return True
```

- [ ] **Step 4: Run the unit tests again**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_startup_data_loader.py
```

Expected: all tests in `tests/test_startup_data_loader.py` pass.

- [ ] **Step 5: Review the diff for this slice**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git diff -- src/services/startup_data_loader.py tests/test_startup_data_loader.py
```

Expected: only readiness semantics and their direct tests are changed.

---

### Task 2: Make `/readiness` Return Real Readiness

**Files:**

- Modify: `src/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add failing endpoint tests for not-ready and ready states**

Append these tests to `tests/test_main.py`:

```python
def test_readiness_returns_503_when_startup_is_not_ready(client):
    with patch("src.main.startup_loader.is_ready", return_value=False), patch(
        "src.main.agent_router.list_agents", return_value=[]
    ):
        response = client.get("/readiness")

    assert response.status_code == 503
    assert response.json()["ready"] is False
    assert response.json()["checks"]["startup_data"] == "loading"


def test_readiness_returns_200_when_startup_and_agents_are_ready(client):
    with patch("src.main.startup_loader.is_ready", return_value=True), patch(
        "src.main.agent_router.list_agents",
        return_value=[{"name": "TranslationAgent", "enabled": True}],
    ):
        response = client.get("/readiness")

    assert response.status_code == 200
    assert response.json()["ready"] is True
    assert response.json()["checks"]["startup_data"] == "ready"
    assert response.json()["checks"]["agents_registered"] == 1
```

- [ ] **Step 2: Run the readiness tests and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py -k readiness
```

Expected: failures because `/readiness` currently always returns HTTP 200 with
`{"ready": true, ...}`.

- [ ] **Step 3: Implement truthful readiness behavior in `src/main.py`**

Change the FastAPI import line to include `Response`:

```python
from fastapi import FastAPI, Request, HTTPException, Response
```

Replace `readiness_check()` with:

```python
@app.get("/readiness", tags=["Health"])
async def readiness_check(response: Response) -> Dict[str, Any]:
    """Readiness probe for orchestration systems."""
    agents_status = agent_router.list_agents()
    startup_ready = startup_loader.is_ready()
    agents_ready = len(agents_status) > 0
    ready = startup_ready and agents_ready

    response.status_code = 200 if ready else 503
    return {
        "ready": ready,
        "checks": {
            "startup_data": "ready" if startup_ready else "loading",
            "agents_registered": len(agents_status),
        },
        "google_translate_enabled": settings.is_google_translate_configured(),
    }
```

- [ ] **Step 4: Re-run the readiness tests**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py -k readiness
```

Expected: readiness tests pass.

- [ ] **Step 5: Run the full `test_main` module before continuing**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py
```

Expected: all tests in `tests/test_main.py` pass before taking the next slice.

---

### Task 3: Make `/health` Cheap and Liveness-Only

**Files:**

- Modify: `src/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add a failing regression test that `/health` does not call
  external providers**

Add this test to `tests/test_main.py`:

```python
def test_health_check_does_not_call_translation_providers(client):
    with patch(
        "src.main.google_translation_service.translate",
        side_effect=AssertionError("google translate probe should not run"),
    ), patch(
        "src.main.translation_service.translate",
        side_effect=AssertionError("libretranslate probe should not run"),
    ):
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "healthy"
```

- [ ] **Step 2: Run the health-only test and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py -k health_check_does_not_call_translation_providers
```

Expected: failure because `health_check()` currently performs live translation
probes.

- [ ] **Step 3: Replace expensive health logic with a cheap liveness
  response**

Replace `health_check()` in `src/main.py` with:

```python
@app.get("/health", tags=["Health"])
async def health_check() -> Dict[str, Any]:
    """Cheap liveness endpoint for process-level monitoring."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {
            "process": "alive",
            "startup_data": "ready" if startup_loader.is_ready() else "loading",
            "agents_registered": len(agent_router.list_agents()),
        },
    }
```

Delete the existing `ApiClient`, Google Translate, LibreTranslate, and
OpenRouter probe blocks from this endpoint. Do not move them elsewhere in this
plan.

- [ ] **Step 4: Re-run health and `test_main` coverage for this slice**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py -k "health_check"
pytest -q tests/test_main.py
```

Expected: both commands pass, and `/health` no longer reaches external network
code during tests.

---

### Task 4: Stop Leaking Internal Webhook Exceptions

**Files:**

- Modify: `src/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Add a failing test for generic webhook 500 responses**

Add this test to `tests/test_main.py`:

```python
def test_webhook_unexpected_error_returns_generic_500(client):
    with patch("src.main.webhook_parser.parse", side_effect=ValueError("boom")):
        response = client.post(
            "/webhook",
            data="{}",
            headers={"X-Line-Signature": "sig"},
        )

    assert response.status_code == 500
    assert response.json() == {
        "status": "error",
        "detail": "Internal server error",
    }
```

- [ ] **Step 2: Run the webhook error test and confirm failure**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py -k unexpected_error_returns_generic_500
```

Expected: failure because the endpoint currently returns the raw exception text
(`"boom"`).

- [ ] **Step 3: Replace the generic webhook exception response in
  `src/main.py`**

Replace the final generic exception block in `webhook()` with:

```python
    except Exception:
        logger.error("❌ Webhook processing error", exc_info=True)
        return JSONResponse(
            content={"status": "error", "detail": "Internal server error"},
            status_code=500,
        )
```

Leave the `InvalidSignatureError` branch unchanged.

- [ ] **Step 4: Re-run the focused webhook tests**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_main.py -k "webhook"
```

Expected: invalid-signature tests still pass, and the new generic-500 test
passes.

---

### Task 5: Update Operational Documentation

**Files:**

- Modify: `docs/architecture/overview.md`
- Modify: `docs/guides/quickstart.md`

- [ ] **Step 1: Update the architecture overview endpoint descriptions**

Change the operational endpoints section in `docs/architecture/overview.md` to:

```markdown
## Operational endpoints

- `/health` (cheap liveness probe; no external provider calls)
- `/readiness` (startup/data/agent readiness; returns HTTP 503 until ready)
```

- [ ] **Step 2: Update quickstart expectations for local checks**

Replace the health endpoint bullets in `docs/guides/quickstart.md` with:

```markdown
Health endpoints:

- `GET http://localhost:8000/health` — process liveness, always cheap
- `GET http://localhost:8000/readiness` — startup readiness, may return `503` until startup data is loaded and agents are registered
```

- [ ] **Step 3: Verify the doc diff only touches endpoint semantics**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git diff -- docs/architecture/overview.md docs/guides/quickstart.md
```

Expected: only the two endpoint description blocks changed.

---

### Task 6: Final Verification, Review, and Handoff

**Files:**

- Review: `src/main.py`
- Review: `src/services/startup_data_loader.py`
- Review: `tests/test_main.py`
- Review: `tests/test_startup_data_loader.py`
- Review: `docs/architecture/overview.md`
- Review: `docs/guides/quickstart.md`

- [ ] **Step 1: Run the focused verification suite**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q tests/test_startup_data_loader.py tests/test_main.py
```

Expected: all focused tests pass.

- [ ] **Step 2: Run the full repository test suite**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest -q
```

Expected: full suite passes with no new failures.

- [ ] **Step 3: Run coverage and record the result honestly**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
pytest --cov=src --cov-report=term
```

Expected: tests pass and total coverage does not decrease from the pre-change
baseline. Record the actual percentage in the review notes; do not claim the
repo meets the documented 94% target unless the command output proves it.

- [ ] **Step 4: Do a manual endpoint smoke check**

Run the app:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
. .venv/bin/activate
python -m uvicorn src.main:app --reload --port 8000
```

In another shell:

```bash
curl -i http://localhost:8000/health
curl -i http://localhost:8000/readiness
```

Expected:

- `/health` returns `HTTP/1.1 200 OK`
- `/readiness` returns `200` only after startup completes successfully in the
  live app
- response bodies match the new documented contract

- [ ] **Step 5: Review the final diff**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git diff -- src/main.py src/services/startup_data_loader.py tests/test_main.py tests/test_startup_data_loader.py docs/architecture/overview.md docs/guides/quickstart.md
```

Expected: diff is limited to the operational endpoint contract, readiness
helper logic, tests, and docs.

- [ ] **Step 6: Prepare PR/review notes**

Include these points in the PR description or review handoff:

```markdown
- `/health` is now a cheap liveness endpoint with no external dependency probes.
- `/readiness` now returns HTTP 503 until startup data is ready and agents are registered.
- `/webhook` no longer leaks raw internal exception text in generic 500 responses.
- Added regression tests for readiness, health probe behavior, webhook generic errors, and startup loader readiness semantics.
- Updated architecture and quickstart docs to match the live endpoint contract.
```

## Review Gates

- Do not merge if `tests/test_startup_data_loader.py` or `tests/test_main.py`
  fail.
- Do not merge if `/readiness` can still return `200` while
  `startup_loader.is_ready()` is false.
- Do not merge if `/health` still calls translation providers or other remote
  dependencies.
- Do not merge if webhook generic 500 responses still include raw exception
  text.
- Do not merge if the docs still describe `/readiness` as always available or
  `/health` as a dependency check.

## Deployment Notes

- This plan changes operational semantics, not business logic. Deploy normally
  after tests pass.
- Notify anyone using orchestration probes that `/readiness` may now return
  `503` during startup, which is the intended contract.
- If external monitors were scraping `/health` for provider connectivity, point
  them to a separate diagnostic workflow rather than re-expanding `/health`.

## Self-Review

- Coverage: this plan addresses the three highest-priority runtime findings
  from the review and adds direct tests for each changed behavior.
- Order: readiness helper first, endpoint contract second, health and webhook
  slices third, docs last.
- Specificity: all file paths, commands, and expected outcomes are explicit.
- Testability: every behavior change starts with a failing test and ends with a
  focused rerun before broader verification.
- Scope: this plan intentionally excludes the broader DI refactor and repo-wide
  coverage debt.
