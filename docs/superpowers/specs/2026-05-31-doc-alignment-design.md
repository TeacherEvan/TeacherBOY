# Documentation Alignment Design

## Summary

This design aligns three equally important documentation surfaces around
storage, persistence, and runtime behavior:

- `README.md`
- `docs/reference/environment.md`
- `.github/copilot-instructions.md`

The goal is to keep shared facts consistent while avoiding redundant,
full-detail repetition. Each document keeps the depth appropriate to its
audience, and feature docs retain behavior-focused content with links back to
the canonical configuration reference.

## Goal

Create a documentation model where the repository entry point, the canonical
configuration reference, and contributor/runtime instructions all agree on the
same storage and persistence contract without duplicating the same full
explanations in multiple places.

## Non-Goals

- Do not introduce a new canonical storage explainer page.
- Do not rewrite unrelated feature documentation beyond stale storage,
  identity, or persistence references that conflict with current behavior.
- Do not change runtime behavior, configuration semantics, or implementation.
- Do not remove historical notes when they still add context, as long as they
  are clearly historical.

## Ownership Model

### `README.md`

`README.md` remains the high-level repository entry point. It should explain:

- what the system is
- how to run it
- where to find deeper documentation
- one short storage and persistence contract

It should not become the full environment-variable reference.

### `docs/reference/environment.md`

This is the canonical source for configuration semantics. It owns:

- local storage path variables
- HF repo ID variables
- mounted-path examples
- precise wording for what each storage variable actually does
- the storage contract used elsewhere in summarized form

### `.github/copilot-instructions.md`

This remains a contributor/runtime architecture guide. It should describe:

- which persistence surfaces exist
- where the owning code paths live
- what is true at runtime about local storage, HF sync, and mounted paths

It should avoid repeating operator-focused setup walkthroughs already covered
in `docs/`.

### Feature Docs

Feature docs should keep feature behavior and feature-specific caveats. They
should not repeat the full shared storage explanation when a short note plus a
link to `docs/reference/environment.md` is enough.

## Storage Contract

The aligned storage contract across all three major surfaces is:

- mounted local paths back local filesystem state
- HF dataset repos remain separate by data type
- `docs/reference/environment.md` defines the exact semantics of each variable
- conversation memory uses `CONVERSATION_STORAGE_PATH` as the local HF-backed
  working/cache path, not as standalone restart persistence by itself
- review-agent staff memory uses `STAFF_MEMORY_STORAGE_PATH`
- bot identity uses `BOT_IDENTITY_STORAGE_PATH`
- scheduler jobs are not persisted as a task store in the current
  implementation

## Proposed File Actions

### `README.md`

- Add or tighten one compact storage and persistence section.
- Keep only the short contract and links to deeper docs.
- Remove repeated low-level config explanation when it duplicates
  `docs/reference/environment.md`.

### `docs/reference/environment.md`

- Keep as the canonical config reference.
- Ensure each storage variable has one precise definition.
- Keep the mounted-volume example.
- Add or preserve a concise storage contract subsection.
- Keep terminology aligned with current runtime behavior.

### `.github/copilot-instructions.md`

- Update stale runtime facts about storage surfaces and HF sync.
- Add mounted-path support facts where missing.
- Compress repeated operator setup details when they belong in `docs/`.
- Preserve contributor-relevant architecture context.

### `docs/CONVERSATION_MEMORY.md`

- Keep usage, behavior, and caveats.
- Keep only a short feature-specific persistence explanation.
- Link to `docs/reference/environment.md` for full variable semantics.

### `docs/DOCUMENT_MEMORY.md`

- Normalize identity naming where stale.
- Trim duplicated storage/HF setup detail to feature-specific notes plus a
  pointer to the environment reference.

### `docs/CALENDAR_REMINDERS.md`

- Keep calendar-specific persistence behavior.
- Remove or compress generic HF-storage explanation already covered centrally.

### `docs/KPS_ASSISTANT.md`

- Replace stale hardcoded local-path wording.
- Keep only the minimal persistence facts needed for the staff-assistant
  feature.
- Point readers to the canonical environment reference for full configuration.

## Validation Strategy

After implementation, validate with:

- targeted search for stale identity/provider/storage wording across
  `README.md`, `docs/`, and `.github/copilot-instructions.md`
- markdown diagnostics on edited docs
- a broken-link sanity pass for changed internal links
- one independent review focused on doc accuracy, redundancy removal, and
  alignment across the three equal-priority sources

## Risks and Mitigations

### Risk: Over-pruning useful detail

If summarized too aggressively, feature docs may become less useful.

Mitigation:

- keep behavior and feature caveats in the feature docs
- remove only duplicated shared config explanation

### Risk: Inconsistent phrasing between the three major sources

If each document uses different language for the same storage behavior,
confusion remains.

Mitigation:

- define one storage contract in the environment reference
- mirror it in shorter form in `README.md` and
  `.github/copilot-instructions.md`

### Risk: Historical identity/provider names are erased where they still matter

Some docs may need compatibility or history context.

Mitigation:

- normalize current-runtime guidance
- keep historical references only when explicitly framed as historical or
  compatibility context

## Acceptance Criteria

- `README.md`, `docs/reference/environment.md`, and
  `.github/copilot-instructions.md` agree on storage and persistence behavior
- duplicate storage guidance is reduced rather than copied into more places
- feature docs keep their feature-specific behavior but point back to the
  canonical environment reference for full configuration semantics
- stale hardcoded or outdated storage references are removed or corrected
- updated docs match current runtime behavior
