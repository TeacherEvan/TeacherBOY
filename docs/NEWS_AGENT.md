# News Agent - Quick Reference

## Overview

The NewsAgent provides real-time weather, air quality, and news headlines for Bangkok in a multi-step conversational interface.

## Trigger

- In groups/rooms: type `news` (English), `ข่าว` (Thai), or `นิวส์`
   - Friends (verified via LINE profile lookup) get the full menu (rate limited to 1/hour per chat)
   - Non-friends get trigger translation only (no menu)
- In private chat:
   - Regular users get trigger translation only (no menu)
   - Admins/moderators get the full menu (no rate limit)

## Flow

1. **Main Menu** (auto-fetched data)

   ```text
   📰 Bangkok (Updated: 12:34)

   🌡️ Temp: 32°C | 💨 PM2.5: 45 µg/m³ (Good 🟢)
   🌧️ Next 5h rain: No

   📅 Next Holiday: Jan 1 - New Year's Day
   📈 Indices: S&P 500 4,700.00 (+0.50%) | DJIA 37,000.00 (-0.20%) | FTSE 7,500.00 (+0.10%)
   ₿ Crypto: BTC $43,250.00 (+2.50%), ETH $2,300.00 (-0.10%), USDT $1.00 (+0.00%)
   💱 FX (1 THB): USD 0.027, JPY 4.000, ZAR 0.490, AUD 0.041, GBP 0.021, RUB 2.400

   📰 Headlines (Thailand):
   1. Headline 1...
   2. Headline 2...
   3. Headline 3...
   4. Headline 4...
   5. Headline 5...
   ```

2. **Headline Detail** (if user presses 1-5)
   - Shows full headline + URL
   - Any message returns to the main menu (no extra prompt is displayed)

## Configuration

Add to `.env` (optional cache tuning):

```bash
WEATHER_CACHE_TTL_SECONDS=1800  # 30 minutes
NEWS_CACHE_TTL_SECONDS=3600     # 1 hour
```

## Data Sources

- **Weather**: [Open-Meteo](https://open-meteo.com) (no API key for non-commercial use; subject to Open-Meteo terms)
- **Air Quality**: [Open-Meteo Air Quality API](https://air-quality-api.open-meteo.com) (no API key for non-commercial use; subject to Open-Meteo terms)
- **News**: Bangkok Post RSS feeds (no API key)

## Agent Priority

- Priority: **15** (runs after Translation at 10)
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

## Language-Appropriate Headline Display

When the request is triggered in Thai (`ข่าว`, `นิวส์`), the News Agent
automatically translates English Bangkok Post headlines into Thai before
displaying them. English triggers keep the original headlines. The flow is:

- Parse Bangkok Post RSS.
- If Thai UI requested, call the shared AI translation service.
- Fall back gracefully to the original English text if translation fails.

This is covered by tests in `tests/test_news_language_display.py`.

## Limitations

- RSS-based headlines (best-effort; availability depends on feed uptime)
- Weather limited to Bangkok coordinates (can be extended)
- In-memory state (no persistence)

## Future Enhancements

- Support for multiple cities
- Historical weather/news data
- FlexMessage UI for richer display
- Persistent session state (Redis)
- Additional RSS feed fallback sources

## Usage Examples

Below are common interaction flows with the News Agent.

### Thai Language Flow

```text
User: ข่าว

Bot: 📰 Bangkok (อัปเดต: 12:34)

🌡️ อุณหภูมิ: 32°C | 💨 PM2.5: 45 µg/m³ (ดี 🟢)
🌧️ 5 ชม.ข้างหน้า: ไม่ (No)

📅 วันหยุดถัดไป: Jan 01 - วันขึ้นปีใหม่
📈 ดัชนี: S&P 500 4,700.00 (+0.50%) | DJIA 37,000.00 (-0.20%) | FTSE 7,500.00 (+0.10%)
₿ Crypto: BTC $43,250.00 (+2.50%), ETH $2,300.00 (-0.10%), USDT $1.00 (+0.00%)
💱 อัตราแลก (1 THB): USD 0.027, JPY 4.000, ZAR 0.490, AUD 0.041, GBP 0.021, RUB 2.400

📰 หัวข้อข่าว (Thailand):
1. รัฐบาลประกาศมาตรการใหม่เพื่อลดมลพิษ...
2. กรุงเทพฯ เตรียมพร้อมรับมือฤดูฝน...
3. ตลาดหุ้นไทยปิดบวก 15 จุด...
4. ท่องเที่ยวไทยคาดนักท่องเที่ยวพุ่ง...
5. การศึกษาไทยเตรียมปรับหลักสูตร...

---

User: 1

Bot: 📰 รัฐบาลประกาศมาตรการใหม่เพื่อลดมลพิษในกรุงเทพมหานคร

🔗 https://www.bangkokpost.com/...
```

### Edge Cases

- **Ending the session:** User types "thanks teacherboy" or any text that doesn't match 1-5, which returns to the main menu.
- **Invalid Input:** If the user types "abc" instead of 1-5, the bot replies: "❌ Please pick 1-5 (headlines)" and stays in the main menu step.
- **Thai Numerals:** The bot accepts Thai numerals (e.g., ๑ for 1) naturally.
- **Translation Priority:** While in the news flow, only 1-5 is accepted. If a user tries to translate a sentence (e.g., "ฉันต้องการข้อมูลข่าว"), the bot will reply with "❌ Please pick 1-5 (headlines)".
