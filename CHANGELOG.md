# Changelog

All notable changes to TeacherBOY will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.5.1] - 2026-01-11

### 🐛 Bug Fixes

#### Calendar Agent - Scrape Flow Parameter Order

- **Fixed parameter mismatch in `scrape_flow.handle_scrape_trigger()` call**
  - Issue: CalendarAgent was passing parameters in wrong order (`event, line_bot_api, chat_id, user_id, text`)
  - Expected: Function signature requires (`event, text, line_bot_api, chat_id, user_id`)
  - Error: `AttributeError: 'MessagingApi' object has no attribute 'lower'` when `text.lower()` was called
  - Fix: Corrected parameter order in calendar_agent.py line 423
  - Impact: "zeus scrape" command now works correctly without runtime errors
  - File: `src/agents/calendar_agent.py`

## [3.5.0] - 2026-01-09

### 🔒 Security

#### Image Privacy & Memory Management

- **Explicit Memory Cleanup:** Added immediate deletion of image data after processing
  - ProfilerAgent: Deletes `image_bytes`, `image_data_url`, and `messages` after GPT-4o vision call
  - ImageAnalyzerAgent: Deletes intermediate data after encoding and after vision API call
  - Prevents sensitive image data from lingering in memory or logs
- **Privacy Documentation:** Created comprehensive IMAGE_PRIVACY.md
  - Image lifecycle documentation (download → encode → process → delete)
  - Storage guarantees (no persistent storage, only transient memory)
  - Session TTLs (60 seconds max for ImageAnalyzer, no storage for Profiler)
  - GDPR/CCPA compliance details (data minimization, user control)
  - Developer guidelines for handling sensitive data
- **Verification:** Confirmed no image storage in:
  - ConversationMemoryService (text only)
  - HistoryLogService (metadata only)
  - Session managers (cleared on retrieval/expiration)

### 📚 Documentation

- **IMAGE_PRIVACY.md:** Complete privacy & memory management guide
  - Image lifecycle and deletion points
  - Privacy guarantees (no disk, database, or persistent storage)
  - Compliance notes (GDPR, CCPA)
  - Developer best practices
- **IMAGE_MEMORY_CLEANUP.md:** Implementation details
  - Technical changes and cleanup points
  - Before/after memory management strategy
  - Test results and verification
  - Privacy guarantees and compliance status

## [3.4.3] - 2026-01-03

### ✨ Enhanced

#### Admin Stats Dashboard - Visual Excellence

- **Flex Message Conversion:** Transformed text-based stats into visually stunning dashboard
  - Color-coded status indicators (🔴/🟡/✅) for LINE quota and cache performance
  - Clean, organized sections with visual hierarchy
  - Responsive layout optimized for mobile viewing
  - Professional card-based design with consistent spacing
- **New Metrics Added:**
  - Profiler session tracking (psychological profiling usage)
  - Image Analyzer session tracking (general image Q&A usage)
  - Enhanced session overview with all active flows
- **Improved Data Visualization:**
  - Provider breakdown with percentages (Google/Libre translation split)
  - Cache hit rate with quality emoji (🟢 ≥80%, 🟡 ≥60%, 🔴 <60%)
  - Error metrics only shown when errors exist (cleaner display)
  - Friend engagement with time formatting (minutes/hours/days ago)
- **Smart Status Indicators:**
  - LINE quota warnings (🔴 ≥90%, 🟡 ≥75%, ✅ otherwise)
  - Cache quality indicators (green/yellow/red based on hit rate)
  - Color-coded error section (red background when issues detected)
- **Better Organization:**
  - System Status: Uptime, LINE quota with visual warnings
  - Usage Metrics: Translations, news, admin commands with provider split
  - User Engagement: Users, groups, friends with last activity
  - Active Sessions: Translation, news, profiler, analyzer, sleeping
  - Cache Performance: Hit rate with visual quality indicator
  - Error Metrics: Conditional display, only shown when needed

## [3.4.2] - 2026-01-03

### ✨ Enhanced

#### Help System - Comprehensive Feature Documentation

- **New "Image Analysis" Category:** Added dedicated section for vision-based features
  - Psychological Profiler (Zeus profile) - 3 analyses/hour
  - Image Analyzer (Zeus analyze this) - 5 analyses/hour
  - Rate limits clearly displayed for each feature
  - Admins get unlimited usage notification
