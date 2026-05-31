# Ms. Green Staff Assistant

## Overview

The bot now exposes its staff-assistant workflows through the `Ms. Green`
runtime identity.

## Core Commands

- `Ms. Green review`
  Reviews the last recent non-English message from the current chat.
  The chat gets a short acknowledgement, and the requester receives the review in DM.

- `Ms. Green whats important this week?`
  Summarizes the next 7 days by combining calendar events and structured staff-memory items.

- `Ms. Green who do you work for?`
  Returns the fixed staff-assistant response for KPS employees.

## Translation Behavior

Automatic plain-Thai translation is disabled.
Translation and summarization now happen only through explicit review-style flows.

AI provider order:

1. GitHub Models `openai/gpt-4o-mini`
2. OpenRouter `openai/gpt-4o`
3. Regex-only fallback for calendar date extraction

## Persistence

- Bot identity uses `BOT_IDENTITY_STORAGE_PATH` for runtime identity overrides.
- Staff memory uses `STAFF_MEMORY_STORAGE_PATH` for local review-agent memory, or Convex when `PERSISTENCE_BACKEND=convex`.
- Calendar reminder DM routing still depends on `notification_target_user_id` on each calendar event.
- For the shared storage contract and mounted-volume examples, see [Environment variables](reference/environment.md).

## Structured Backend Option

Set `PERSISTENCE_BACKEND=convex` to make Convex the primary structured backend for:

- review-agent staff memory
- calendar events and reminder state
- future admin configuration records via Convex `appSettings`

Required Convex environment variables:

- `CONVEX_DEPLOYMENT_URL`
- `CONVEX_SYNC_TOKEN`
- `CONVEX_REQUEST_TIMEOUT_SECONDS`

The admin-only configuration window is not implemented yet.
Convex `appSettings` is the persistence target reserved for that future work.

Rollback path:

- Set `PERSISTENCE_BACKEND=local`
- Restart the app
