# Documentation Alignment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the repository entry point, the canonical environment
reference, contributor instructions, and the affected feature docs around one
consistent storage and persistence contract without changing runtime behavior.

**Architecture:** Keep `docs/reference/environment.md` as the canonical
configuration surface, add only a short persistence summary to `README.md`,
trim duplicate setup detail from feature docs, and refresh
`.github/copilot-instructions.md` so contributor guidance matches the live
runtime model. The implementation is documentation-only: it removes stale
wording, consolidates repeated explanations, and replaces hardcoded path text
with the correct environment-variable semantics.

**Tech Stack:** Markdown, ripgrep, git diff, Python 3 for link/newline sanity checks

---

## Goal and Non-Goals

### Goal

- Make `README.md`, `docs/reference/environment.md`, and
  `.github/copilot-instructions.md` agree on storage and persistence behavior.
- Keep feature docs concise and feature-specific while pointing to the
  canonical environment reference for full configuration semantics.
- Remove stale hardcoded-path and stale-identity wording from the selected documentation surfaces.

### Non-Goals

- Do not change any Python runtime behavior, settings, or persistence implementations.
- Do not create a new standalone storage explainer page.
- Do not rewrite unrelated docs outside the approved file set.
- Do not remove historical references that are clearly marked as historical context.

## File Responsibilities

### Modify

- `README.md`
  Add one compact persistence section and one canonical link to the environment reference.
- `docs/reference/environment.md`
  Keep the canonical storage contract and tighten wording so each storage variable has one unambiguous meaning.
- `.github/copilot-instructions.md`
  Refresh contributor/runtime facts to match the current storage model and current public runtime identity.
- `docs/CONVERSATION_MEMORY.md`
  Keep feature behavior, but trim duplicated storage explanation and point back to the environment reference.
- `docs/DOCUMENT_MEMORY.md`
  Add the environment-reference pointer and mounted-path wording without re-explaining the full shared storage contract.
- `docs/CALENDAR_REMINDERS.md`
  Keep calendar-specific persistence behavior and compress generic HF-storage explanation.
- `docs/KPS_ASSISTANT.md`
  Replace hardcoded path prose with the correct storage variables and a link back to the environment reference.

### Leave Untouched

- `src/`
  Runtime code is already correct for the mounted-path work and is out of scope.
- `workspace_non_critical_issues.json`
  No new non-critical issue is expected from this docs-only alignment work.
- `docs/superpowers/specs/2026-05-31-doc-alignment-design.md`
  This is the approved design input, not an implementation target.

## Ordered Tasks

### Task 1: Tighten the canonical storage contract in the environment reference

**Depends on:** none

**Files:**

- Modify: `docs/reference/environment.md`

- [ ] **Step 1: Capture the current storage sections before editing**

Run:

```bash
rg -n "Mounted-Volume Deployment|Local Storage Paths|CONVERSATION_STORAGE_PATH|BOT_IDENTITY_STORAGE_PATH|STAFF_MEMORY_STORAGE_PATH|CALENDAR_HF_REPO_ID" docs/reference/environment.md
```

Expected:

```text
Matches for the mounted-volume section, the local storage path section, and the named variables.
```

- [ ] **Step 2: Replace the mounted-volume summary with the canonical contract wording**

Use this exact Markdown content for the mounted-volume block:

```md
## Mounted-Volume Deployment

- Mounted storage backs local filesystem paths. It does not replace the separate Hugging Face dataset repo IDs.
- Keep HF repo separation explicit: `HF_MEMORY_REPO_ID` for conversations, `DOCUMENT_HF_REPO_ID` for document memory, `HISTORY_LOG_HF_REPO_ID` for history logs, and `CALENDAR_HF_REPO_ID` for calendar data.
- Use mounted paths for local filesystem state and CommitScheduler working data.
- For conversation memory, `CONVERSATION_STORAGE_PATH` is the local working/cache directory used by the HF-backed sync path. Restart persistence for conversation history still depends on `HF_MEMORY_TOKEN` and `HF_MEMORY_REPO_ID` in the current implementation.
- `BOT_IDENTITY_STORAGE_PATH` stores runtime identity overrides.
- `STAFF_MEMORY_STORAGE_PATH` stores review-agent staff memory.
- There is no persisted APScheduler task store in this implementation. Scheduled jobs remain runtime-only.
```