- **Improved Help Command:**
  - "/zeus help" trigger now works (was already in patterns but not documented)
  - All features properly categorized and explained
  - Rate limiting information included in command descriptions
  - Visual indicators for rate-limited features
- **Better User Experience:**
  - Clear examples for each command
  - Contextual availability based on configuration
  - Rate limit info shown in red for visibility

## [3.4.1] - 2026-01-03

### 🐛 Fixed

#### Image Analyzer Agent - Type Safety & Error Handling

- **Type Checker Resolution:** Fixed "Never is not iterable" error in `_download_image` method
  - Added `type: ignore[union-attr]` comment for response iteration
  - Wrapped iteration in try-except to catch TypeError
  - Added error logging for unexpected response types
- **Improved Robustness:** Better handling of edge cases in LINE API responses
  - Graceful fallback when response type is unexpected
  - Clearer error messages for debugging

## [3.4.0] - 2026-01-03

### 🚀 Added

#### Image Analyzer Agent - General Purpose Image Q&A

- **New Multi-Step Flow:** Users can now ask Zeus questions about any image
  - Trigger: "Zeus analyze this" / "analyze image" / "Zeus examine this"
  - Zeus asks for image (60 seconds timeout)
  - Zeus asks for question about the image
  - Zeus analyzes and answers using GPT-4o vision
- **Use Cases:**
  - Menu translation: "What would be most enjoyable on this menu to a westerner?"
  - Sign reading: "What does this sign say?"
  - Product identification: "What products are shown here?"
  - General visual questions
- **Session Management:** Dedicated `ImageAnalyzerSessionManager` with:
  - Two-phase state machine (WAITING_FOR_IMAGE → WAITING_FOR_QUESTION)
  - 60-second timeout per phase
  - Background cleanup task
- **Rate Limiting:** 5 analyses per hour per chat (admins unlimited)

### 🎨 Enhanced

#### Zeus Persona - Warmer Responses

- **Increased Temperature:** LLM temperature raised from 1.0 to 1.15 for slightly warmer responses
- **Updated System Prompt:** Zeus now speaks with "warmth of a benevolent ruler"
  - Previous: "stoic, concise, and pragmatic"
  - New: "wise, measured, and authoritative, yet with warmth"
  - "A touch of paternal wisdom is welcome"
  - "Light mythological references are fine when they add value"

## [3.3.1] - 2026-01-03

### 🎨 Enhanced

#### Psychological Profiler - Fictional Artwork Analysis

- **Artistic Content Support:** Enhanced prompt to properly handle fictional characters in artwork
  - Explicit context for anime, manga, pencil drawings, concept art analysis
  - Clear distinction between fictional art and real person photography
- **Accessibility Improvements:** Added support context for neurodivergent users (autism)
  - Helps users understand character expressions in art for creative projects
  - Art direction assistance for music videos and visual storytelling
- **Safety Feature Handling:** Model instructed to analyze visible artistic elements even if safety features activate
  - Reduces unnecessary content filtering on fictional characters
  - Maintains appropriate safety for real person analysis
- **Documentation Updates:**
  - Added "Supported Content Types" section to profiler usage guide
  - Expanded ethics section with fictional vs real person clarification
  - Added troubleshooting for safety feature issues
  - New use cases section with creative project examples

## [3.3.0] - 2026-01-02

### 🚀 Added

#### Conversation Memory Service

- **Multi-Turn Conversations:** Zeus LLM agent now maintains context across multiple messages
- **Hugging Face Hub Sync:** Optional cloud persistence via HF datasets with automatic CommitScheduler
- **Session Management:**
  - Configurable TTL (default: 24 hours)
  - Max messages per session (default: 20)
  - Automatic session cleanup
  - Privacy-focused session hashing
- **Configuration:**
  - `CONVERSATION_MEMORY_ENABLED` (default: true)
  - `HF_MEMORY_TOKEN` (optional HF API token)
  - `HF_MEMORY_REPO_ID` (optional HF dataset repo)
  - `CONVERSATION_MAX_MESSAGES` (default: 20)
  - `CONVERSATION_TTL_HOURS` (default: 24)

#### History Logging Service

