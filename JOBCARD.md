# Job Cards

## Job Card: TeacherBOY Enhancements - Welcome Message, News Frequency, Special News, Admin Stats

**Status:** Completed ✅

## Summary

- Changed welcome message to "Welcome friend" with Thai translation "ยินดีต้อนรับเพื่อน" sent on FollowEvent.
- Updated news headlines/sources update frequency from 1 hour to 2 hours by changing cache TTL.
- Dramatically enhanced "/special news" command with Flex Message carousel for better visual experience, showing tourism, sports, and international news in interactive bubbles.
- Enhanced "/admin stats" to display current tourism news headlines in the dashboard.

## Changes Made

1. **Welcome Message:** Added push message on FollowEvent in main.py for new friends.
2. **News Frequency:** Modified cache TTL in news_data_service.py from 3600 to 7200 seconds.
3. **Special News Enhancement:** Converted to Flex carousel with tappable headlines, fallback to text.
4. **Admin Stats Tourism News:** Added section fetching and displaying recent tourism news in stats dashboard.

## 5 Important Notes

1. Welcome message uses push API since FollowEvent has no reply_token.
2. News cache TTL change affects all news refreshes, improving API efficiency.
3. Special news Flex messages provide premium UX, with text fallback for compatibility.
4. Admin stats tourism news uses existing news service, no additional API calls.
5. All changes maintain backward compatibility and error handling.

## Suggested Validation

- Test welcome message by adding bot as friend.
- Verify news updates every 2 hours by checking cache timestamps.
- Test /special news in DM to see Flex carousel.
- Check /admin stats includes tourism news section.

---

## Job Card — Remove “Legalities” From News Menu

**Status:** Completed ✅

## Summary of Removal

- Removed the "legalities" section from NewsAgent output so the Bangkok news menu no longer shows cannabis/e-cig/alcohol status.
- Updated documentation to reflect the current NewsAgent menu (weather/PM2.5/rain, next holiday, indices, crypto incl. USDT, FX rates, headlines 1–5 interactive).

## Important Notes on Removal

1. Free-tier message limits: Prefer local unit tests/mocks over live LINE messages to avoid consuming free-tier quotas.
2. Keep manual validation minimal: after tests are green, validate with 1–2 real messages in a test group only.
3. Access model stays the same: group/room friends get the full menu; non-friends get trigger translation only; private chats remain trigger translation only.
4. Interactivity stays headlines-only: only selections 1–5 should return headline detail + link.
5. State/metrics are in-memory: session state and counters reset on process restart (expected).

## Suggested Validation (Low-Quota)

- Local: run `pytest` once.
- Manual (optional): send `news` in a friend-eligible group; confirm no legal-status block; reply `1` and confirm the detail + link.

---

## Job Card: TeacherBOY Overhaul (Historical)

**Status:** Completed ✅  
**Date:** December 9, 2025  
**Assignee:** Senior Principal Architect (Copilot)

## 📋 Task Overview

Comprehensive overhaul of the TeacherBOY LINE Bot to elevate it to production-grade quality, focusing on performance, UX, and code maintainability.

## 🔧 Changes Implemented

### Phase 4: User Experience Refinement (Current)

- **Silent Join:** Removed welcome message to reduce noise in groups.
- **Silent Activation:** Bot only activates when Thai text is detected.
- **Text-Only Responses:** Replaced Flex Messages with simple text for cleaner chat history.
- **Docker Deployment:** Standardized on Docker for consistent runtime environment.
- **Calendar Freeze:** Deprecated Calendar Agent to focus on core translation features.

### Phase 1: Discovery & Strategy

- **Audit:** Identified blocking synchronous calls in `message_handler.py` and inefficient HTTP client usage in `translation_service.py`.
- **Strategy:** Adopted full async architecture using FastAPI's `lifespan` and `httpx`.

### Phase 2: Refactor & Optimization

- **Async Architecture:**
  - Replaced `handle_text_message_sync` with native `async def handle_text_message`.
  - Implemented manual webhook event parsing to bypass synchronous SDK limitations.
- **Connection Pooling:**
  - Implemented `httpx.AsyncClient` singleton managed by FastAPI lifespan events.
  - Eliminated per-request client creation overhead.
- **UX Upgrade:**
  - Designed and implemented **Flex Messages** for translation results.
  - Added visual indicators (Flags 🇹🇭/🇬🇧) and clear layout.

### Phase 3: Quality Assurance

- **Type Safety:** Added type hints to all services and handlers.
- **Error Handling:** Improved error logging and graceful failure modes in webhook handling.
- **Linting:** Fixed f-string and logic redundancies.

## 📈 Performance Improvements

- **Latency:** Reduced latency by reusing HTTP connections to LibreTranslate.
- **Concurrency:** Non-blocking I/O allows handling multiple concurrent webhook requests efficiently.

## 📝 Next Steps / Recommendations

- **Testing:** Add unit tests for the new async handlers (requires `pytest-asyncio`).
- **Caching:** Implement Redis caching for frequent translations to save API costs.
- **Deployment:** Set up CI/CD pipeline for automated testing and deployment.
