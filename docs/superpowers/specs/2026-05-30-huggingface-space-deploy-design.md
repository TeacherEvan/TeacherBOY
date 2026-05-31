# Hugging Face Space Deploy Design

Date: 2026-05-30

## Problem

The current Hugging Face sync workflow treats the Space git repository as a
peer branch by fetching and rebasing onto `hf/main` before pushing. That
creates an architectural mismatch:

- GitHub is the intended source of truth.
- The Hugging Face Space is a deployment target.
- Rebase-based sync fails when Space history diverges from GitHub history.
- Runtime Hugging Face data sync uses `HF_MEMORY_TOKEN`, while Space
   deployment uses `HF_TOKEN`, so deployment and persistence are separate
   concerns.

## Decision

Adopt a repo-authoritative deployment model:

- GitHub `main` is the only source of truth for application code.
- Hugging Face Space `main` is a deploy target, not a collaboration branch.
- No direct edits should be made in the Hugging Face Space UI.
- The deployment workflow must not merge or rebase from the Space remote.

## Recommended Architecture

Separate Hugging Face into two independent planes:

1. Runtime persistence
   - Uses `HF_MEMORY_TOKEN` plus the configured HF repo IDs.
   - Supports conversation memory, calendar sync, document memory, and history-log backup.
   - Failure mode is service/data availability.

2. Space deployment
   - Uses `HF_TOKEN` only for git-based Space deployment.
   - Publishes code from GitHub to the Space.
   - Failure mode is deployment/auth/rebuild.

This removes the current ambiguity where one workflow tries to preserve Space
history even though the Space should be reproducible from GitHub.

## Workflow Design

GitHub Actions deploy flow:

1. Trigger on push to GitHub `main`.
2. Configure authenticated `hf` remote.
3. Validate remote reachability.
4. If `hf/main` exists, fetch it only to establish the lease for a safe force-push.
5. Publish GitHub `HEAD` to `hf/main` with `git push --force-with-lease hf HEAD:main`.
6. If `hf/main` does not exist yet, create it with `git push hf HEAD:main`.

The workflow must not call `git pull`, `git merge`, or `git rebase` against the Hugging Face remote.

## Manual Sync

Use the same model manually:

```bash
git remote add hf https://huggingface.co/spaces/EvilEvan/TeacherBOY
git push --force-with-lease hf main:main
```

Use authenticated remote credentials when prompted with a Hugging Face access token.

## Migration

Because the current Space branch has already diverged from GitHub history,
the first deployment after this redesign is a deliberate overwrite of
`hf/main` from GitHub `main`.

Precondition:

- Confirm there are no Space-only changes worth preserving.

Migration action:

```bash
git push --force-with-lease hf main:main
```

## Non-Goals

- Supporting bidirectional branch reconciliation between GitHub and Hugging Face.
- Preserving direct Space UI edits.
- Using deployment workflow logic to solve runtime HF data synchronization.

## Verification

- Workflow YAML validates cleanly.
- Manual deploy command matches documented deploy model.
- Deployment guide and environment comments distinguish `HF_TOKEN` from `HF_MEMORY_TOKEN`.
- The live webhook URL remains `https://<space-host>.hf.space/webhook` and is
   unaffected by branch history.