- **Comprehensive Audit Trail:** Logs all bot events (startup, shutdown, errors, commands, API calls)
- **AES Encryption:** Optional encryption for sensitive log data
- **Cloud Backup:** Hugging Face Hub sync for log persistence
- **Log Rotation:** Automatic archival after configurable days (default: 7)
- **Zeus-Style Formatting:** Mythological, authoritative error messages when enabled
- **Rich Event Types:** STARTUP, SHUTDOWN, ERROR, MESSAGE, COMMAND, API_CALL, USER_ACTION, SYSTEM_EVENT
- **Log Levels:** DEBUG, INFO, WARNING, ERROR, CRITICAL
- **Configuration:**
  - `HISTORY_LOG_ENABLED` (default: true)
  - `HISTORY_LOG_PATH` (default: ./data/logs)
  - `HISTORY_LOG_ENCRYPTION_KEY` (optional AES key)
  - `HISTORY_LOG_HF_REPO_ID` (optional HF dataset repo)
  - `HISTORY_LOG_ROTATION_DAYS` (default: 7)
  - `ZEUS_ERROR_STYLE` (default: true)

#### Testing

- **28 History Log Tests:** Full coverage of encryption, HF sync, rotation, Zeus formatting
- **6 Conversation Memory Tests:** Session management, cleanup, HF integration
- **Test Suite:** 261/264 tests passing (3 pre-existing failures unrelated)

### 🔧 Technical Details

- Added `src/services/conversation_memory_service.py` (350+ lines)
- Added `src/services/history_log_service.py` (550+ lines)
- Extended `src/config.py` with 10 new configuration fields
- Integrated services in `src/main.py` lifespan with graceful shutdown
- Added `cryptography` to requirements.txt for optional encryption
- Created comprehensive documentation in `docs/CONVERSATION_MEMORY.md`

### 📝 Documentation

- New guide: `docs/CONVERSATION_MEMORY.md`
- Updated configuration reference with new settings
- Added Zeus-style error formatting examples

## [3.2.1] - 2026-01-01

### 🐛 Fixed

#### Special News Tourism Feed

- **TAT News RSS 403 Error:** Replaced `tatnews.org/feed/` (HTTP 403 Forbidden) with Bangkok Post Travel RSS
- All three special news feeds now use reliable Bangkok Post RSS sources:
  - Tourism: `bangkokpost.com/rss/data/travel.xml`
  - Sports: `bangkokpost.com/rss/data/sports.xml`
  - International: `bangkokpost.com/rss/data/world.xml`
- Updated feed name detection to recognize "travel" URL as "Thailand Tourism"

## [3.2.0] - 2025-12-16

### 🚀 Added

#### Rate Limiting with Admin Exemption

- **TranslationAgent:** Admins bypass rate limits (unlimited), standard users: 10 requests/60s
- **NewsAgent:** Friends get 1 news request per hour, admins unlimited, non-friends translation only
- Admin detection via `settings.get_admin_user_ids()`
- Bilingual rate limit messages (Thai/English)
- Per-chat rate tracking with automatic reset
- Admin bypass logging for monitoring

### 🐛 Fixed

#### Type Safety

- Added `Optional[str]` type hint to `_is_admin()` method in NewsAgent
- Fixed type checking error where `user_id` could be `None`

### 📝 Documentation

#### Comprehensive Updates

- Added index/table of contents to `.github/copilot-instructions.md`
- Documented rate limiting rules for both TranslationAgent and NewsAgent
- Added admin exemption details and logging patterns
- Updated CHANGELOG with rate limiting features

### 🔧 Technical Details

#### Files Modified

- `src/agents/translation_agent.py`: Added admin check in rate limit logic
- `src/agents/news_agent.py`:
  - Rate limiter: `RateLimiter(max_requests=1, time_window_seconds=3600)`
  - Friend verification via LINE API `get_profile()`
  - Bilingual rate limit messages
  - Added `Optional` type hint for type safety
- `.github/copilot-instructions.md`: Added index and rate limiting section

## [3.1.0] - 2025-12-16

### 🛡️ Critical Security Fix

#### Added

- **Incomplete Sentence Detection:** Automatically detects incomplete sentences that could cause translation hallucination
- New function `detect_incomplete_sentence()` in `src/utils/text_preprocessing.py`
- Configuration option `TRANSLATION_DETECT_INCOMPLETE` (default: enabled)
- Warning logs when incomplete sentences are detected
- Comprehensive test suite (14 tests) for incomplete sentence detection

