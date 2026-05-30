# Maintainer Notes

This page consolidates the repository's active documentation-maintenance rules and architecture simplification constraints.

## Documentation source of truth

- Keep user-facing and developer-facing docs under `docs/`.
- Keep the root directory focused on the project entry points: `README.md`, `CHANGELOG.md`, and `SECURITY.md`.
- Prefer updating canonical docs instead of creating one-off summary files in the repo root.
- The current exception is `INTEGRATION_ECOSYSTEM_AUDIT.md`, which remains at the
    repo root as the active long-form simplification roadmap referenced by
    maintainer guidance.

## When docs must be updated

Update documentation immediately for:

- required environment variable changes
- security-sensitive configuration changes
- command or trigger changes
- routing or priority changes in agents
- deployment workflow changes

## Simplification constraints

These are the active maintainability rules already enforced by project guidance:

- Agents should stay under 600 lines.
- Services should stay under 500 lines.
- Flows should stay under 400 lines.
- Prefer lazy loading for heavyweight agents, flows, and data.
- Use dependency injection for services instead of direct imports.
- Preserve backward compatibility for public behavior unless explicitly changing it.
- Keep coverage at or above 94%.

## Documentation cleanup policy

- Merge duplicate rollout summaries into canonical docs or `CHANGELOG.md`.
- Delete redirect stubs once canonical links are updated.
- Treat temporary audit reports, checklists, and implementation summaries as disposable unless they are still actively referenced.
- If a historical note contains unique architectural reasoning,
  summarize that reasoning into a canonical doc before deleting the original.

## Preferred documentation layout

- `docs/guides/` for setup, deployment, and operator workflows
- `docs/architecture/` for system behavior and structure
- `docs/reference/` for environment variables, commands, and maintainer-facing constraints
- root-level docs only when they are repo entry points or security/release records

## Pre-merge doc checks

- Remove or fix broken internal links.
- Ensure examples match current runtime behavior.
- Prefer the current project name `Zeus`, with `TeacherBOY` used only when needed for compatibility or history.
- If architecture changed, update both overview and agent routing docs.
- Update [docs/architecture/overview.md](../architecture/overview.md).
- Update [docs/architecture/agents.md](../architecture/agents.md).

---

**Last Updated:** 2026-05-30  
**Audience:** Developers  
**Status:** Stable
