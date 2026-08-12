# Ms Green Features Toggle System - Design Document

**Date:** 2026-06-07  
**Status:** 🔄 **Design Complete — Not Implemented** (as of 2026-06-14)

---

## Overview
Global feature toggle system for Ms. Green (TeacherBOY) LINE bot. Provides a LINE Rich Menu with 5 toggle buttons (Translate, Calendar/Reminders, News, Search, LLM Chat) that update a JSON config file and instantly reflect visual state (green=on, red=off).

## Architecture

### Components
1. **FeatureToggleService** (`src/services/feature_toggle_service.py`)
   - Loads/saves `data/features.json`
   - In-memory cache with hot-reload on file change
   - Provides `is_enabled(feature_key)` for agents to check

2. **Rich Menu Generator** (`src/services/rich_menu_generator.py`)
   - Generates Rich Menu image with 5 areas (green/red per feature)
   - Creates postback actions: `action=toggle&feature=<key>`
   - Updates Rich Menu via LINE Messaging API

3. **Postback Handler** (`src/handlers/postback_handler.py`)
   - Receives postback events from LINE
   - Parses `action=toggle&feature=<key>`
   - Calls FeatureToggleService, regenerates Rich Menu, replies confirmation

4. **Agent Integration**
   - BaseAgent checks `FeatureToggleService.is_enabled(self.name)` in `should_handle`
   - Disabled agents skip processing entirely

### Data Flow
```
User taps Rich Menu area
    → LINE sends postback event to webhook
    → PostbackHandler parses feature key
    → FeatureToggleService toggles state in JSON
    → RichMenuGenerator regenerates image (green/red)
    → LINE API updates Rich Menu
    → User sees instant color change
```

### Config File Schema (`data/features.json`)
```json
{
  "translate": true,
  "calendar": true,
  "news": true,
  "search": true,
  "llm": true
}
```

### Feature-to-Agent Mapping
| Feature Key | Agent Name | Priority |
|-------------|------------|----------|
| translate | TranslationAgent | 10 |
| calendar | CalendarAgent | 6 |
| news | NewsAgent / SpecialNewsAgent | 12/15 |
| search | SearchAgent | 8 |
| llm | LLMAgent | 9 |

## Error Handling
- Invalid feature key → ignore, log warning
- Config file corrupted → reset to defaults, log error
- LINE API failure → retry once, log error, keep old menu
- File permission errors → log, continue with in-memory state

## Testing Strategy
- Unit: FeatureToggleService load/save/toggle, hot-reload
- Unit: RichMenuGenerator produces valid image bytes
- Integration: PostbackHandler → service → menu update
- E2E: AgentRouter respects toggle state (mock service)

## Implementation Order
1. FeatureToggleService + config file
2. RichMenuGenerator + LINE API integration
3. PostbackHandler + webhook route
4. AgentRouter/BaseAgent integration
5. Tests for all components
