# Admin Wake And Retention Hardening Design

## Goal

Harden and verify five related behaviors around translation wake/sleep control, admin parsing, user retention, and help visibility so they behave correctly in production group chats and remain protected by regression tests.

## Scope

The implementation covers:

1. Translation wake behavior when a sleeping chat receives Thai text from an admin.
2. Alias-aware sleep command matching and privileged-only indefinite sleep.
3. Flexible `Assistant add = ...` moderator parsing.
4. Structured retention of follow events and inbound routed interactions.
5. Preservation of the help-menu block for non-privileged users in groups and rooms.

## Design

The current code paths already contain most of the intended runtime behavior in [src/agents/translation_agent.py](src/agents/translation_agent.py), [src/agents/admin_agent.py](src/agents/admin_agent.py), [src/main.py](src/main.py), and [src/agents/help_agent.py](src/agents/help_agent.py). The primary risk is incomplete or missing regression coverage, especially for cross-cutting behavior that depends on session state and webhook routing.

The implementation should therefore proceed slice-by-slice: add a failing regression test for one behavior, verify the failure, make the smallest production fix only if the test exposes a gap, and then rerun the narrow check. Existing help gating coverage in [tests/test_private_help.py](tests/test_private_help.py) should be treated as preserved behavior and re-verified in the final pass rather than reimplemented.

## Testing Strategy

Use narrow pytest targets for each slice first, then run one combined verification command over the touched test files. Each new or updated test must demonstrate a real regression boundary: sleeping chat wake reset, alias-based stop phrases, flexible moderator parsing, and follow-event persistence.