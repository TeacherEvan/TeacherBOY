# Flexible Vision API + Log/Storage Glitch Remediation — Implementation Plan (Enhanced)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Agent:** Fenrie 🐺 (solo; no Anti-Gravity / external agent collaboration in this build)
> **Enhanced sub-skills invoked:** writing-plans-enhanced + surgical-implementation (task gates, verification per phase) + subagent-driven-development (optional execution mode)
> **Verification mode:** Mixed — Test (pytest) + Transform (HF dataset tree & run-log content before/after) + Browser-observable (live HF Space HTTP endpoints via curl)
> **Spec:** `docs/investigation-notes/vision-plan-2026-09-17.md` (Recommendation 2: build a JSON vision endpoint), `docs/recommendations.md` (R2), `AGENTS.md` (project constraints), plus the 2026-09-22 log investigation summary below.
> **Anti-Gravity boundary (if applicable):** N/A for the build itself. If this plan is ever shared with an external agent, share only repo files listed here — never `.env` contents, HF tokens, Space secret values, LINE user IDs, or chat content. All secrets stay in the HF Space's own settings.

**Goal:** Turn the LINE-only bot into a token-protected, generic image-analysis webhook API (`/api/v1/analyze`) that any of Evan's other projects can call to scrape receipts, articles, news, and general text — while fixing the concrete glitches found in the live HF Space logs (log spam, a leaked API key in log lines, a blocked RSS feed, corrupted HF dataset paths).

**Architecture:** Add a thin, additive HTTP layer (`src/api/external_vision.py`) that reuses the existing provider-priority vision fallback (`chat_completion_with_vision_fallback` in `src/utils/llm_fallback.py`, Gemini first). Task → prompt mapping lives in a new `src/services/external_vision_service.py`; receipts reuse the proven `RECEIPT_SCRAPE_PROMPT` + `gemini_text_to_ocr_payload`; article/news ask the model for strict JSON and parse it leniently. Auth is a Bearer token (new `EXTERNAL_API_TOKEN`, falling back to `BUDGETBOSS_SYNC_TOKEN` so it works today). Glitch fixes are small and independent: log-noise/secret-leak control, graceful RSS degradation, HF dataset pollution purge + upload-time ignore guard, and landing the two in-flight fixes already sitting uncommitted in the working tree.

**Tech Stack:** Python 3.11, FastAPI 0.109.1, pydantic 2.x / pydantic-settings 2.1.0, httpx 0.25.2, pytest 7.4.3 + pytest-asyncio 0.21.1, ruff 0.4.8, huggingface-hub 0.23.0, Docker → HuggingFace Space `EvilEvan/TeacherBOY` (public Space, private datasets), GitHub Actions CI/CD.

## Global Constraints

- **NEVER use the Maton AI API key in this project** (AGENTS.md). Nothing in this plan touches Maton.
- **LLM/vision fallback chain stays Gemini-first** (`settings.get_llm_provider_priority()`, default `gemini`); other providers are fallbacks only.
- **Tests mock all external APIs.** No real keys needed; `LINE_CHANNEL_SECRET` / `LINE_CHANNEL_ACCESS_TOKEN` are set by `tests/conftest.py` already.
- **Ruff 0.4.8 gates everything** on push to main: `ruff check src/ tests/` and `ruff format --check src/ tests/` (line-length 127, double quotes). Mypy is non-blocking (`|| true`).
- **Deploy path:** push to `origin/main` → GitHub Actions (`ci.yml` deploy job + `huggingface_sync.yml`, gated by repo variable `ENABLE_HF_SYNC == 'true'`) force-pushes to the HF Space. The Space SHA must equal the pushed commit — verify via the HF API.
- **Secrets never appear in logs, docs, or commits.** New code must not log image bytes, tokens, or full provider URLs.
- **HF repo IDs must stay in the `EvilEvan/teacherboy-*` namespace** (config validator).
- **Line length 127 / style:** match neighbouring files; type hints; `from src.config import settings` pattern.
- Image size accepted by the new API: default **6 MB decoded** (configurable). Per-IP rate limit default **30 req/min** (configurable). Analysis deadline default **60 s** (configurable).

---

## Part 0 — What the logs actually said (evidence for Part A tasks)

Captured 2026-09-22 from `https://huggingface.co/api/spaces/EvilEvan/TeacherBOY/logs/run` (195 KB stream, 968 parsed log lines) and `/logs/build`:

| # | Finding | Evidence |
|---|---|---|
| F1 | **76 % of run-log lines are third-party DEBUG noise** (unusable production logs) | 739 DEBUG / 189 INFO / 6 WARN+ERR. Top loggers: `hpack.hpack` 439, `filelock` 116, `httpcore.*` 140, `httpx` 11 |
| F2 | **Exchange-rate API key leaks into log lines** via httpx INFO request logging | `httpx - INFO - HTTP Request: GET https://v6.exchangerate-api.com/v6/<KEY>/latest/THB "HTTP/2 200 OK"` (source: `news_data_service.py:566` builds the URL with the key in the path) |
| F3 | **Bangkok Post RSS is 451-blocked from the Space** and logged as ERROR + traceback on every news request | `news_data_service.py:277 - 📰 RSS parse error for .../thailand.xml: Client error '451 Unavailable For Legal Reasons'` at 2026-09-22 13:03:56 |
| F4 | **Tracing middleware warning at startup** — already fixed in the uncommitted working tree, not deployed | `tracing.py:147 - ⚠️ Tracing setup failed: Cannot add middleware after an application has started` (2026-09-20). Local diff moves `setup_tracing(app, settings)` to module scope before `lifespan` (main.py) |
| F5 | **HF dataset pollution**: `teacherBOY-memory` contains a deep `.cache/huggingface/download/...` tree and 6 nested `conversations/conversations/*.json` files; loader skips them with a purge warning; **no upload-side guard exists** | HF API tree: 90+ cache paths; `hf_storage_mixin.py:200` warning "Skipping 6 nested/corrupted file(s)… Purge them from the HF dataset" |
| F6 | **Two in-flight fixes uncommitted** (tracing; deprecated `local_dir_use_symlinks` args for huggingface-hub 0.23) | `git status`: modified `src/main.py`, `src/services/document_memory_service.py`, `src/services/hf_storage_mixin.py` |
| F7 | **Junk files committed at repo root** (`=2.100.0,`, `=42.0.0`, `diff.txt`, `form_translation_code.txt`, `temp_handler_code.txt`) | `git ls-files` confirms tracked |
| F8 | **No external vision endpoint exists** — the Space is a LINE app only; previous investigation flagged this as the HIGH gap (R2) | `/webhook` (LINE-signature only) and `/receipt/scan` (Budget Boss only) are the only POST routes in `src/main.py` |
| F9 | Minor smells (backlog, not blockers): `ReceiptAgent._is_user_linked` is a TODO that denies when enforced; webhook per-IP dict grows per unique IP; `/receipt/scan` defined after `__main__` guard (works, cosmetic) | `receipt_agent.py:72-82`, `main.py:1404-1419`, `main.py:1657` |

Positive findings (no action): Space RUNNING on `cpu-basic` with a persistent bucket volume; deployed SHA `477c557` == local `main` HEAD; build log clean (cached layers, ~20 s); message handling end-to-end verified in logs (text, image analysis via `gemini-2.5-flash`, calendar scrape, news flow — all successful).

