# News Agent - Usage Example

## LINE Chat Example

### Example 1: Thai Language Flow

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

---

User: ok

Bot: (Returns to main menu with weather/news)
```

### Example 2: English Language Flow

```text
User: news

Bot: 📰 Bangkok (Updated: 12:34)

🌡️ Temp: 32°C | 💨 PM2.5: 45 µg/m³ (Good 🟢)
🌧️ Next 5h rain: No

📅 Next Holiday: Jan 01 - New Year's Day
📈 Indices: S&P 500 4,700.00 (+0.50%) | DJIA 37,000.00 (-0.20%) | FTSE 7,500.00 (+0.10%)
₿ Crypto: BTC $43,250.00 (+2.50%), ETH $2,300.00 (-0.10%), USDT $1.00 (+0.00%)
💱 FX (1 THB): USD 0.027, JPY 4.000, ZAR 0.490, AUD 0.041, GBP 0.021, RUB 2.400

📰 Headlines (Thailand):
1. Government announces new pollution control measures...
2. Bangkok prepares for rainy season...
3. Thai stock market closes up 15 points...
4. Tourism industry expects surge in visitors...
5. Education ministry plans curriculum reform...

---

User: 3

Bot: 📰 Thai stock market closes up 15 points amid positive investor sentiment

🔗 https://www.bangkokpost.com/business/...

---

User: back

Bot: (Returns to main menu)
```

## Edge Cases

### Ending the News Session

```text
User: thanks teacherboy
Bot: 👋 News session ended. Type 'news' or 'ข่าว' to start again!
```

### Invalid Input

```text
User: news
Bot: (menu)

User: abc
Bot: ❌ Please pick 1-5 (headlines)

(Stays in main menu step)
```

### Thai Numerals

```text
User: ข่าว
Bot: (เมนู)

User: ๑
Bot: (Accepts Thai numeral ๑ as 1, shows headline 1 detail)
```

## Concurrent Usage

### Translation + News (Different Chats)

```text
Chat A (User 1): สวัสดี
Bot: Hello

Chat B (User 2): news
Bot: (News menu)

Chat A (User 1): ฉันชื่อจอห์น
Bot: My name is John

Chat B (User 2): 1
Bot: (Shows headline 1 detail)

(Both agents work independently, no conflicts)
```

### Translation Priority Over News

```text
User: news
Bot: (News menu)

User: ฉันต้องการข้อมูลข่าว
Bot: ❌ Please pick 1-5 (headlines)

(While in the news flow, only 1-5 is accepted)
```

## Group Chat Usage

```text
[LINE Group: Bangkok Expats]

User A: news
Bot: (News menu to whole group)

User B: What's the weather?
(Ignored - not in news flow, not Thai text)

User A: 2
Bot: (News menu to whole group)

User C: 1
Bot: (Shows headline 1 to whole group)
```

## Testing Locally

Run the bot locally to test:

```bash
# Start the bot
python -m uvicorn src.main:app --reload --port 8000

# In ngrok (separate terminal)
ngrok http 8000

# Update LINE webhook URL to:
https://YOUR-NGROK-URL/webhook

# Test in LINE app
- Add bot as friend
- Send "news"
- Follow the flow!
```

## API Call Monitoring

Watch the logs to see caching in action:

```text
2025-12-15 10:30:00 - INFO - 📰 Fetched fresh weather data
2025-12-15 10:30:05 - INFO - 📰 Fetched fresh en news headlines
2025-12-15 10:35:00 - INFO - 📰 Using cached weather data
2025-12-15 10:35:05 - INFO - 📰 Using cached en news headlines
```

Cache hits = No API calls = Faster response + Lower costs!