# Hugging Face Space Deploy Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` (recommended) or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the one-time migration to a repo-authoritative Hugging Face
Space deployment model and verify that the live Space and LINE webhook use the
correct `hf.space` app host.

**Architecture:** Treat GitHub `main` as the only source of truth for
application code and Hugging Face Space `main` as a deploy target. The
workflow and docs are already aligned; the remaining work is an operational
migration and verification pass that intentionally overwrites the divergent
Space branch and confirms the live webhook behavior.

**Tech Stack:** Git, GitHub Actions, Hugging Face Spaces, FastAPI, LINE
Messaging API, curl

---

## Goals

- Confirm the repo no longer contains rebase-based Hugging Face deploy behavior.
- Perform the one-time `--force-with-lease` migration from GitHub `main` to Space `main`.
- Verify the live Space rebuilds successfully and exposes the webhook on the `hf.space` host.
- Verify the LINE channel is configured to use the `hf.space` webhook URL
  instead of the `huggingface.co/spaces/...` page URL.

## Non-Goals

- Do not reintroduce bidirectional Hugging Face/GitHub sync.
- Do not modify runtime HF data persistence behavior (`HF_MEMORY_TOKEN`, memory/calendar/log/document repos).
- Do not make unrelated code or agent behavior changes.

## File Responsibilities

### Review Only

- `.github/workflows/huggingface_sync.yml`
  - Must remain publish-only: configure `hf` remote, verify reachability, publish `HEAD:main`.
- `docs/guides/deployment.md`
  - Canonical operator guide for repo-authoritative Space deployment.
- `docs/guides/line-setup.md`
  - Canonical LINE webhook setup guide, including `hf.space` webhook examples.
- `docs/guides/quickstart.md`
  - Quick path for initial Hugging Face deploy and webhook configuration.

### Operational Targets

- Hugging Face Space remote: `https://huggingface.co/spaces/EvilEvan/TeacherBOY`
- Live Space host: `https://evilevan-teacherboy.hf.space`
- LINE webhook path: `/webhook`

---

### Task 1: Verify the Repo-Authoritative Deployment Surface

**Files:**

- Review: `.github/workflows/huggingface_sync.yml`
- Review: `docs/guides/deployment.md`
- Review: `docs/guides/line-setup.md`
- Review: `docs/guides/quickstart.md`

- [ ] **Step 1: Check the workflow for forbidden rebase logic**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
rg -n "git pull --rebase hf main|git merge hf|git rebase hf" .github/workflows/huggingface_sync.yml
```

Expected: no matches.

- [ ] **Step 2: Confirm the workflow publishes with force-with-lease**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
rg -n "git push --force-with-lease hf HEAD:main|git push hf HEAD:main" .github/workflows/huggingface_sync.yml
```

Expected: one match for `git push --force-with-lease hf HEAD:main` and one
match for `git push hf HEAD:main` in the branch-creation path.

- [ ] **Step 3: Confirm the canonical docs teach the `hf.space` webhook and repo-authoritative push**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
rg -n "force-with-lease hf main:main|hf\.space/webhook|huggingface\.co/spaces/<owner>/<space>" docs/guides/deployment.md docs/guides/quickstart.md docs/guides/line-setup.md docs/LINE_SETUP.md docs/reference/quick-reference.md
```

Expected: matches show `git push --force-with-lease hf main:main`,
`hf.space/webhook`, and warnings against using the
`huggingface.co/spaces/...` page URL.

- [ ] **Step 4: Capture the working tree before the migration step**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git status --short
```

Expected: only intentional local changes are present; no unexpected untracked migration artifacts.

---

### Task 2: Perform the One-Time Hugging Face Branch Migration

**Files:**

- Operational target: Hugging Face remote `hf`

- [ ] **Step 1: Verify local branch and remote targets**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git branch --show-current
git remote -v
```

Expected: current branch is `main`; `origin` points at `TeacherEvan/TeacherBOY`; `hf` may or may not already exist.

- [ ] **Step 2: Configure the Hugging Face remote to the Space repo**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
if git remote get-url hf >/dev/null 2>&1; then
  git remote set-url hf https://huggingface.co/spaces/EvilEvan/TeacherBOY
else
  git remote add hf https://huggingface.co/spaces/EvilEvan/TeacherBOY
fi
git remote get-url hf
```

