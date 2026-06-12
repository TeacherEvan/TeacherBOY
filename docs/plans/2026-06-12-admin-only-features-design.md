# Admin-Only Features Design

## Overview
Restrict specific bot features to admins and moderators only. Non-privileged users attempting to use these features will have their messages silently ignored (agent returns `False` from `should_handle`), allowing other agents to handle or no response if no other agent matches.

## Features to Restrict

| Agent | Current Priority | Features to Restrict |
|-------|------------------|---------------------|
| NewsAgent | 15 | `news`, `ข่าว`, `นิวส์` triggers (full flow) |
| CalendarAgent | 6 | All triggers: view, add, remove, scrape, discrete scrape |
| ImageAnalyzerAgent | 7 | `analyze`, `analyze this`, `analyze image` triggers |
| ProfilerAgent | 7 | `profile`, `read face`, `face analysis`, etc. triggers |
| SearchAgent | 8 | Already restricts - admins can search anywhere, others via group rules |
| SpecialNewsAgent | 12 | Already restricts - privileged users can use anywhere |

## Access Control Logic

Use existing `privilege_service.is_privileged(user_id)` which checks:
1. In-memory claimed admins (`/admin claim <key>`)
2. Environment-based admins (`ADMIN_USER_IDS` from config)
3. Claimed moderators (persisted to `data/moderators.json`)
4. Environment-based moderators (`MODERATOR_USER_IDS` from config)

## Implementation Approach

### For each agent's `should_handle()` method:
1. Add early check: if trigger matches but user is not privileged → return `False`
2. Keep existing logic for privileged users
3. No response message sent (silent ignore)

### Files to Modify:
1. `src/agents/news_agent.py` - Add privilege check in `should_handle`
2. `src/agents/calendar_agent.py` - Add privilege check in `should_handle`
3. `src/agents/image_analyzer_agent.py` - Add privilege check in `should_handle`
4. `src/agents/profiler_agent.py` - Add privilege check in `should_handle`

### Testing Strategy:
- Each agent: test that privileged user can trigger, non-privileged cannot
- TDD: Write failing tests first, then implement

## Design Decisions

### Why silent ignore?
- Prevents feature discovery by non-privileged users
- Avoids cluttering chat with "admin only" messages
- Allows other agents (like LLMAgent) to potentially handle the message

### Why use `is_privileged()` not `is_admin()`?
- Moderators already have similar elevated access for news features
- Consistent with existing SpecialNewsAgent pattern
- Single source of truth for privilege checks

### Why modify `should_handle` not `handle`?
- `should_handle` determines routing priority
- Returning `False` lets router try next agent
- `handle` only runs after `should_handle` returns `True`

## Migration Notes
- No database migrations needed
- Existing admin/moderator configs work unchanged
- No breaking changes to privileged user experience

## Rollback Plan
If issues arise:
1. Revert changes to the 4 agent files
2. Features return to previous access levels
3. No data corruption possible