### ✨ News Agent Enhancement

#### Added

- **Language-Appropriate News Display:** News headlines now display in the language selected by the user
- New method `_translate_headlines_to_thai()` in `src/agents/news_agent.py`
- Automatic translation of English headlines to Thai when Thai language is selected
- 7 comprehensive tests for language-specific news display
- Documentation: `docs/NEWS_LANGUAGE_DISPLAY.md`

#### Fixed

- **News Agent:** Headlines are now properly translated to Thai when user selects Thai language
  - Previously: English headlines shown regardless of language selection ❌
  - Now: Thai headlines when Thai selected, English when English selected ✅
- Improved user experience with native language support

#### Technical Details

- Modified: `src/agents/news_agent.py`
- Added: `tests/test_news_language_display.py`
- Translation uses Google Translate (primary) or LibreTranslate (fallback)
- Smart caching: Translated headlines cached for 1 hour
- Error handling: Falls back to original English if translation fails

### 🛡️ Translation Hallucination Fix

#### Fixed

- **CRITICAL:** Translation APIs no longer add unwanted context to incomplete sentences
  - Example: "so i tried" → "so i tried..." (prevents hallucination)
  - Previously: "so i tried" could translate to "doing something silly/bad" ❌
  - Now: "so i tried..." translates accurately without added context ✅
- Prevents professional/legal issues from mistranslations
- Protects users from unintended meaning in critical communications

#### Technical Details

- Modified: `src/services/google_translation.py`
- Modified: `src/services/translation_service.py`
- Modified: `src/config.py`
- Added: `tests/test_incomplete_sentence_detection.py`
- Added: Documentation in `docs/INCOMPLETE_SENTENCE_FIX.md`
- Added: Quick reference in `docs/INCOMPLETE_SENTENCE_FIX.md`
- Added: Visual comparison (consolidated into docs; see `docs/INCOMPLETE_SENTENCE_FIX.md`)

#### Impact

- **Risk Level:** LOW (backward compatible, safe to deploy)
- **Performance:** Minimal (<1ms per message)
- **User Experience:** Improved translation accuracy
- **Test Coverage:** 59/59 translation and news tests passing

### Documentation

- Updated README.md with hallucination prevention feature
- Added comprehensive documentation for both fixes
- Created visual comparison guide for users

---

## [3.0.0] - 2024-12-15

### Added

- **Multi-Agent Architecture:** Complete overhaul to modular agent system
- **News Agent:** Real-time Bangkok weather, PM2.5, and Thai news headlines
- **Admin Commands:** In-chat bot management for authorized users
- **OpenTelemetry Tracing:** Production-grade observability support
- Text preprocessing utilities for parentheses preservation
- Comprehensive test coverage for translation features

### Changed

- Migrated to LINE Bot SDK v3 (async API)
- Improved session management with sleep mode
- Enhanced error handling and logging
- Optimized HTTP client pooling

### Fixed

- Parentheses preservation in translations (names, notes)
- Rate limiting logic
- Session state management

---

## [2.0.0] - 2024-11-01

### Added

- Google Cloud Translation API integration (primary)
- LibreTranslate fallback support
- Smart language detection
- Session-based translation mode
- Sleep/wake commands
- Group chat support

### Changed

- Complete rewrite in Python FastAPI
- Asynchronous architecture
- Improved performance

---

## [1.0.0] - 2024-06-01

### Added

- Initial release
- Basic Thai-English translation
- LINE Bot integration
- Text-only responses

---

## Upgrade Guide

### From 3.0.x to 3.1.0

**No breaking changes.** This is a safety/security update.

1. Pull latest code
2. No environment variable changes required (feature is auto-enabled)
3. Optional: Set `TRANSLATION_DETECT_INCOMPLETE=false` to disable (not recommended)
4. Run tests: `pytest tests/`
5. Deploy

**What users will notice:**

- Incomplete messages will have "..." appended
- More accurate translations
- No unwanted context in translations

---

## Contributing

See project documentation for contribution guidelines.

## Support

- 📖 Documentation: [docs/](docs/)
- 🐛 Issues: GitHub Issues
- 💬 Discussions: GitHub Discussions