Expected: printed URL is `https://huggingface.co/spaces/EvilEvan/TeacherBOY`.

- [ ] **Step 3: Snapshot the current Space branch tip before overwriting**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git ls-remote hf HEAD refs/heads/main
```

Expected: either one `HEAD`/`refs/heads/main` hash pair or no `refs/heads/main` if the branch does not exist yet.

- [ ] **Step 4: Publish GitHub `main` to the Space using a safe force-push**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
git push --force-with-lease hf main:main
```

Expected: push succeeds and updates `hf/main` to the local `main` commit.

- [ ] **Step 5: Verify the Space branch now matches local `main`**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
local_sha="$(git rev-parse main)"
remote_sha="$(git ls-remote hf refs/heads/main | awk '{print $1}')"
printf 'local=%s\nremote=%s\n' "$local_sha" "$remote_sha"
```

Expected: `local` and `remote` hashes are identical.

---

### Task 3: Verify the Live Space and Webhook Behavior

**Files:**

- Live service: `https://evilevan-teacherboy.hf.space`
- Canonical guide: `docs/guides/line-setup.md`

- [ ] **Step 1: Verify the Space health endpoint responds**

Run:

```bash
curl -sS https://evilevan-teacherboy.hf.space/health
```

Expected: JSON response containing a healthy process status.

- [ ] **Step 2: Verify the readiness endpoint responds**

Run:

```bash
curl -sS https://evilevan-teacherboy.hf.space/readiness
```

Expected: JSON response showing the app is ready after startup completes.

- [ ] **Step 3: Verify the live webhook route exists on the app host**

Run:

```bash
curl -i -X POST https://evilevan-teacherboy.hf.space/webhook
```

Expected: `HTTP/2 400` with an invalid-signature response, which proves the
route exists and is enforcing LINE signature validation.

- [ ] **Step 4: Verify the page URL still fails, to distinguish the wrong host**

Run:

```bash
curl -i -X POST https://huggingface.co/spaces/EvilEvan/TeacherBOY/webhook
```

Expected: `HTTP/2 404` or `Cannot POST /spaces/EvilEvan/TeacherBOY/webhook`,
which confirms why LINE verification fails when configured against the page
URL.

- [ ] **Step 5: Update the LINE channel webhook URL manually in the console**

Use this exact value in LINE Developers Console:

```text
https://evilevan-teacherboy.hf.space/webhook
```

Expected: after clicking **Update** and **Verify**, LINE reports success with HTTP `200`.

---

### Task 4: Confirm Post-Migration Operator State

**Files:**

- Review: `.github/workflows/huggingface_sync.yml`
- Review: `docs/guides/deployment.md`
- Review: `docs/guides/line-setup.md`

- [ ] **Step 1: Confirm the next GitHub push will follow the same deploy model**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
sed -n '1,120p' .github/workflows/huggingface_sync.yml
```

Expected: the workflow still contains only publish logic and no pull/rebase behavior.

- [ ] **Step 2: Confirm the operator docs match the live behavior**

Run:

```bash
cd /home/ewaldt/Documents/VS/Other/Bot/TeacherBOY
sed -n '68,115p' docs/guides/deployment.md
sed -n '1,80p' docs/guides/line-setup.md
```

Expected: deployment docs show `git push --force-with-lease hf main:main`,
and LINE docs show the `hf.space` webhook example plus the warning against
the `huggingface.co/spaces/...` page URL.

- [ ] **Step 3: Record the migration result in the working session notes or PR summary**

Include this checklist in your summary:

```text
- Hugging Face Space branch overwritten from GitHub main with --force-with-lease
- Live Space health and readiness endpoints verified
- Live /webhook route verified on hf.space host
- LINE webhook URL updated to https://evilevan-teacherboy.hf.space/webhook
- Operator docs verified against live behavior
```

Expected: the migration can be audited without re-deriving the deploy model.
