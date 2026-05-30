# 2026-05-30 Review Feedback Follow-up

- [x] Add regression coverage for AI review fallback when the GitHub provider raises
- [x] Fall back to OpenRouter when the primary AI review provider fails with an exception
- [x] Exclude undated staff memory items from the weekly due view
- [x] Ignore bot-authored buffered messages when selecting content for `KPS review`
- [x] Prevent a second `KPS review` request from overwriting an unanswered pending review
- [x] Correct the staff-answer typo in the review agent response
- [x] Run focused verification for AI review, review agent, staff memory, identity, and main startup tests