- [ ] **Step 3: Keep the three local storage path definitions precise and short**

Ensure these exact definitions appear under `## Local Storage Paths`:

```md
### `CONVERSATION_STORAGE_PATH`

- **Type:** String
- **Default:** `./data/conversations`
- **Description:** Local working/cache directory used by the HF-backed conversation memory sync path; by itself it does not enable restart persistence
- **Example:** `CONVERSATION_STORAGE_PATH=/data/ms-sunshine/conversations`

### `BOT_IDENTITY_STORAGE_PATH`

- **Type:** String
- **Default:** `./data/bot_identity/profile.json`
- **Description:** Local JSON file for runtime bot identity name and alias overrides
- **Example:** `BOT_IDENTITY_STORAGE_PATH=/data/ms-sunshine/bot_identity/profile.json`

### `STAFF_MEMORY_STORAGE_PATH`

- **Type:** String
- **Default:** `./data/staff_memory/staff_memory.json`
- **Description:** Local JSON file for review-agent staff memory on the mounted volume
- **Example:** `STAFF_MEMORY_STORAGE_PATH=/data/ms-sunshine/staff_memory/staff_memory.json`
```

- [ ] **Step 4: Re-run the narrow inventory check**

Run:

```bash
rg -n "Mounted-Volume Deployment|CONVERSATION_STORAGE_PATH|BOT_IDENTITY_STORAGE_PATH|STAFF_MEMORY_STORAGE_PATH|runtime-only" docs/reference/environment.md
```

Expected:

```text
Matches for the updated mounted-volume section, all three storage variables, and the runtime-only scheduler note.
```

- [ ] **Step 5: Commit**

```bash
git add docs/reference/environment.md
git commit -m "docs: clarify canonical storage contract"
```

### Task 2: Add a compact persistence summary to README.md

**Depends on:** Task 1

**Files:**

- Modify: `README.md`

- [ ] **Step 1: Confirm the current docs-link area and absence of a persistence summary**

Run:

```bash
rg -n "Docs Home|Maintainer Notes|Persistence Model|Environment variables" README.md
```

Expected:

```text
Matches for the docs links, no `Persistence Model` heading yet, and no direct `Environment variables` quick link.
```

- [ ] **Step 2: Add the canonical environment-reference link to the docs list**

Insert this bullet directly under the maintainer-notes link in the `### Quick Links` list:

```md
- **[🧭 Environment Reference](docs/reference/environment.md)**
```

- [ ] **Step 3: Add one compact persistence section after the docs overview**

Insert this exact section immediately after the sentence
`The docs folder is the maintained documentation source of truth.` and before
`## 🚀 Features`:

```md
## 🗂️ Persistence Model

Ms. Green uses mounted local paths for filesystem state and separate Hugging Face dataset repositories for optional cloud persistence.

- `CONVERSATION_STORAGE_PATH` is the local working/cache directory for HF-backed conversation sync; restart persistence still depends on `HF_MEMORY_TOKEN` and `HF_MEMORY_REPO_ID`.
- `BOT_IDENTITY_STORAGE_PATH` stores runtime identity overrides.
- `STAFF_MEMORY_STORAGE_PATH` stores review-agent staff memory.
- Scheduled jobs remain runtime-only; there is no persisted APScheduler task store in the current implementation.

For the full variable reference and mounted-volume examples, see [Environment variables](docs/reference/environment.md).
```

- [ ] **Step 4: Verify the new summary is present and concise**

Run:

```bash
rg -n "Environment Reference|Persistence Model|CONVERSATION_STORAGE_PATH|runtime-only" README.md
```

Expected:

```text
Matches for the new quick link, the new persistence section, the conversation-storage note, and the runtime-only scheduler note.
```

- [ ] **Step 5: Commit**

```bash
git add README.md
git commit -m "docs: summarize persistence model in readme"
```

### Task 3: Refresh contributor/runtime guidance in `.github/copilot-instructions.md`

**Depends on:** Task 1

**Files:**

- Modify: `.github/copilot-instructions.md`

- [ ] **Step 1: Capture the stale identity and storage examples before editing**

Run:

```bash
rg -n "KPS-Assistant|zeus-memory|data/bot_identity|data/staff_memory|HF_MEMORY_REPO_ID|BOT_IDENTITY_STORAGE_PATH|STAFF_MEMORY_STORAGE_PATH" .github/copilot-instructions.md
```

Expected:

```text
Matches for the stale identity bullet, stale HF repo examples, and storage-related sections that need normalization.
```

- [ ] **Step 2: Replace the top-level runtime identity and persistence bullets**

Update the `### Big picture` and `### Data/persistence integration points` bullets so they read exactly as follows:

```md
- Runtime identity is configurable via `src/services/bot_identity_service.py`; the current public-facing runtime identity is `Ms. Green`, while legacy aliases can remain valid for compatibility.

### Data/persistence integration points

- Local data lives under configurable filesystem paths (defaulting under `data/` for calendar, conversations, logs, bot identity, and staff memory).
- Mounted paths back local filesystem state; optional HF Hub sync is configured via settings in `src/config.py` and remains separated by data type.
- Startup performs a blocking “load-before-serve” via `src/services/startup_data_loader.py` (called from `src/main.py`) so HF-backed data is present before handling requests.
- There is no persisted APScheduler task store in the current implementation.
```

- [ ] **Step 3: Normalize the HF and storage examples later in the file**

Replace stale example repo IDs and hardcoded local-path wording with these
exact examples where the file currently shows `zeus-memory` or bare
`data/...` paths:

```md
$env:HF_MEMORY_REPO_ID = "username/ms-green-memory"
```

```md
$env:HF_MEMORY_REPO_ID = "user/ms-green-memory"      # Conversation memory
$env:HISTORY_LOG_HF_REPO_ID = "user/ms-green-logs"   # History logs
$env:CALENDAR_HF_REPO_ID = "user/ms-green-calendar"  # Calendar events
```

Add this short storage note near the persistence/environment guidance block:

```md
- `CONVERSATION_STORAGE_PATH` is the local working/cache directory for HF-backed conversation sync; it is not standalone restart persistence by itself.
- `BOT_IDENTITY_STORAGE_PATH` stores runtime identity overrides.
- `STAFF_MEMORY_STORAGE_PATH` stores review-agent staff memory.
```

- [ ] **Step 4: Verify the stale examples are gone from this file**

Run:

```bash
rg -n "KPS-Assistant|zeus-memory|data/bot_identity/profile.json|data/staff_memory/staff_memory.json" .github/copilot-instructions.md
```

Expected:

```text
No matches.
```

- [ ] **Step 5: Commit**

```bash
git add .github/copilot-instructions.md
git commit -m "docs: align contributor instructions with runtime storage model"
```

### Task 4: Trim duplicated persistence detail in the memory docs

**Depends on:** Tasks 1 and 2

**Files:**

- Modify: `docs/CONVERSATION_MEMORY.md`
- Modify: `docs/DOCUMENT_MEMORY.md`

- [ ] **Step 1: Capture the current storage wording in both memory docs**

Run:

```bash
rg -n "HF_MEMORY_REPO_ID|CONVERSATION_STORAGE_PATH|DOCUMENT_STORAGE_PATH|guaranteed persistence|Environment variables" docs/CONVERSATION_MEMORY.md docs/DOCUMENT_MEMORY.md
```

Expected:

```text
Matches for the current persistence wording, with no environment-reference link in `docs/DOCUMENT_MEMORY.md` yet.
```

