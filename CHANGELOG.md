# Changelog

All notable changes to TeacherBOY will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
  * Rate limiter: `RateLimiter(max_requests=1, time_window_seconds=3600)`
  * Friend verification via LINE API `get_profile()`
  * Bilingual rate limit messages
  * Added `Optional` type hint for type safety
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
- Added: Documentation in `TRANSLATION_HALLUCINATION_FIX.md`
- Added: Quick reference in `docs/INCOMPLETE_SENTENCE_FIX.md`
- Added: Visual comparison in `TRANSLATION_FIX_COMPARISON.md`

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

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

## Support

- 📖 Documentation: [docs/](docs/)
- 🐛 Issues: GitHub Issues
- 💬 Discussions: GitHub Discussions
