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

- Bot identity: `data/bot_identity/profile.json`
- Staff memory: `data/staff_memory/staff_memory.json`
- Calendar reminder DM target: `notification_target_user_id` on each calendar event