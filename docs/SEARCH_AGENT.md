# Search Agent - User Guide

## Overview

The Ms. Green Search Agent provides web search capabilities using the Brave Search API. It searches the web and provides an AI-generated summary with source citations.

## How to Use

### Trigger

Send a search query using the trigger phrase:

```
Ms. Green search <your query>
```

**Examples:**

```
Ms. Green search Python tutorials
Ms. Green search best Thai restaurants in Bangkok
Ms. Green search how to learn Thai language
Ms. Green search weather forecast Phuket tomorrow
```

### Response Format

Ms. Green returns:
1. **AI Summary** - A concise answer synthesized from search results
2. **Sources** - Numbered list of source URLs for verification

**Example:**

```
User: Ms. Green search Python async tutorial

Ms. Green: 🔍 **Search Results: "Python async tutorial"**

**Summary:**
Python's asyncio library enables concurrent programming using async/await syntax. Key concepts:
- `async def` defines coroutine functions
- `await` pauses execution until awaitable completes
- `asyncio.gather()` runs multiple coroutines concurrently
- Event loop manages task scheduling

**Sources:**
1. https://docs.python.org/3/library/asyncio.html
2. https://realpython.com/async-io-python/
3. https://docs.python.org/3/howto/async.html
3. https://medium.com/@yeraydiazdiaz/async-python-...
```

## Access Control

| Context | User Type | Access |
|---------|-----------|--------|
| Private Chat (DM) | Any user | ✅ Full access |
| Group/Room | Admin | ✅ Full access |
| Group/Room | Regular user | ❌ Blocked (translation only) |

**Note**: In groups, only admins can use search. Regular users will get translation instead.

## Rate Limits

- Standard search rate limits apply
- Admins: Unlimited
- Regular users: Standard limits per chat

## Configuration

Requires Brave Search API key:

```env
# Get key from: https://brave.com/search/api/
BRAVE_SEARCH_API_KEY=your_api_key_here
```

Without this key, the agent will respond with a configuration error.

## Features

- **Natural language queries** - No special syntax needed
- **AI-powered summary** - Not just raw links, but synthesized answers
- **Source citations** - Every claim backed by source URL
- **Thai & English support** - Queries in either language work
- **Recent information** - Brave Search provides up-to-date results

## Example Use Cases

### Research
```
Ms. Green search latest AI developments 2026
```

### Travel Planning
```
Ms. Green search things to do in Chiang Mai December
```

### Technical Help
```
Ms. Green search Docker compose tutorial for beginners
```

### Language Learning
```
Ms. Green search Thai grammar particles explained
```

### Current Events
```
Ms. Green search Thailand election results 2026
```

## Troubleshooting

### "Search Agent: Brave Search not configured"
→ Add `BRAVE_SEARCH_API_KEY` to your `.env` file

### "Search not available in this chat"
→ You're in a group chat. Only admins can use search in groups. Use DM for private search.

### No results found
→ Try rephrasing your query or use more specific terms

## Technical Details

### Agent Priority

- Priority 8 (after Calendar/Profiler, before LLM/Translation)
- Handles `Ms. Green search <query>` pattern

### Files

- `src/agents/search_agent.py` - Main agent logic
- `src/services/brave_search_service.py` - Brave API integration
- `tests/test_search_agent.py` - Test suite

### Flow

```
User: "Ms. Green search Python async"
        │
        ▼
SearchAgent.should_handle() → True (matches pattern)
        │
        ▼
SearchAgent.handle()
        │
        ├─► Brave Search API call
        │
        ├─► Get top 5-10 results
        │
        ├─► LLM (Gemini primary, fallback chain) summarizes results
        │
        └─► Return formatted response with sources
```

## Related Documentation

- [Quick Reference](reference/quick-reference.md) - Command summary
- [Brave Search API](https://brave.com/search/api/) - API documentation
- [Admin Commands](ADMIN_COMMANDS.md) - Admin search access

---

**Last Updated**: June 2026  
**Version**: 1.0.0