- [ ] **Step 2: Compress the shared storage explanation in `docs/CONVERSATION_MEMORY.md`**

Keep the existing feature-specific behavior, but replace the multi-repo
storage explanation near the mounted-volume section with this exact note:

```md
For the full storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).

In short:

- `CONVERSATION_STORAGE_PATH` is the local working/cache directory for HF-backed sync.
- Restart persistence for conversation history still depends on `HF_MEMORY_TOKEN` and `HF_MEMORY_REPO_ID`.
```

Do not remove the existing feature-specific troubleshooting or API-reference sections.

- [ ] **Step 3: Add the canonical pointer and mounted-path note to `docs/DOCUMENT_MEMORY.md`**

Insert this exact block immediately after the configuration snippet:

````md
For the full storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).

For production deployments with a mounted volume, point `DOCUMENT_STORAGE_PATH` at the mounted filesystem path and keep `DOCUMENT_HF_REPO_ID` separate for optional HF-backed persistence:

```env
DOCUMENT_STORAGE_PATH=/data/ms-sunshine/documents
DOCUMENT_HF_REPO_ID=username/ms-green-documents
```
````

Replace the current persistence note with this exact line:

```md
> For restart persistence across container resets, set both `DOCUMENT_HF_REPO_ID` and `HF_MEMORY_TOKEN`. `DOCUMENT_STORAGE_PATH` controls the local filesystem location.
```

- [ ] **Step 4: Verify both docs now point back to the environment reference**

Run:

```bash
rg -n "Environment variables\]\(reference/environment.md\)|CONVERSATION_STORAGE_PATH|DOCUMENT_STORAGE_PATH" docs/CONVERSATION_MEMORY.md docs/DOCUMENT_MEMORY.md
```

Expected:

```text
Matches for the environment-reference link in both files and the short variable-specific notes.
```

- [ ] **Step 5: Commit**

```bash
git add docs/CONVERSATION_MEMORY.md docs/DOCUMENT_MEMORY.md
git commit -m "docs: trim duplicated storage detail in memory docs"
```

### Task 5: Align calendar and KPS assistant docs, then run cross-doc validation

**Depends on:** Tasks 1 through 4

**Files:**

- Modify: `docs/CALENDAR_REMINDERS.md`
- Modify: `docs/KPS_ASSISTANT.md`
- Verify: `README.md`
- Verify: `docs/reference/environment.md`
- Verify: `.github/copilot-instructions.md`
- Verify: `docs/CONVERSATION_MEMORY.md`
- Verify: `docs/DOCUMENT_MEMORY.md`

- [ ] **Step 1: Capture the current calendar and KPS assistant persistence wording**

Run:

```bash
rg -n "HF Hub Persistence|HF_MEMORY_TOKEN|CALENDAR_HF_REPO_ID|data/bot_identity|data/staff_memory|Persistence" docs/CALENDAR_REMINDERS.md docs/KPS_ASSISTANT.md
```

Expected:

```text
Matches for the generic HF-storage block in the calendar doc and the hardcoded path bullets in the KPS assistant doc.
```

- [ ] **Step 2: Replace the generic HF-storage block in `docs/CALENDAR_REMINDERS.md` with a short calendar-specific note**

Use this exact Markdown in the persistence/configuration area:

```md
### Persistence Notes

- `CALENDAR_DATA_PATH` controls the local filesystem path for calendar data.
- `CALENDAR_HF_REPO_ID` remains the separate optional HF dataset for calendar backup.
- For the shared storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).
```

Do not remove the existing calendar-specific chat-scoping explanation.

- [ ] **Step 3: Replace the hardcoded path bullets in `docs/KPS_ASSISTANT.md`**

Replace the current `## Persistence` list with this exact content:

```md
## Persistence

- Bot identity uses `BOT_IDENTITY_STORAGE_PATH` for runtime identity overrides.
- Staff memory uses `STAFF_MEMORY_STORAGE_PATH` for review-agent staff memory.
- Calendar reminder DM routing still depends on `notification_target_user_id` on each calendar event.
- For the shared storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).
```