**The One Change (Evan's request):** a flexible, token-protected image-analysis API the other projects can webhook into — receipts, articles, news, OCR, general Q&A — returning structured JSON. Everything in Part A is a small prerequisite/hygiene fix with direct log evidence.

---

## File Structure (what this plan creates / modifies)

**Create:**
- `src/utils/logging_hygiene.py` — caps noisy third-party loggers at WARNING (F1, F2).
- `src/utils/ip_rate_limiter.py` — tiny stdlib per-IP sliding-window limiter (used by the new API).
- `src/services/external_vision_service.py` — task→prompt registry + `analyze_image_task()`.
- `src/api/__init__.py`, `src/api/external_vision.py` — the `/api/v1` router (auth, rate limit, image resolution, endpoints).
- `scripts/purge_hf_dataset_pollution.py` — one-shot cleanup for F5 (dry-run by default).
- `docs/EXTERNAL_API.md` — consumer docs for other projects.
- Tests: `tests/test_logging_hygiene.py`, `tests/test_news_rss_fallback.py`, `tests/test_hf_storage_guard.py`, `tests/services/test_llm_fallback_provider_meta.py`, `tests/services/test_external_vision_service.py`, `tests/test_external_vision_api.py`, plus small additions to `tests/test_config.py` and `tests/test_main.py`.

**Modify:**
- `src/main.py` — call `silence_noisy_loggers()`; include the new router; `/health` gains an `external_api` status flag.
- `src/config.py` — External Vision API settings block + helpers.
- `src/utils/llm_fallback.py` — provider-aware vision variant (keeps old function signature intact).
- `src/services/news_data_service.py` — RSS HTTP errors degrade to WARNING without traceback (F3).
- `src/services/hf_storage_mixin.py` — upload-time ignore guard + stale-`.cache` heal (F5).
- `README.md`, `docs/recommendations.md` — doc sync.

---

# Part A — Glitch fixes from the live logs

### Task 0: Local test environment bootstrap (one-time)

**Files:** none in repo (creates `.venv/`, which is already git-ignored).

**Interfaces:**
- Produces: an activated venv where `pytest`, `ruff`, and `src.*` imports work.

- [ ] **Step 1: Create the venv (mirrors CI)**

```bash
cd /home/leandi-duplessis/github/workspaces/TeacherBOY
~/.local/bin/python3.11 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -r requirements.txt
.venv/bin/pip install pytest==7.4.3 pytest-asyncio==0.21.1 ruff==0.4.8
```

Note: `requirements.txt` includes `easyocr` (pulls torch, sizeable download) — that mirrors the CI unit-test job exactly, so local results match CI. Expect the install to take a while; it only needs doing once.

- [ ] **Step 2: Activate and record the baseline**

```bash
. .venv/bin/activate
pytest -q 2>&1 | tail -20
```

Expected: suite runs; note pass/fail counts in the PR description. Known-independent failures (if any) must be recorded before this plan's changes begin — do not fix unrelated failures here.

- [ ] **Step 3: Verify ruff works**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/
```

Expected: clean (this is the state CI requires before every commit below).

> All later tasks assume `. .venv/bin/activate` has been run in the shell.

### Verify Visual & Transform Claims (Task 0)

- [ ] **Visual claim:** `python -c "import fastapi"` fails before, succeeds after; `pytest --version` prints 7.4.3.
- [ ] **Transform claim:** `.venv/` exists with installed packages.
- [ ] **Verification method:** the three commands above, output pasted into the task log.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 1: Land the in-flight fixes (tracing + huggingface-hub args)

**Files:**
- Modify (already modified in working tree): `src/main.py`, `src/services/document_memory_service.py`, `src/services/hf_storage_mixin.py`
- Test: `tests/test_main.py` (existing suite gates the change)

**Interfaces:**
- Consumes: nothing new.
- Produces: clean working tree; `setup_tracing(app, settings)` guaranteed to run at import time (module scope, before `lifespan`), so FastAPI middleware stack is still mutable. `hf_hub_download(...)` calls no longer pass the deprecated `local_dir_use_symlinks` argument (huggingface-hub is pinned to 0.23.0, where the argument is deprecated and re-expanding symlinks confused the sync folder).

- [ ] **Step 1: Review the pending diff once more**

```bash
git diff
```

Expected: exactly the 3-file diff already inspected (66 lines): `setup_tracing` moved out of `lifespan` to module scope, two `-        local_dir_use_symlinks=False,` deletions.

- [ ] **Step 2: Run the affected tests**

```bash
pytest tests/test_main.py tests/test_document_memory.py -v
```

Expected: all pass (the tracing change only affects middleware setup order; the hub arg removal is a no-op at runtime on 0.23.0).

- [ ] **Step 3: Lint gate**

```bash
ruff check src/main.py src/services/document_memory_service.py src/services/hf_storage_mixin.py
ruff format --check src/main.py src/services/document_memory_service.py src/services/hf_storage_mixin.py
```

Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add src/main.py src/services/document_memory_service.py src/services/hf_storage_mixin.py
git commit -m "fix(startup): run tracing setup at module scope; drop deprecated huggingface-hub symlink arg"
```

### Verify Visual & Transform Claims (Task 1)

- [ ] **Visual claim:** next deploy's run log contains **no** "Cannot add middleware after an application has started" warning at startup.
- [ ] **Transform claim:** `git status` clean for those 3 files; `git log --oneline -1` shows the new commit.
- [ ] **Verification method:** `git status`, `pytest` output; post-deploy re-pull of `/logs/run` (Task 12).
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 2: Stop the log floods and the key leak (F1 + F2)

**Files:**
- Create: `src/utils/logging_hygiene.py`
- Create: `tests/test_logging_hygiene.py`
- Modify: `src/main.py` (call it right after `logging.basicConfig`)

**Interfaces:**
- Produces: `NOISY_LOGGERS: tuple[str, ...]` and `silence_noisy_loggers() -> None`. `main.py` calls it at import time. Root/app log level behaviour is unchanged (`settings.debug` still increases app verbosity); only third-party loggers are capped at WARNING. This is what stops `httpx` from writing full request URLs (the exchange-rate key path) into public run logs.

- [ ] **Step 1: Write the failing test**

`tests/test_logging_hygiene.py`:

```python
"""Third-party loggers must never flood (or leak URLs into) production logs."""

import logging

from src.utils.logging_hygiene import NOISY_LOGGERS, silence_noisy_loggers


def test_noisy_loggers_capped_at_warning():
    silence_noisy_loggers()
    for name in NOISY_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING


def test_httpx_cannot_emit_info_request_lines():
    silence_noisy_loggers()
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_logging_hygiene.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'src.utils.logging_hygiene'`.

- [ ] **Step 3: Implement `src/utils/logging_hygiene.py`**

```python
"""Log-noise control for third-party libraries.

The HF Space runs with DEBUG enabled in production, which floods the run log
with per-byte hpack/httpcore traces (739 of 968 captured lines on 2026-09-22)
and, worse, httpx's INFO request lines that embed full URLs — including API
keys passed as path segments (e.g. exchangerate-api v6). These loggers are
capped at WARNING regardless of the app-level log level; application loggers
keep their configured verbosity.
"""

import logging

NOISY_LOGGERS: tuple[str, ...] = (
    "hpack",
    "hpack.hpack",
    "httpcore",
    "httpcore.http2",
    "httpcore.http11",
    "httpcore.connection",
    "httpx",
    "filelock",
    "urllib3",
)


def silence_noisy_loggers() -> None:
    """Cap third-party loggers at WARNING so run logs stay readable and secret-free."""
    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
```

- [ ] **Step 4: Wire it into `src/main.py`**

After the `logger = logging.getLogger(__name__)` line (below the existing `logging.basicConfig(...)` block at the top of the file), add:

```python
from src.utils.logging_hygiene import silence_noisy_loggers

# Keep production run logs readable (and free of key-bearing URLs): the
# third-party loggers listed in logging_hygiene are capped at WARNING.
silence_noisy_loggers()
```

Place the import with the other `src.utils` imports and the call immediately after the module logger is created.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_logging_hygiene.py tests/test_main.py -v
```

Expected: PASS. (`test_main` exercises the import path end-to-end.)

- [ ] **Step 6: Commit**

```bash
git add src/utils/logging_hygiene.py tests/test_logging_hygiene.py src/main.py
git commit -m "fix(logging): cap third-party loggers at WARNING; stop URL/key leakage into run logs"
```

### Verify Visual & Transform Claims (Task 2)

- [ ] **Visual claim:** the next deployed run log contains zero `hpack` / `filelock` / `httpcore` lines and no `v6/` exchange-rate URL.
- [ ] **Transform claim:** 195 KB → (expected) a few KB of app-level logs for the same traffic window.
- [ ] **Verification method:** re-pull `/logs/run` after deploy (Task 12 step "log check"), grep for `hpack|filelock|v6/`.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 3: RSS 451/4xx degrades quietly (F3)

**Files:**
- Modify: `src/services/news_data_service.py` (`_parse_rss_feed`, around line 249)
- Create: `tests/test_news_rss_fallback.py`

**Interfaces:**
- Produces: `_parse_rss_feed(url)` returns the fallback item list on any failure; HTTP-status failures log at WARNING without traceback, unexpected parse failures stay at ERROR with traceback. `NewsDataService._rss_fallback_items()` is a new static helper.

- [ ] **Step 1: Write the failing test**

`tests/test_news_rss_fallback.py`:

```python
"""HTTP-status RSS failures degrade quietly; malformed feeds stay loud."""

import httpx
import pytest

from src.services.news_data_service import NewsDataService


class _RaisingClient:
    def __init__(self, status_code: int):
        self._status = status_code

    async def get(self, url, timeout=None, follow_redirects=None):
        request = httpx.Request("GET", url)
        response = httpx.Response(self._status, request=request)
        raise httpx.HTTPStatusError("blocked", request=request, response=response)


@pytest.mark.asyncio
async def test_rss_http_error_logs_warning_not_error(caplog):
    service = NewsDataService(http_client=None, news_api_key=None)
    service.client = _RaisingClient(451)

    with caplog.at_level("WARNING"):
        items = await service._parse_rss_feed("https://www.bangkokpost.com/rss/data/thailand.xml")

    assert items[0]["title"] == "News unavailable"
    assert any("RSS feed unavailable (HTTP 451)" in record.message for record in caplog.records)
    assert not any(record.levelname == "ERROR" for record in caplog.records)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_news_rss_fallback.py -v
```

Expected: FAIL — current code logs ERROR ("RSS parse error …") and there is no "RSS feed unavailable (HTTP 451)" message.

- [ ] **Step 3: Implement** — replace the `except` block in `_parse_rss_feed`:

```python
        except httpx.HTTPStatusError as e:
            # Feed-side blocks (e.g. Bangkok Post returns 451 "Unavailable For
            # Legal Reasons" to HF Space egress) are expected degradation, not
            # application errors: log once, quietly, and serve the fallback.
            logger.warning(f"📰 RSS feed unavailable (HTTP {e.response.status_code}) for {url}")
            return self._rss_fallback_items()
        except Exception as e:
            logger.error(f"📰 RSS parse error for {url}: {e}", exc_info=True)
            return self._rss_fallback_items()
```

And add below `_parse_rss_feed`:

```python
    @staticmethod
    def _rss_fallback_items() -> list[dict[str, str]]:
        """Neutral fallback when a feed cannot be fetched or parsed."""
        return [
            {"title": "News unavailable", "url": ""},
            {"title": "Visit Bangkok Post", "url": "https://www.bangkokpost.com"},
        ]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_news_rss_fallback.py tests/test_news_agent.py -v
```

Expected: PASS (existing news tests unaffected — fallback shape is unchanged).

- [ ] **Step 5: Commit**

```bash
git add src/services/news_data_service.py tests/test_news_rss_fallback.py
git commit -m "fix(news): treat blocked RSS feeds (HTTP 4xx/451) as quiet degradation"
```

### Verify Visual & Transform Claims (Task 3)

- [ ] **Visual claim:** post-deploy run logs show `📰 RSS feed unavailable (HTTP 451)` at WARNING and no traceback block for the feed.
- [ ] **Transform claim:** news flow still returns headlines for other sources; fallback list only appears when the fetch fails.
- [ ] **Verification method:** `/logs/run` grep after a `/news`-triggering message (Task 12); pytest above.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 4: HF dataset pollution — purge + upload guard (F5)

**Files:**
- Modify: `src/services/hf_storage_mixin.py` (add `_heal_stale_cache()`, call it in `_setup_hf_storage`, add `ignore_patterns` to `CommitScheduler`)
- Create: `scripts/purge_hf_dataset_pollution.py`
- Create: `tests/test_hf_storage_guard.py`

**Interfaces:**
- Produces: `HFStorageMixin._heal_stale_cache() -> None`; `CommitScheduler(..., ignore_patterns=[".cache/*", "*.tmp"])`; CLI script `scripts/purge_hf_dataset_pollution.py` (`--apply` to delete; dry-run default; exits non-zero if bad files remain).

- [ ] **Step 1: Write the failing test**

`tests/test_hf_storage_guard.py`:

```python
"""Legacy HF download caches inside the sync folder must be healed on startup."""

from src.services.hf_storage_mixin import HFStorageMixin


class _DummyStorage(HFStorageMixin):
    pass


def test_stale_cache_is_removed_from_sync_folder(tmp_path):
    dummy = _DummyStorage()
    dummy._hf_sync_folder = tmp_path / "conversations"
    stale = dummy._hf_sync_folder / ".cache" / "huggingface" / "download"
    stale.mkdir(parents=True)
    (stale / "junk.metadata").write_text("x")

    dummy._heal_stale_cache()

    assert not (dummy._hf_sync_folder / ".cache").exists()


def test_heal_is_a_noop_when_no_cache_exists(tmp_path):
    dummy = _DummyStorage()
    dummy._hf_sync_folder = tmp_path / "clean"
    dummy._hf_sync_folder.mkdir()
    dummy._heal_stale_cache()  # must not raise
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_hf_storage_guard.py -v
```

Expected: FAIL — `AttributeError: 'HFStorageMixin' object has no attribute '_heal_stale_cache'`.

- [ ] **Step 3: Implement the mixin changes**

In `src/services/hf_storage_mixin.py`:

Add this method (below `stop_hf_storage`):

```python
    def _heal_stale_cache(self) -> None:
        """Remove legacy `.cache/` dirs from the sync folder.

        Older releases downloaded HF files with the cache inside the sync
        folder; CommitScheduler then re-uploaded it, growing repo paths like
        "conversations/.cache/huggingface/download/..." (purged 2026-09-22).
        """
        if self._hf_sync_folder is None:
            return
        stale = self._hf_sync_folder / ".cache"
        if stale.exists():
            import shutil

            shutil.rmtree(stale, ignore_errors=True)
            logger.info(f"Removed stale HF download cache at {stale}")
```

In `_setup_hf_storage`, right after `self._hf_sync_folder.mkdir(parents=True, exist_ok=True)`, add:

```python
            self._heal_stale_cache()
```

And change the CommitScheduler creation to include:

```python
            self._commit_scheduler = CommitScheduler(
                repo_id=self.hf_repo_id,
                repo_type=self.hf_repo_type,
                folder_path=str(self._hf_sync_folder),
                every=self.hf_sync_interval,
                token=self.hf_token,
                private=self.hf_private,
                squash_history=self.hf_squash_history,
                path_in_repo=self.hf_path_in_repo,
                ignore_patterns=[".cache/*", "*.tmp", "*.metadata"],
            )
```

(`filter_repo_objects` uses fnmatch-style patterns where `*` also crosses `/`, so `.cache/*` covers the whole nested tree.)

- [ ] **Step 4: Write the purge script**

`scripts/purge_hf_dataset_pollution.py`:

```python
#!/usr/bin/env python3
"""One-shot purge of legacy HF dataset pollution (nested conversations/ + .cache/).

Found 2026-09-22 in EvilEvan/teacherBOY-memory: ~90 `.cache/huggingface/...`
entries under conversations/ and 6 nested conversations/conversations/*.json
files re-uploaded by very old releases. New uploads are guarded by
HFStorageMixin.ignore_patterns; this script removes the legacy backlog.

Usage:
    HF_TOKEN=hf_xxx python3 scripts/purge_hf_dataset_pollution.py            # dry-run
    HF_TOKEN=hf_xxx python3 scripts/purge_hf_dataset_pollution.py --apply    # delete
"""

import argparse
import os
import sys

from huggingface_hub import CommitOperationDelete, HfApi

REPO_ID = os.environ.get("PURGE_REPO_ID", "EvilEvan/teacherBOY-memory")
REPO_TYPE = "dataset"
BAD_PREFIXES = ("conversations/conversations/", "conversations/.cache/")
BATCH = 100


def find_bad_files(api: HfApi) -> list[str]:
    files = api.list_repo_files(REPO_ID, repo_type=REPO_TYPE)
    bad = [f for f in files if f.startswith(BAD_PREFIXES) or ".cache/huggingface" in f]
    print(f"{len(files)} files in {REPO_ID}; {len(bad)} need purging")
    for f in bad[:10]:
        print("  -", f)
    return bad


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="Actually delete (default: dry-run)")
    args = parser.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        print("HF_TOKEN is required", file=sys.stderr)
        return 2

    api = HfApi(token=token)
    bad = find_bad_files(api)
    if not bad:
        print("Nothing to purge. ✅")
        return 0

    if not args.apply:
        print("Dry-run only; re-run with --apply to delete.")
        return 0

    for i in range(0, len(bad), BATCH):
        operations = [CommitOperationDelete(path_in_repo=f) for f in bad[i : i + BATCH]]
        api.create_commit(
            repo_id=REPO_ID,
            repo_type=REPO_TYPE,
            operations=operations,
            commit_message=f"chore: purge legacy nested/cache pollution (batch {i // BATCH + 1})",
        )
        print(f"deleted {i + len(operations)}/{len(bad)}")

    remaining = find_bad_files(api)
    if remaining:
        print(f"❌ {len(remaining)} bad files still remain", file=sys.stderr)
        return 1
    print("✅ Purge complete; dataset tree is clean.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests + dry-run the script**

```bash
pytest tests/test_hf_storage_guard.py -v
HF_TOKEN=$HF_TOKEN python3 scripts/purge_hf_dataset_pollution.py
```

Expected: tests PASS; dry-run prints the ~96 bad files and exits 0 without deleting.

- [ ] **Step 6: Apply the purge and verify the tree**

```bash
HF_TOKEN=$HF_TOKEN python3 scripts/purge_hf_dataset_pollution.py --apply
python3 - <<'EOF'
import json, urllib.request, os
req = urllib.request.Request(
    "https://huggingface.co/api/datasets/EvilEvan/teacherBOY-memory/tree/main?recursive=true",
    headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
)
tree = json.load(urllib.request.urlopen(req))
nested = [x["path"] for x in tree if "conversations/conversations" in x["path"]]
print("nested remaining:", nested)
EOF
```

Expected: `remaining bad files: 0`; nested list empty. Save both outputs as the transform evidence.

- [ ] **Step 7: Commit**

```bash
git add src/services/hf_storage_mixin.py scripts/purge_hf_dataset_pollution.py tests/test_hf_storage_guard.py
git commit -m "fix(storage): guard HF uploads against cache dirs; add dataset pollution purge script"
```

### Verify Visual & Transform Claims (Task 4)

- [ ] **Visual claim:** HF dataset `teacherBOY-memory` tree page no longer shows `.cache/` or `conversations/conversations/` entries.
- [ ] **Transform claim:** bad-file count goes ~96 → 0 (script output before/after); next CommitScheduler sync uploads no `.cache` files.
- [ ] **Verification method:** the two script runs above and the API tree re-list.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

# Part B — The flexible vision API

### Task 5: Config block for the External Vision API

**Files:**
- Modify: `src/config.py` (new settings block after the Budget Boss block, ~line 1131)
- Test: `tests/test_config.py` (append)

**Interfaces:**
- Produces: `settings.external_api_enabled`, `settings.external_api_token`, `settings.external_api_rate_limit_per_minute`, `settings.external_api_max_image_mb`, `settings.external_api_timeout_seconds`, `settings.external_api_image_hosts` + helpers `get_external_api_token() -> str | None` and `get_external_api_image_hosts() -> set[str]`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_config.py`)

```python
def test_external_api_token_falls_back_to_budgetboss_token(monkeypatch):
    from src.config import Settings

    monkeypatch.setenv("BUDGETBOSS_SYNC_TOKEN", "bb-token")
    monkeypatch.delenv("EXTERNAL_API_TOKEN", raising=False)
    assert Settings().get_external_api_token() == "bb-token"

    monkeypatch.setenv("EXTERNAL_API_TOKEN", "ext-token")
    assert Settings().get_external_api_token() == "ext-token"


def test_external_api_image_hosts_parses_extras(monkeypatch):
    from src.config import Settings

    monkeypatch.setenv("EXTERNAL_API_IMAGE_HOSTS", "cdn.example.com, img.example.org")
    assert Settings().get_external_api_image_hosts() == {"cdn.example.com", "img.example.org"}


def test_external_api_defaults():
    from src.config import Settings

    s = Settings()
    assert s.external_api_enabled is True
    assert s.external_api_rate_limit_per_minute == 30
    assert s.external_api_max_image_mb == 6.0
    assert s.external_api_timeout_seconds == 60.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config.py -v
```

Expected: FAIL — helper methods do not exist yet.

- [ ] **Step 3: Implement in `src/config.py`** (insert after `receipt_agent_enabled`, before `is_any_vision_provider_configured`)

```python
    # ============================================================================
    # External Vision API Configuration (token-protected, for other projects)
    # ============================================================================
    external_api_enabled: bool = Field(
        default=True,
        description="Enable the token-protected /api/v1 analysis API for external projects.",
    )
    external_api_token: str | None = Field(
        default=None,
        description=(
            "Bearer token required by /api/v1 endpoints. Falls back to "
            "BUDGETBOSS_SYNC_TOKEN when unset so existing projects keep working."
        ),
        validation_alias=AliasChoices("EXTERNAL_API_TOKEN"),
    )
    external_api_rate_limit_per_minute: int = Field(
        default=30,
        ge=1,
        le=600,
        description="Per-IP request budget for /api/v1 endpoints (sliding 60s window).",
    )
    external_api_max_image_mb: float = Field(
        default=6.0,
        ge=0.1,
        le=20.0,
        description="Maximum accepted decoded image size for /api/v1 requests.",
    )
    external_api_timeout_seconds: float = Field(
        default=60.0,
        ge=5.0,
        le=180.0,
        description="Hard deadline for a single /api/v1 analysis call.",
    )
    external_api_image_hosts: str | None = Field(
        default=None,
        description="Extra comma-separated hosts allowed for image.url fetches (SSRF allowlist extension).",
    )

    def get_external_api_token(self) -> str | None:
        """Token that /api/v1 endpoints accept (EXTERNAL_API_TOKEN, else Budget Boss token)."""
        return self.external_api_token or self.budgetboss_sync_token

    def get_external_api_image_hosts(self) -> set[str]:
        """Extra hosts (beyond utils.ssrf_guard.DEFAULT_ALLOWED_HOSTS) allowed for image.url fetches."""
        return {h.strip().lower() for h in (self.external_api_image_hosts or "").split(",") if h.strip()}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_config.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat(config): external vision API settings (token, limits, image host allowlist)"
```

### Verify Visual & Transform Claims (Task 5)

- [ ] **Visual claim:** n/a (config only).
- [ ] **Transform claim:** `Settings().get_external_api_token()` returns the fallback chain; `/health` will surface it later (Task 10).
- [ ] **Verification method:** pytest output above.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 6: Provider-aware vision fallback

**Files:**
- Modify: `src/utils/llm_fallback.py`
- Create: `tests/services/test_llm_fallback_provider_meta.py`

**Interfaces:**
- Produces: `chat_completion_with_vision_fallback_ex(messages, *, model=None, temperature=0.7, max_tokens=None) -> tuple[str, str] | None` returning `(text, provider)`. The existing `chat_completion_with_vision_fallback(...) -> str | None` remains and delegates to it — all current call sites (profiler, image analyzer, receipt agent, receipt bridge) keep their exact behaviour.

- [ ] **Step 1: Write the failing tests**

`tests/services/test_llm_fallback_provider_meta.py`:

```python
"""Provider-aware vision fallback: reports who actually served the call."""

import types

import pytest

from src.utils import llm_fallback


def _stub_priority(monkeypatch, providers):
    """Swap the module-level settings for a stub (pydantic models reject foreign attrs)."""
    monkeypatch.setattr(llm_fallback, "settings", types.SimpleNamespace(get_llm_provider_priority=lambda: providers))


@pytest.mark.asyncio
async def test_vision_fallback_ex_reports_serving_provider(monkeypatch):
    _stub_priority(monkeypatch, ["gemini", "openrouter"])
    monkeypatch.setattr(llm_fallback.gemini_service, "is_vision_configured", lambda: True)

    async def fake_gemini(**kwargs):
        return "hello from gemini"

    monkeypatch.setattr(llm_fallback.gemini_service, "chat_completion_with_vision", fake_gemini)
    monkeypatch.setattr(llm_fallback.openrouter_service, "is_configured", lambda: False)

    result = await llm_fallback.chat_completion_with_vision_fallback_ex(messages=[{"role": "user", "content": "hi"}])
    assert result == ("hello from gemini", "gemini")


@pytest.mark.asyncio
async def test_vision_fallback_ex_falls_through_to_next_provider(monkeypatch):
    _stub_priority(monkeypatch, ["gemini", "openrouter"])
    monkeypatch.setattr(llm_fallback.gemini_service, "is_vision_configured", lambda: True)

    async def fake_gemini(**kwargs):
        return None

    async def fake_openrouter(**kwargs):
        return "from openrouter"

    monkeypatch.setattr(llm_fallback.gemini_service, "chat_completion_with_vision", fake_gemini)
    monkeypatch.setattr(llm_fallback.openrouter_service, "is_configured", lambda: True)
    monkeypatch.setattr(llm_fallback.openrouter_service, "chat_completion_with_vision", fake_openrouter)

    result = await llm_fallback.chat_completion_with_vision_fallback_ex(messages=[{"role": "user", "content": "hi"}])
    assert result == ("from openrouter", "openrouter")


@pytest.mark.asyncio
async def test_legacy_string_helper_still_returns_text(monkeypatch):
    _stub_priority(monkeypatch, ["gemini"])
    monkeypatch.setattr(llm_fallback.gemini_service, "is_vision_configured", lambda: True)

    async def fake_gemini(**kwargs):
        return "text only"

    monkeypatch.setattr(llm_fallback.gemini_service, "chat_completion_with_vision", fake_gemini)

    assert await llm_fallback.chat_completion_with_vision_fallback(messages=[{"role": "user", "content": "hi"}]) == "text only"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/services/test_llm_fallback_provider_meta.py -v
```

Expected: FAIL — `chat_completion_with_vision_fallback_ex` does not exist.

- [ ] **Step 3: Implement** — replace the final function in `src/utils/llm_fallback.py` with the pair:

```python
async def chat_completion_with_vision_fallback_ex(
    messages: VisionMessages,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> tuple[str, str] | None:
    """Vision completion that also reports which provider served it.

    Returns (text, provider) for the first provider in priority order that
    returns content, or None when every configured provider failed.
    """
    priority = settings.get_llm_provider_priority()

    for provider in priority:
        result = await _run_one_vision_provider(
            provider=provider,
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        if result:
            return result, provider

    return None


async def chat_completion_with_vision_fallback(
    messages: VisionMessages,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
) -> str | None:
    """Provider-priority vision completion (text only; legacy signature).

    Tries vision-capable providers in the configured priority order
    (`settings.get_llm_provider_priority()`, default: Gemini first). A provider
    can skip vision by leaving `chat_completion_with_vision(...)` unimplemented
    or returning None.
    """
    result = await chat_completion_with_vision_fallback_ex(
        messages,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return result[0] if result else None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/services/test_llm_fallback_provider_meta.py tests/test_image_analyzer_debrief_routing.py tests/services/test_receipt_bridge_app.py -v
```

Expected: PASS — including the existing call sites' tests (legacy behaviour preserved).

- [ ] **Step 5: Commit**

```bash
git add src/utils/llm_fallback.py tests/services/test_llm_fallback_provider_meta.py
git commit -m "feat(vision): provider-aware vision fallback variant; keep legacy string helper"
```

### Verify Visual & Transform Claims (Task 6)

- [ ] **Visual claim:** n/a (library change; no behaviour change for LINE agents).
- [ ] **Transform claim:** service responses (Task 9) can now name the serving provider.
- [ ] **Verification method:** pytest above.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 7: `external_vision_service` — task registry + runner

**Files:**
- Create: `src/services/external_vision_service.py`
- Create: `tests/services/test_external_vision_service.py`

**Interfaces:**
- Consumes: `chat_completion_with_vision_fallback_ex` (Task 6), `RECEIPT_SCRAPE_PROMPT` (from `src.agents.receipt_agent`), `gemini_text_to_ocr_payload` (from `src.services.receipt_bridge`).
- Produces:
  - `SUPPORTED_TASKS: tuple[str, ...]` = `("receipt", "article", "news", "ocr", "general")`
  - `build_task_prompt(task: str, custom_prompt: str | None) -> str`
  - `parse_structured_json(text: str) -> dict | None`
  - `async analyze_image_task(*, image_data_url: str, task: str, prompt: str | None = None, country_hint: str = "TH", max_tokens: int = 2000) -> dict` → `{"task", "text", "structured", "ocr", "provider", "latency_ms"}`. Raises `ValueError` (unknown task) and `RuntimeError` (all providers failed).

- [ ] **Step 1: Write the failing tests**

`tests/services/test_external_vision_service.py`:

```python
"""Task prompts, lenient JSON parsing, and result shaping for the external API."""

import pytest

from src.services import external_vision_service as svc


def test_parse_structured_json_handles_code_fences():
    payload = '```json\n{"title": "Hello", "key_points": ["a"]}\n```'
    assert svc.parse_structured_json(payload) == {"title": "Hello", "key_points": ["a"]}


def test_parse_structured_json_returns_none_on_garbage():
    assert svc.parse_structured_json("no json here") is None
    assert svc.parse_structured_json("") is None


def test_build_task_prompt_uses_custom_prompt_when_given():
    assert svc.build_task_prompt("ocr", "Read only the totals.") == "Read only the totals."
    assert svc.build_task_prompt("receipt", None).startswith("Extract ALL text from this receipt")


def test_build_task_prompt_rejects_unknown_task():
    with pytest.raises(ValueError):
        svc.build_task_prompt("nope", None)


@pytest.mark.asyncio
async def test_receipt_task_returns_ocr_payload(monkeypatch):
    async def fake_fallback(messages, **kwargs):
        return ("COFFEE 45 THB\nTOTAL 45", "gemini")

    monkeypatch.setattr(svc, "chat_completion_with_vision_fallback_ex", fake_fallback)

    out = await svc.analyze_image_task(image_data_url="data:image/png;base64,abc", task="receipt")

    assert out["provider"] == "gemini"
    assert out["task"] == "receipt"
    assert out["ocr"]["engine"] == "gemini-vision@1"
    assert out["ocr"]["lines"][0]["text"] == "COFFEE 45 THB"


@pytest.mark.asyncio
async def test_article_task_parses_structured_json(monkeypatch):
    async def fake_fallback(messages, **kwargs):
        return ('{"title": "T", "key_points": ["k1"]}', "openrouter")

    monkeypatch.setattr(svc, "chat_completion_with_vision_fallback_ex", fake_fallback)

    out = await svc.analyze_image_task(image_data_url="data:image/png;base64,abc", task="article")

    assert out["structured"] == {"title": "T", "key_points": ["k1"]}
    assert out["provider"] == "openrouter"


@pytest.mark.asyncio
async def test_all_providers_failed_raises_runtime_error(monkeypatch):
    async def fake_fallback(messages, **kwargs):
        return None

    monkeypatch.setattr(svc, "chat_completion_with_vision_fallback_ex", fake_fallback)

    with pytest.raises(RuntimeError):
        await svc.analyze_image_task(image_data_url="data:image/png;base64,abc", task="ocr")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/services/test_external_vision_service.py -v
```

Expected: FAIL — module not found.

- [ ] **Step 3: Implement `src/services/external_vision_service.py`**

```python
"""Generic vision task runner for external projects (see docs/EXTERNAL_API.md).

One entry point — `analyze_image_task` — turns an image data URL plus a task
name into JSON-ready output. Prompts reuse the patterns already proven in the
LINE flows (receipt scrape prompt, literal OCR scrape) and add strict-JSON
prompts for article/news extraction, which are parsed leniently so a model
that wraps JSON in prose or code fences still yields structure.
"""

import json
import logging
import re
import time
from typing import Any

from src.agents.receipt_agent import RECEIPT_SCRAPE_PROMPT
from src.services.receipt_bridge import gemini_text_to_ocr_payload
from src.utils.llm_fallback import chat_completion_with_vision_fallback_ex

logger = logging.getLogger(__name__)

TASK_RECEIPT = "receipt"
TASK_ARTICLE = "article"
TASK_NEWS = "news"
TASK_OCR = "ocr"
TASK_GENERAL = "general"

SUPPORTED_TASKS: tuple[str, ...] = (TASK_RECEIPT, TASK_ARTICLE, TASK_NEWS, TASK_OCR, TASK_GENERAL)

OCR_PROMPT = (
    "Extract ALL text from this image. Return ONLY the text content found in the image. "
    "Include any text from signs, documents, receipts, screens, menus, labels, handwriting, etc. "
    "Preserve line breaks and layout as much as possible. "
    "If multiple languages are present, include all. "
    "Do not add explanations or analysis - just the extracted text."
)

ARTICLE_PROMPT = (
    "You are reading an image of an article, clipping, or document. "
    "Return STRICT JSON only (no prose, no code fences) with keys: "
    '"title" (string), "publication" (string or null), "date" (ISO date or null), '
    '"byline" (string or null), "summary" (string, max 120 words), '
    '"key_points" (array of 3-6 short strings), "language" (short code like "en" or "th"). '
    "If a field is not visible, use null and do not guess."
)

NEWS_PROMPT = (
    "You are reading an image of a news item (screenshot, clipping, or page). "
    "Return STRICT JSON only (no prose, no code fences) with keys: "
    '"headline" (string), "source" (string or null), "date" (ISO date or null), '
    '"top_facts" (array of 3-6 short strings), "why_it_matters" (string, max 60 words), '
    '"entities" (object with "people", "organizations", "locations" arrays), "language" (short code). '
    "Only include facts visible in the image; never speculate."
)

GENERAL_PROMPT = (
    "Describe this image accurately and answer any question the caller included. "
    "Be literal and factual; state uncertainty instead of guessing."
)

_TASK_PROMPTS: dict[str, str] = {
    TASK_OCR: OCR_PROMPT,
    TASK_RECEIPT: RECEIPT_SCRAPE_PROMPT,
    TASK_ARTICLE: ARTICLE_PROMPT,
    TASK_NEWS: NEWS_PROMPT,
    TASK_GENERAL: GENERAL_PROMPT,
}

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


def build_task_prompt(task: str, custom_prompt: str | None) -> str:
    """Resolve the prompt for a task; a custom prompt replaces the default entirely."""
    if custom_prompt and custom_prompt.strip():
        return custom_prompt.strip()
    if task not in _TASK_PROMPTS:
        raise ValueError(f"Unsupported task: {task}")
    return _TASK_PROMPTS[task]


def parse_structured_json(text: str) -> dict[str, Any] | None:
    """Leniently pull the first JSON object out of a model response."""
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.strip("`")
        candidate = candidate.removeprefix("json").strip()
    match = _JSON_BLOCK_RE.search(candidate)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


async def analyze_image_task(
    *,
    image_data_url: str,
    task: str,
    prompt: str | None = None,
    country_hint: str = "TH",
    max_tokens: int = 2000,
) -> dict[str, Any]:
    """Run one vision task and shape a JSON-ready result.

    Raises:
        ValueError: unknown task.
        RuntimeError: every configured vision provider failed.
    """
    effective_prompt = build_task_prompt(task, prompt)

    started = time.monotonic()
    result = await chat_completion_with_vision_fallback_ex(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": effective_prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
        temperature=0.1 if task in (TASK_OCR, TASK_RECEIPT) else 0.2,
        max_tokens=max_tokens,
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    if result is None:
        raise RuntimeError("All vision providers failed")

    text, provider = result
    payload: dict[str, Any] = {
        "task": task,
        "text": text,
        "structured": None,
        "ocr": None,
        "provider": provider,
        "latency_ms": latency_ms,
    }

    if task == TASK_RECEIPT:
        payload["ocr"] = gemini_text_to_ocr_payload(text, country_hint)
    elif task in (TASK_ARTICLE, TASK_NEWS):
        payload["structured"] = parse_structured_json(text)

    return payload
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/services/test_external_vision_service.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/services/external_vision_service.py tests/services/test_external_vision_service.py
git commit -m "feat(vision): external task runner (receipt/article/news/ocr/general) with lenient JSON"
```

### Verify Visual & Transform Claims (Task 7)

- [ ] **Visual claim:** n/a (service layer).
- [ ] **Transform claim:** calling `analyze_image_task` with a receipt text returns an OcrPayload dict (`engine: "gemini-vision@1"`).
- [ ] **Verification method:** pytest output above.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 8: The `/api/v1` router (auth, rate limit, image input, endpoints)

**Files:**
- Create: `src/utils/ip_rate_limiter.py`
- Create: `src/api/__init__.py`
- Create: `src/api/external_vision.py`
- Create: `tests/test_external_vision_api.py`

**Interfaces:**
- Consumes: `settings.get_external_api_token()` etc. (Task 5), `SUPPORTED_TASKS` / `analyze_image_task` (Task 7), `DEFAULT_ALLOWED_HOSTS` / `safe_fetch` (`src/utils/ssrf_guard.py`).
- Produces: `router` (APIRouter, prefix `/api/v1`): `GET /api/v1/tasks`, `POST /api/v1/analyze`. Test seams: module accessors `_api_enabled()`, `_expected_token()`, `_rate_limit_per_minute()`, `_max_image_bytes()`, `_timeout_seconds()`, `_extra_image_hosts()`, `_vision_providers_configured()`, plus `_limiter` (with `.clear()`).

- [ ] **Step 1: Write the failing test — limiter first**

`tests/test_external_vision_api.py`:

```python
"""Tests for /api/v1 endpoints: auth, limits, input handling, happy paths."""

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from src.api import external_vision as ev
from src.utils.ip_rate_limiter import IpRateLimiter


def test_ip_limiter_blocks_after_budget():
    limiter = IpRateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("1.1.1.1", now=0.0)
    assert limiter.allow("1.1.1.1", now=1.0)
    assert not limiter.allow("1.1.1.1", now=2.0)
    assert limiter.allow("2.2.2.2", now=2.0)  # other IPs unaffected
    assert limiter.allow("1.1.1.1", now=61.0)  # window slides
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_external_vision_api.py -v
```

Expected: FAIL — `src.utils.ip_rate_limiter` and `src.api.external_vision` don't exist.

- [ ] **Step 3: Implement `src/utils/ip_rate_limiter.py`**

```python
"""Tiny per-IP sliding-window limiter (stdlib only).

Kept separate from services/rate_limiter.py (chat/user budgets for LINE) so the
external API has its own independent budget.
"""

import time
from collections import defaultdict


class IpRateLimiter:
    def __init__(self, max_requests: int, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = defaultdict(list)

    def allow(self, ip: str, now: float | None = None) -> bool:
        """Record a hit for `ip` and return True while it stays within budget."""
        now = time.monotonic() if now is None else now
        window_start = now - self.window_seconds
        hits = [t for t in self._hits[ip] if t > window_start]
        if len(hits) >= self.max_requests:
            self._hits[ip] = hits
            return False
        hits.append(now)
        self._hits[ip] = hits
        return True

    def clear(self) -> None:
        self._hits.clear()
```

- [ ] **Step 4: Extend the test file with the endpoint tests** (append to `tests/test_external_vision_api.py`)

```python
@pytest.fixture
def client() -> TestClient:
    test_app = FastAPI()
    test_app.include_router(ev.router)
    return TestClient(test_app)


@pytest.fixture(autouse=True)
def _api_env(monkeypatch):
    ev._limiter.clear()
    monkeypatch.setattr(ev, "_api_enabled", lambda: True)
    monkeypatch.setattr(ev, "_expected_token", lambda: "test-ext-token")
    monkeypatch.setattr(ev, "_rate_limit_per_minute", lambda: 100)
    monkeypatch.setattr(ev, "_max_image_bytes", lambda: 6 * 1024 * 1024)
    monkeypatch.setattr(ev, "_timeout_seconds", lambda: 30.0)
    monkeypatch.setattr(ev, "_extra_image_hosts", lambda: set())
    monkeypatch.setattr(ev, "_vision_providers_configured", lambda: True)
    yield
    ev._limiter.clear()


def _auth() -> dict[str, str]:
    return {"Authorization": "Bearer test-ext-token"}


def test_tasks_endpoint_lists_supported_tasks(client):
    response = client.get("/api/v1/tasks", headers=_auth())
    assert response.status_code == 200
    assert response.json()["tasks"] == ["receipt", "article", "news", "ocr", "general"]


def test_missing_token_is_401(client):
    response = client.post("/api/v1/analyze", json={"image": {"base64": "aGk="}, "task": "ocr"})
    assert response.status_code == 401


def test_bad_token_is_401(client):
    response = client.post(
        "/api/v1/analyze",
        json={"image": {"base64": "aGk="}, "task": "ocr"},
        headers={"Authorization": "Bearer nope"},
    )
    assert response.status_code == 401


def test_503_when_no_token_configured(client, monkeypatch):
    monkeypatch.setattr(ev, "_expected_token", lambda: None)
    response = client.post("/api/v1/analyze", json={"image": {"base64": "aGk="}, "task": "ocr"}, headers=_auth())
    assert response.status_code == 503


def test_503_when_disabled(client, monkeypatch):
    monkeypatch.setattr(ev, "_api_enabled", lambda: False)
    response = client.post("/api/v1/analyze", json={"image": {"base64": "aGk="}, "task": "ocr"}, headers=_auth())
    assert response.status_code == 503


def test_unknown_task_is_422(client):
    response = client.post("/api/v1/analyze", json={"image": {"base64": "aGk="}, "task": "nope"}, headers=_auth())
    assert response.status_code == 422


def test_oversize_image_is_413(client, monkeypatch):
    monkeypatch.setattr(ev, "_max_image_bytes", lambda: 64)
    big = "A" * 4096
    response = client.post("/api/v1/analyze", json={"image": {"base64": big}, "task": "ocr"}, headers=_auth())
    assert response.status_code == 413


def test_non_allowlisted_url_host_is_400(client):
    response = client.post(
        "/api/v1/analyze",
        json={"image": {"url": "https://evil.example.com/a.png"}, "task": "ocr"},
        headers=_auth(),
    )
    assert response.status_code == 400


def test_exactly_one_image_source_required(client):
    response = client.post(
        "/api/v1/analyze",
        json={"image": {"base64": "aGk=", "url": "https://huggingface.co/x.png"}, "task": "ocr"},
        headers=_auth(),
    )
    assert response.status_code == 400


def test_receipt_happy_path(client, monkeypatch):
    async def fake_task(**kwargs):
        return {
            "task": "receipt",
            "text": "TOTAL 45",
            "structured": None,
            "ocr": {"engine": "gemini-vision@1", "lines": []},
            "provider": "gemini",
            "latency_ms": 12,
        }

    monkeypatch.setattr(ev, "analyze_image_task", fake_task)
    response = client.post("/api/v1/analyze", json={"image": {"base64": "aGk="}, "task": "receipt"}, headers=_auth())

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["ocr"]["engine"] == "gemini-vision@1"
    assert body["provider"] == "gemini"
    assert body["requestId"]


def test_rate_limit_returns_429(client, monkeypatch):
    async def fake_task(**kwargs):
        return {"task": "ocr", "text": "x", "structured": None, "ocr": None, "provider": "gemini", "latency_ms": 1}

    monkeypatch.setattr(ev, "analyze_image_task", fake_task)
    monkeypatch.setattr(ev, "_rate_limit_per_minute", lambda: 2)
    body = {"image": {"base64": "aGk="}, "task": "ocr"}

    assert client.post("/api/v1/analyze", json=body, headers=_auth()).status_code == 200
    assert client.post("/api/v1/analyze", json=body, headers=_auth()).status_code == 200
    assert client.post("/api/v1/analyze", json=body, headers=_auth()).status_code == 429
```

- [ ] **Step 5: Implement `src/api/__init__.py` (empty) and `src/api/external_vision.py`**

```python
"""External Vision API — token-protected /api/v1 endpoints for other projects.

Design notes:
- Auth: Bearer token (EXTERNAL_API_TOKEN, falls back to BUDGETBOSS_SYNC_TOKEN).
- Input: base64 / data URL / allowlisted HTTPS URL (SSRF-guarded via utils.ssrf_guard).
- Output: JSON with extracted text plus task-specific structure (receipt OCR payload,
  article/news parsed JSON).
- Rate limit: per-IP sliding window (EXTERNAL_API_RATE_LIMIT_PER_MINUTE, default 30/min).
- No raw image bytes are ever logged; only task/size/latency metadata.
"""

import asyncio
import base64
import binascii
import hmac
import logging
import uuid

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from src.config import settings
from src.services.external_vision_service import SUPPORTED_TASKS, analyze_image_task
from src.utils.ip_rate_limiter import IpRateLimiter
from src.utils.ssrf_guard import DEFAULT_ALLOWED_HOSTS, safe_fetch

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["External Vision API"])

_limiter = IpRateLimiter(max_requests=30, window_seconds=60)


# --- settings accessors (single seam for tests) -----------------------------


def _api_enabled() -> bool:
    return settings.external_api_enabled


def _expected_token() -> str | None:
    return settings.get_external_api_token()


def _rate_limit_per_minute() -> int:
    return settings.external_api_rate_limit_per_minute


def _max_image_bytes() -> int:
    return int(settings.external_api_max_image_mb * 1024 * 1024)


def _timeout_seconds() -> float:
    return settings.external_api_timeout_seconds


def _extra_image_hosts() -> set[str]:
    return settings.get_external_api_image_hosts()


def _vision_providers_configured() -> bool:
    return settings.is_any_vision_provider_configured()


# --- request models ----------------------------------------------------------


class ImageInput(BaseModel):
    dataUrl: str | None = Field(default=None, description="data:image/...;base64,... payload")
    base64: str | None = Field(default=None, description="Raw base64 image payload (no data: prefix)")
    url: str | None = Field(default=None, description="HTTPS image URL (host must be allowlisted)")


class AnalyzeRequest(BaseModel):
    image: ImageInput
    task: str = Field(default="general", description="One of: receipt, article, news, ocr, general")
    prompt: str | None = Field(default=None, max_length=4000, description="Optional custom prompt (replaces the task default)")
    countryHint: str = Field(default="TH", max_length=8, description="Locale hint used for receipt OCR payloads")


# --- guards -------------------------------------------------------------------


def _require_auth(request: Request) -> None:
    if not _api_enabled():
        raise HTTPException(status_code=503, detail="External API disabled")
    token = _expected_token()
    if not token:
        raise HTTPException(status_code=503, detail="External API not configured")
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer ") or not hmac.compare_digest(header[7:], token):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _check_rate_limit(request: Request) -> None:
    _limiter.max_requests = _rate_limit_per_minute()
    ip = request.client.host if request.client else "unknown"
    if not _limiter.allow(ip):
        logger.warning(f"🌐 External API rate limit hit for {ip}")
        raise HTTPException(status_code=429, detail="Rate limit exceeded")


# --- image input handling ------------------------------------------------------


def _sniff_mime(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/jpeg"


def _decode_base64_payload(raw: str) -> str:
    """Return a `data:image/...;base64,` URL from a data URL or raw base64 string."""
    candidate = raw.strip()
    if candidate.startswith("data:"):
        if not candidate.startswith("data:image/"):
            raise HTTPException(status_code=400, detail="Only image/* data URLs are accepted")
        return candidate
    try:
        decoded = base64.b64decode(candidate, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid base64 image payload") from exc
    mime = _sniff_mime(decoded)
    return f"data:{mime};base64,{candidate}"


def _enforce_size(data_url: str) -> int:
    _, _, b64 = data_url.partition(",")
    approx_bytes = len(b64) * 3 // 4
    if approx_bytes > _max_image_bytes():
        raise HTTPException(status_code=413, detail="Image too large")
    return approx_bytes


async def _fetch_image_url(url: str) -> str:
    allowed = DEFAULT_ALLOWED_HOSTS | _extra_image_hosts()
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await safe_fetch(client, url, allowed_hosts=allowed)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"image.url rejected: {exc}") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"image.url fetch failed: {exc}") from exc

    content_type = (response.headers.get("content-type") or "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="image.url must return an image/* content type")
    if len(response.content) > _max_image_bytes():
        raise HTTPException(status_code=413, detail="Image too large")
    return f"data:{content_type};base64,{base64.b64encode(response.content).decode('ascii')}"


async def _resolve_image(image: ImageInput) -> tuple[str, int]:
    provided = [v for v in (image.dataUrl, image.base64, image.url) if v]
    if len(provided) != 1:
        raise HTTPException(status_code=400, detail="Provide exactly one of image.dataUrl, image.base64, image.url")
    if image.dataUrl:
        data_url = _decode_base64_payload(image.dataUrl)
    elif image.base64:
        data_url = _decode_base64_payload(image.base64)
    else:
        data_url = await _fetch_image_url(image.url or "")
    return data_url, _enforce_size(data_url)


# --- endpoints -----------------------------------------------------------------


@router.get("/tasks")
async def list_tasks(request: Request) -> dict:
    """List the analysis tasks this Space supports, plus the current rate limit."""
    _require_auth(request)
    return {"tasks": list(SUPPORTED_TASKS), "rate_limit_per_minute": _rate_limit_per_minute()}


@router.post("/analyze")
async def analyze(request: Request, body: AnalyzeRequest) -> dict:
    """Analyze one image with the requested task and return structured JSON."""
    _require_auth(request)
    _check_rate_limit(request)

    if body.task not in SUPPORTED_TASKS:
        raise HTTPException(
            status_code=422,
            detail=f"Unsupported task '{body.task}'. Supported: {', '.join(SUPPORTED_TASKS)}",
        )

    request_id = uuid.uuid4().hex[:16]
    data_url, size_bytes = await _resolve_image(body.image)

    if not _vision_providers_configured():
        raise HTTPException(status_code=503, detail="No vision provider configured")

    logger.info(f"🌐 /api/v1/analyze task={body.task} request_id={request_id} bytes={size_bytes}")

    try:
        result = await asyncio.wait_for(
            analyze_image_task(
                image_data_url=data_url,
                task=body.task,
                prompt=body.prompt,
                country_hint=body.countryHint,
            ),
            timeout=_timeout_seconds(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail="Analysis timed out") from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    logger.info(
        f"✅ /api/v1/analyze done task={body.task} request_id={request_id} "
        f"provider={result.get('provider')} latency_ms={result.get('latency_ms')}"
    )
    return {"success": True, "requestId": request_id, "bytes": size_bytes, **result}
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest tests/test_external_vision_api.py -v
```

Expected: PASS (13 tests: limiter + all endpoint cases).

- [ ] **Step 7: Commit**

```bash
git add src/utils/ip_rate_limiter.py src/api/__init__.py src/api/external_vision.py tests/test_external_vision_api.py
git commit -m "feat(api): token-protected /api/v1 vision endpoints (analyze, tasks)"
```

### Verify Visual & Transform Claims (Task 8)

- [ ] **Visual claim:** n/a until wired into the app (Task 9) — router tests use an isolated FastAPI app.
- [ ] **Transform claim:** request → response JSON contains `success`, `requestId`, `provider`, `latency_ms`, and task payload.
- [ ] **Verification method:** pytest output above.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 9: Wire the router into the app + health flag + docs

**Files:**
- Modify: `src/main.py` (include router; `/health` gains `external_api` check)
- Modify: `README.md` (link to the new doc)
- Create: `docs/EXTERNAL_API.md`
- Modify: `tests/test_main.py` (route presence test)

**Interfaces:**
- Consumes: `src.api.external_vision.router` (Task 8).
- Produces: live routes `GET /api/v1/tasks`, `POST /api/v1/analyze` on the deployed app; `/health` → `checks.external_api.enabled` (wrapped in `bool(...)` so mocked settings in existing tests serialise fine).

- [ ] **Step 1: Write the failing test** (append to `tests/test_main.py`)

```python
def test_app_exposes_external_api_routes():
    """The /api/v1 vision API must be mounted on the application."""
    from src.main import app

    paths = {route.path for route in app.routes}
    assert "/api/v1/analyze" in paths
    assert "/api/v1/tasks" in paths
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_main.py::test_app_exposes_external_api_routes -v
```

Expected: FAIL — `/api/v1/*` not mounted yet.

- [ ] **Step 3: Implement in `src/main.py`**

With the other `src.*` imports at the top:

```python
from src.api.external_vision import router as external_vision_router
```

After the CORS middleware block (below `app = FastAPI(...)` and `setup_tracing(...)`), add:

```python
# External Vision API (/api/v1) — token-protected image analysis for other projects
app.include_router(external_vision_router)
```

In `health_check()`, add to the `checks` dict (after `"llm_providers": {...}`):

```python
            "external_api": {
                "enabled": bool(settings.external_api_enabled) and bool(settings.get_external_api_token()),
            },
```

(The explicit `bool(...)` keeps the new field JSON-serialisable when tests patch `src.main.settings` with a MagicMock.)

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_main.py -v
```

Expected: PASS — including the pre-existing health/readiness tests.

- [ ] **Step 5: Write `docs/EXTERNAL_API.md`**

````markdown
# External Vision API

Token-protected endpoints for other projects to run image analysis on the
TeacherBOY Space. Additive to the LINE bot — the webhook flow is untouched.

Base URL: `https://evilevan-teacherboy.hf.space`

## Auth

Every `/api/v1/*` request needs a Bearer token:

- `EXTERNAL_API_TOKEN` Space secret, or
- `BUDGETBOSS_SYNC_TOKEN` as fallback (so Budget Boss keeps working without changes).

## Tasks

| task | what it returns |
|---|---|
| `receipt` | extracted text + OcrPayload (`engine: "gemini-vision@1"`, line list) for finance ingestion |
| `article` | strict JSON (title, publication, date, byline, summary, key_points, language) in `structured` |
| `news` | strict JSON (headline, source, date, top_facts, why_it_matters, entities, language) in `structured` |
| `ocr` | raw extracted text (signs, menus, documents, screenshots) |
| `general` | open description; pass `prompt` for a specific question |

## Request

`POST /api/v1/analyze` — JSON body:

```json
{
  "image": { "base64": "<raw base64>" },
  "task": "receipt",
  "countryHint": "TH"
}
```

`image` accepts exactly one of: `dataUrl` (a `data:image/...;base64,...` string),
`base64` (raw base64; MIME sniffed automatically), or `url` (HTTPS only;
host must be on the SSRF allowlist — `huggingface.co` and friends are built in,
extend via the `EXTERNAL_API_IMAGE_HOSTS` secret, comma-separated).

Optional: `prompt` (≤4000 chars, replaces the task's default prompt).

## Response

```json
{
  "success": true,
  "requestId": "0f3a9c2b7d1e4a55",
  "bytes": 182233,
  "task": "receipt",
  "text": "COFFEE 45 THB\nTOTAL 45",
  "structured": null,
  "ocr": { "engine": "gemini-vision@1", "lines": [ ... ] },
  "provider": "gemini",
  "latency_ms": 2340
}
```

## Errors

| status | meaning |
|---|---|
| 400 | bad input (invalid base64, both/neither image source, non-allowlisted URL, non-image content type) |
| 401 | missing/wrong Bearer token |
| 413 | image larger than `EXTERNAL_API_MAX_IMAGE_MB` (default 6 MB) |
| 422 | unknown task |
| 429 | per-IP rate limit (`EXTERNAL_API_RATE_LIMIT_PER_MINUTE`, default 30/min) |
| 502 | all vision providers failed |
| 504 | analysis exceeded `EXTERNAL_API_TIMEOUT_SECONDS` (default 60 s) |
| 503 | API disabled / no token configured / no vision provider |

## Examples

```bash
# List tasks
curl -s https://evilevan-teacherboy.hf.space/api/v1/tasks \
  -H "Authorization: Bearer $EXTERNAL_API_TOKEN"

# Scrape a receipt (base64)
B64=$(base64 -w0 receipt.jpg)
curl -s -X POST https://evilevan-teacherboy.hf.space/api/v1/analyze \
  -H "Authorization: Bearer $EXTERNAL_API_TOKEN" -H "Content-Type: application/json" \
  -d "{\"image\":{\"base64\":\"$B64\"},\"task\":\"receipt\",\"countryHint\":\"TH\"}"

# Article screenshot → structured JSON
curl -s -X POST https://evilevan-teacherboy.hf.space/api/v1/analyze \
  -H "Authorization: Bearer $EXTERNAL_API_TOKEN" -H "Content-Type: application/json" \
  -d '{"image":{"url":"https://huggingface.co/datasets/EvilEvan/teacherboy-images/resolve/main/sample.png"},"task":"article"}'
```

```python
# Python (requests)
import base64, requests

with open("receipt.jpg", "rb") as fh:
    b64 = base64.b64encode(fh.read()).decode()

resp = requests.post(
    "https://evilevan-teacherboy.hf.space/api/v1/analyze",
    headers={"Authorization": f"Bearer {TOKEN}"},
    json={"image": {"base64": b64}, "task": "receipt", "countryHint": "TH"},
    timeout=90,
)
resp.raise_for_status()
print(resp.json()["ocr"]["lines"][:3])
```
````

Add to `README.md` (in the features/endpoints section, next to the webhook/health mentions):

```markdown
- **External Vision API** (`/api/v1/analyze`, `/api/v1/tasks`) — token-protected image
  analysis for other projects (receipts, articles, news, OCR). See
  [docs/EXTERNAL_API.md](docs/EXTERNAL_API.md).
```

- [ ] **Step 6: Run the full local gate**

```bash
ruff check src/ tests/ && ruff format --check src/ tests/
pytest tests/test_main.py tests/test_external_vision_api.py tests/services/test_external_vision_service.py -v
```

Expected: clean + PASS.

- [ ] **Step 7: Commit**

```bash
git add src/main.py tests/test_main.py docs/EXTERNAL_API.md README.md
git commit -m "feat(api): mount /api/v1 vision router; document external integration"
```

### Verify Visual & Transform Claims (Task 9)

- [ ] **Visual claim:** `GET /` on the deployed Space still 200; `GET /api/v1/tasks` 200 with token, 401 without.
- [ ] **Transform claim:** `/health` JSON now includes `checks.external_api.enabled`.
- [ ] **Verification method:** Task 10 live smoke tests (curl).
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

### Task 10: Repo hygiene (F7) — junk files

**Files:**
- Delete: `=2.100.0,`, `=42.0.0` (0-byte pip redirect artifacts)
- Move: `diff.txt` (352 KB), `form_translation.txt`, `temp_handler_code.txt` → `docs/archive/2026-09/`

**Interfaces:**
- Produces: clean repo root; history preserved by git rename.

- [ ] **Step 1: Move/delete**

```bash
mkdir -p docs/archive/2026-09
git rm -q "=2.100.0," "=42.0.0"
git mv diff.txt docs/archive/2026-09/diff-2026-09-15.txt
git mv form_translation.txt docs/archive/2026-09/form_translation.txt
git mv temp_handler_code.txt docs/archive/2026-09/temp_handler_code.txt
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: drop stray pip artifacts; archive loose scratch files"
```

### Verify Visual & Transform Claims (Task 10)

- [ ] **Visual claim:** repo root no longer lists `=2.100.0,`, `=42.0.0`, or the loose `.txt` files.
- [ ] **Transform claim:** `git log --stat -1` shows renames + deletions.
- [ ] **Verification method:** `ls` + `git show --stat HEAD`.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

# Part C — Deploy & live verification

### Task 11: Deploy to the Space and verify end-to-end

**Files:** none (operational task).

**Interfaces:**
- Consumes: everything above, committed on `main`.

- [ ] **Step 1: Pre-flight gate**

```bash
cd /home/leandi-duplessis/github/workspaces/TeacherBOY
. .venv/bin/activate
ruff check src/ tests/ && ruff format --check src/ tests/
pytest -q 2>&1 | tail -5
git status --short   # expected: clean
```

Expected: lint clean; tests green (baseline parity with Task 0).

- [ ] **Step 2: Push to main (GitHub Actions deploys)**

```bash
git push origin main
```

Then watch the deploy:

```bash
gh run list --workflow ci.yml --limit 3
gh run watch "$(gh run list --workflow ci.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
```

If `gh` is unavailable, watch from the Actions tab in the browser. Expected: `lint-and-type` → `unit-test` → `docker-build` → `deploy` all green; `huggingface_sync.yml` also runs (repo variable `ENABLE_HF_SYNC=true`).

- [ ] **Step 3: Verify the Space picked up the new SHA**

```bash
python3 - <<'EOF'
import json, os, urllib.request

def get_sha():
    req = urllib.request.Request(
        "https://huggingface.co/api/spaces/EvilEvan/TeacherBOY",
        headers={"Authorization": f"Bearer {os.environ['HF_TOKEN']}"},
    )
    return json.load(urllib.request.urlopen(req))["runtime"]["sha"]

print("space sha:", get_sha())
EOF
git rev-parse HEAD
```

Expected: Space SHA == `git rev-parse HEAD`; the Space rebuilds (~2–5 min). Poll the HF API until the new SHA is live and `runtime.stage == "RUNNING"`.

- [ ] **Step 4: Confirm the Space token**

Check `https://evilevan-teacherboy.hf.space/health`:

```bash
curl -s https://evilevan-teacherboy.hf.space/health | python3 -c "import json,sys; print(json.load(sys.stdin)['checks']['external_api'])"
```

Expected: `{'enabled': True}`. If `enabled: False`, set the Space secret (Settings → Variables and secrets):
`EXTERNAL_API_TOKEN = <a new random string>` (or rely on the existing `BUDGETBOSS_SYNC_TOKEN`). Re-check until true. **[Evan action — do not do this from a script.]**

- [ ] **Step 5: Auth + tasks smoke test**

```bash
TOKEN="$EXTERNAL_API_TOKEN"   # export locally = same value set in the Space
curl -s -o /dev/null -w "%{http_code}\n" https://evilevan-teacherboy.hf.space/api/v1/tasks            # expect 401
curl -s https://evilevan-teacherboy.hf.space/api/v1/tasks -H "Authorization: Bearer $TOKEN"          # expect 200 + task list
```

- [ ] **Step 6: Real OCR end-to-end (the money shot)**

Generate a tiny text image, POST it, assert the text comes back:

```bash
.venv/bin/python - <<'PY'
from PIL import Image, ImageDraw
img = Image.new("RGB", (720, 240), "white")
ImageDraw.Draw(img).text((30, 100), "FENRIE SMOKE TEST 45123", fill="black")
img.save("/tmp/smoke_ocr.png")
print("wrote /tmp/smoke_ocr.png")
PY
# PIL ships with the easyocr dependency; if missing: .venv/bin/pip install pillow

B64=$(base64 -w0 /tmp/smoke_ocr.png)
curl -s -X POST "https://evilevan-teacherboy.hf.space/api/v1/analyze" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"image\":{\"base64\":\"$B64\"},\"task\":\"ocr\"}" \
  | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['provider'], '|', d['text'][:200]); assert 'SMOKE' in d['text'].upper(), 'text not extracted'; print('OCR SMOKE: PASS')"
```

Expected: `provider` is a real model (gemini first), extracted text contains `SMOKE`, script prints `OCR SMOKE: PASS`.

- [ ] **Step 7: Log verification (transforms from Part A)**

```bash
curl -sN -H "Authorization: Bearer $HF_TOKEN" "https://huggingface.co/api/spaces/EvilEvan/TeacherBOY/logs/run" > /tmp/run_after.log &
PID=$!; sleep 40; kill $PID 2>/dev/null
python3 - <<'EOF'
lines = open("/tmp/run_after.log", errors="replace").read().splitlines()
for needle in ("hpack", "filelock", "httpcore", "Cannot add middleware", "v6/exchangerate"):
    hits = [l for l in lines if needle in l]
    print(f"{needle!r}: {len(hits)} hits")
api = [l for l in lines if "/api/v1/analyze" in l]
print("api log lines:", len(api))
EOF
```

Expected: 0 hits for all noise needles; ≥2 lines for `/api/v1/analyze` (the smoke test);

- [ ] **Step 8: Update `docs/recommendations.md`**

Append:

```markdown
## 2026-09-22 — Flexible Vision API (Fenrie)

- [R2] ✅ Implemented: `/api/v1/analyze` + `/api/v1/tasks` mounted in `src/main.py`
  (see `docs/EXTERNAL_API.md`, plan `docs/plans/2026-09-22-flexible-vision-api.md`).
- [R1] Superseded: other projects can now consume the Space directly, no provider re-config needed.
```

```bash
git add docs/recommendations.md
git commit -m "docs: mark vision endpoint recommendation as implemented"
git push origin main
```

### Verify Visual & Transform Claims (Task 11)

- [ ] **Visual claim:** HF Space page shows the new commit; `/api/v1/tasks` answers with the task list; OCR smoke response contains the drawn text.
- [ ] **Transform claim:** Space SHA == new HEAD; run log noise counts drop to 0; `/health` shows `external_api.enabled: true`.
- [ ] **Verification method:** the curl/python outputs above, saved into the PR/issue notes.
- [ ] **Verification result:** [PASS / FAIL / BLOCKED — evidence snippet]

---

## Self-Review (run 2026-09-22 before saving)

**1. Spec coverage:** Every finding F1–F9 maps to a task — F1/F2 → Task 2; F3 → Task 3; F4/F6 → Task 1; F5 → Task 4; F7 → Task 10; F8 (the One Change) → Tasks 5–9; F9 → recorded in the backlog below (intentionally not built; no live-log evidence of user impact). The 2026-09-17 investigation's R2 ("build `/vision/analyze` … JSON response format") is delivered as `/api/v1/analyze` with stronger auth/limits.

**2. Placeholder scan:** No TBD/TODO/"handle edge cases" steps; every code step carries the full code to paste. The only operational unknowns are flagged as explicit human actions (Space secret provisioning in Task 11 Step 4).

**3. Type consistency:** Names used consistently across tasks — `silence_noisy_loggers`, `IpRateLimiter.allow/clear`, `chat_completion_with_vision_fallback_ex -> tuple[str, str] | None`, `SUPPORTED_TASKS`, `analyze_image_task(**kwargs) -> dict`, router accessors `_expected_token` etc., config helpers `get_external_api_token()/get_external_api_image_hosts()`, response keys `success/requestId/bytes/task/text/structured/ocr/provider/latency_ms`. Task 8's tests patch exactly the accessor names defined in Task 8's implementation.

**4. Visual/Transform verification completeness:** Every user-observable change has an observation method: log content (Tasks 2, 3, 11), dataset tree (Task 4), live HTTP endpoints (Tasks 9, 11), OCR round-trip on real infrastructure (Task 11 Step 6). No change relies on "tests pass" alone.

**5. Anti-Gravity collaboration boundary:** N/A — no external agent involved. Sharing rules stated in the header for any future sharing (no secrets, no user data, repo files only).

**6. Source provenance check:** All referenced internals verified in-repo on 2026-09-22 (file:line noted in findings); external doc claims (huggingface-hub 0.23.0 `ignore_patterns` on `CommitScheduler`) match the pinned dependency in `requirements.txt:35`; HF API endpoints were exercised live during investigation (space meta, dataset tree, logs).

---

## Backlog (found, deliberately NOT built now)

- `ReceiptAgent._is_user_linked` TODO — implement the Budget Boss linked-users check before enabling `RECEIPT_REQUIRE_LINKED` (security).
- Webhook per-IP limiter dict (`main.py:1404`) grows per unique IP; consider moving to the new `IpRateLimiter` with periodic `clear()` on a timer.
- Bangkok Post feeds: consider adding a second Thai source or per-feed disable list if 451 persists; the current fix only silences the log noise.
- `/receipt/scan` could become a thin wrapper over `/api/v1/analyze` with `ingest` semantics once Budget Boss migrates.
- Rotate the ExchangeRate-API key (it appeared in run logs before Task 2 lands) — operational action in the HF account.

## Execution Handoff

Two execution options:

1. **Subagent-Driven (recommended)** — one fresh subagent per task, review between tasks, fast iteration. Tasks 1–8 are small and independent; the subagent pattern keeps each change reviewed against its verification block.
2. **Inline Execution** — run the tasks in this session with `executing-plans`, batch checkpoints after Part A (Tasks 0–4) and Part B (Tasks 5–9) for review.

Either way, Task 11 (deploy + live smoke) should run last, with Evan watching the HF Space settings when the token step comes up.