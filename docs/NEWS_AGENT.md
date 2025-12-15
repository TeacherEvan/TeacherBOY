# News Agent - Quick Reference

## Overview

The NewsAgent provides real-time weather, air quality, and news headlines for Bangkok in a multi-step conversational interface.

## Trigger

Type `news` or `ข่าว` in any LINE chat to start.

## Flow

1. **Language Selection**
   - Bot asks: "1 = Thai (ไทย)" or "2 = English"
   - User responds with `1` or `2`

2. **Main Menu** (auto-fetched data)

   ```
   🌡️ Temperature (Bangkok): 32°C
   💨 PM2.5 (Bangkok): 45
   🌧️ Will it rain in next 5 hours: No

   🍃 Cannabis: Legal
   🚭 E-Cigarettes: *NOT LEGAL*
   🍺 Alcohol: Prescriptive

   📰 Top 5 Headlines Today:
   1 - Headline 1...
   2 - Headline 2...
   3 - Headline 3...
   4 - Headline 4...
   5 - Headline 5...

   💡 Press 1-5 to read more
   💡 Press 9 for resources
   ```

3. **Headline Detail** (if user presses 1-5)
   - Shows full headline + URL
   - User sends any message to return to menu

4. **Resources** (if user presses 9)
   - Shows API sources (Open-Meteo, ThaiPBS, Bangkok Post, etc.)
   - Exits news flow

## Configuration

Add to `.env`:

```bash
# Optional - for news headlines (100 req/day free tier)
NEWS_API_KEY=your_newsapi_org_key

# Optional - cache TTL settings (defaults shown)
WEATHER_CACHE_TTL_SECONDS=1800  # 30 minutes
NEWS_CACHE_TTL_SECONDS=3600     # 1 hour
```

## Data Sources

- **Weather**: [Open-Meteo](https://open-meteo.com) (free, no API key)
- **Air Quality**: [Open-Meteo Air Quality API](https://air-quality-api.open-meteo.com) (free, no API key)
- **News**: [NewsAPI.org](https://newsapi.org) (optional, 100 req/day free)

## Agent Priority

- Priority: **15** (between Translation at 10 and Calendar at 20)
- Does not interfere with translation features
- Ignores LINE system messages in brackets `[Name]`

## Session Management

- **Auto-timeout**: 5 minutes of inactivity
- **In-memory**: State lost on bot restart (by design)
- **Per-chat**: Each chat has independent news session

## Technical Details

### Files Created

- `src/services/news_session_manager.py` - Session state tracking
- `src/services/news_data_service.py` - API integration with caching
- `src/agents/news_agent.py` - Multi-step conversation handler

### Integration Points

- Registered in `src/main.py` lifespan
- Uses shared `httpx.AsyncClient` from main
- Configuration in `src/config.py`

### Caching Strategy

- Weather data: 30 minutes TTL
- News headlines: 1 hour TTL
- Shared across all chats (reduces API calls)

## Testing

```bash
# Run news agent tests
pytest tests/test_news_agent.py -v

# Run all tests
pytest
```

## Limitations

- NewsAPI.org free tier: 100 requests/day
- No historical news (only current day)
- Weather limited to Bangkok coordinates (can be extended)
- In-memory state (no persistence)

## Future Enhancements

- Support for multiple cities
- Historical weather/news data
- FlexMessage UI for richer display
- Persistent session state (Redis)
- RSS feed fallback for unlimited news