- [ ] **Step 4: Run the cross-doc stale-wording check**

Run:

```bash
rg -n "KPS-Assistant|zeus-memory|data/bot_identity/profile.json|data/staff_memory/staff_memory.json" README.md docs/reference/environment.md .github/copilot-instructions.md docs/CONVERSATION_MEMORY.md docs/DOCUMENT_MEMORY.md docs/CALENDAR_REMINDERS.md docs/KPS_ASSISTANT.md
```

Expected:

```text
No matches.
```

- [ ] **Step 5: Run the changed-doc link sanity check**

Run:

```bash
python - <<'PY'
from pathlib import Path
import re

files = [
    Path("README.md"),
    Path("docs/reference/environment.md"),
    Path(".github/copilot-instructions.md"),
    Path("docs/CONVERSATION_MEMORY.md"),
    Path("docs/DOCUMENT_MEMORY.md"),
    Path("docs/CALENDAR_REMINDERS.md"),
    Path("docs/KPS_ASSISTANT.md"),
]

link_pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
missing = []

for file_path in files:
    text = file_path.read_text(encoding="utf-8")
    for target in link_pattern.findall(text):
        if target.startswith("http://") or target.startswith("https://"):
            continue
        clean_target = target.split("#", 1)[0]
        resolved = (file_path.parent / clean_target).resolve()
        if clean_target and not resolved.exists():
            missing.append(f"{file_path}:{target}")

if missing:
    raise SystemExit("Missing link targets:\n" + "\n".join(missing))

print("All changed-doc markdown links resolve.")
PY
```

Expected:

```text
All changed-doc markdown links resolve.
```

- [ ] **Step 6: Run the EOF/newline and whitespace sanity checks**

Run:

```bash
python - <<'PY'
from pathlib import Path

files = [
    Path("README.md"),
    Path("docs/reference/environment.md"),
    Path(".github/copilot-instructions.md"),
    Path("docs/CONVERSATION_MEMORY.md"),
    Path("docs/DOCUMENT_MEMORY.md"),
    Path("docs/CALENDAR_REMINDERS.md"),
    Path("docs/KPS_ASSISTANT.md"),
]

bad = []
for path in files:
    data = path.read_bytes()
    if not data.endswith(b"\n"):
        bad.append(str(path))

if bad:
    raise SystemExit("Missing trailing newline: " + ", ".join(bad))

print("All changed docs end with a trailing newline.")
PY

git diff --check
```

Expected:

```text
All changed docs end with a trailing newline.
No output from git diff --check.
```

- [ ] **Step 7: Commit**

```bash
git add docs/CALENDAR_REMINDERS.md docs/KPS_ASSISTANT.md README.md docs/reference/environment.md .github/copilot-instructions.md docs/CONVERSATION_MEMORY.md docs/DOCUMENT_MEMORY.md
git commit -m "docs: align storage guidance across core surfaces"
```

## Self-Review Checklist

### Spec coverage

- `README.md`, `docs/reference/environment.md`, and `.github/copilot-instructions.md` each have an explicit task.
- The feature docs named in the approved spec each have an explicit task.
- The plan preserves the “shared facts, different depth” model instead of introducing a new canonical page.
- The plan includes validation for stale wording, internal links, and newline/whitespace hygiene.

### Placeholder scan

- No `TODO`, `TBD`, or “update as needed” wording remains.
- Every edit step includes exact Markdown content or an exact command.
- Every validation step names exact files and expected results.

### Type and naming consistency

- The plan consistently uses `CONVERSATION_STORAGE_PATH`,
  `BOT_IDENTITY_STORAGE_PATH`, `STAFF_MEMORY_STORAGE_PATH`,
  `HF_MEMORY_REPO_ID`, `DOCUMENT_HF_REPO_ID`, and `CALENDAR_HF_REPO_ID`.
- The runtime identity is consistently named `Ms. Green` in the planned replacements.
