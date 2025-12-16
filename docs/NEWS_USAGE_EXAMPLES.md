# News Agent - Usage Example

## LINE Chat Example

### Example 1: Thai Language Flow

```text
User: news

Bot: 📰 News / ข่าว

Select language:
1 = Thai (ไทย)
2 = English

---

User: 1

Bot: 📰 ข่าวและสภาพอากาศ

🌡️ อุณหภูมิ (Bangkok): 32°C
💨 PM2.5 (Bangkok): 45
🌧️ จะฝนตกใน 5 ชั่วโมงข้างหน้า: ไม่ (No)

🍃 กัญชา: ถูกกฎหมาย (Legal)
🚭 บุหรี่ไฟฟ้า: *ผิดกฎหมาย* (NOT LEGAL)
🍺 แอลกอฮอล์: ควรระวัง (Prescriptive)

📰 ข่าวสำคัญวันนี้:
1 - รัฐบาลประกาศมาตรการใหม่เพื่อลดมลพิษ...
2 - กรุงเทพฯ เตรียมพร้อมรับมือฤดูฝน...
3 - ตลาดหุ้นไทยปิดบวก 15 จุด...
4 - ท่องเที่ยวไทยคาดนักท่องเที่ยวพุ่ง...
5 - การศึกษาไทยเตรียมปรับหลักสูตร...

💡 กด 1-5 เพื่ออ่านข่าวเพิ่มเติม
💡 กด 9 เพื่อดูแหล่งข้อมูล

---

User: 1

Bot: 📰 รัฐบาลประกาศมาตรการใหม่เพื่อลดมลพิษในกรุงเทพมหานคร

🔗 อ่านเพิ่มเติม: https://news.thaipbs.or.th/...

กดข้อความใดก็ได้เพื่อกลับไปเมนู

---

User: ok

Bot: (Returns to main menu with weather/news)

---

User: 9

Bot: 📚 แหล่งข้อมูล / Resources:

🌡️ สภาพอากาศ: Open-Meteo
https://open-meteo.com

📰 ข่าว:
• ThaiPBS: https://news.thaipbs.or.th
• Bangkok Post: https://bangkokpost.com
• The Nation: https://nationthailand.com

ขอบคุณที่ใช้บริการ! 🙏

(News session ends)
```

### Example 2: English Language Flow

```text
User: news

Bot: 📰 News / ข่าว

Select language:
1 = Thai (ไทย)
2 = English

---

User: 2

Bot: 📰 News & Weather

🌡️ Temperature (Bangkok): 32°C
💨 PM2.5 (Bangkok): 45
🌧️ Will it rain in next 5 hours: No

🍃 Cannabis: Legal
🚭 E-Cigarettes: *NOT LEGAL*
🍺 Alcohol: Prescriptive

📰 Top 5 Headlines Today:
1 - Government announces new pollution control measures...
2 - Bangkok prepares for rainy season...
3 - Thai stock market closes up 15 points...
4 - Tourism industry expects surge in visitors...
5 - Education ministry plans curriculum reform...

💡 Press 1-5 to read more
💡 Press 9 for resources

---

User: 3

Bot: 📰 Thai stock market closes up 15 points amid positive investor sentiment

🔗 Read more: https://www.bangkokpost.com/business/...

Send any message to return to menu

---

User: back

Bot: (Returns to main menu)

---

User: 9

Bot: 📚 Resources:

🌡️ Weather: Open-Meteo
https://open-meteo.com

📰 News:
• ThaiPBS: https://news.thaipbs.or.th/en
• Bangkok Post: https://bangkokpost.com
• The Nation: https://nationthailand.com

Thank you for using TeacherBOY! 🙏

(News session ends)
```

## Edge Cases

### Session Timeout

```text
User: news
Bot: (Language selection)
... (5 minutes pass with no response)

User: 1
Bot: 📰 News / ข่าว

Select language:
1 = Thai (ไทย)
2 = English

(Session expired, restarts from beginning)
```

### Invalid Input

```text
User: news
Bot: (Language selection)

User: abc
Bot: ❌ Please select a valid option (1-5 or 9)

(Stays in language selection step)
```

### Thai Numerals

```text
User: news
Bot: (Language selection)

User: ๑
Bot: (Accepts Thai numeral ๑ as 1, proceeds in Thai)
```

### No NewsAPI Key Configured

```text
User: news
Bot: (Language selection)

User: 2
Bot: 📰 News & Weather

🌡️ Temperature (Bangkok): 32°C
💨 PM2.5 (Bangkok): 45
🌧️ Will it rain in next 5 hours: No

🍃 Cannabis: Legal
🚭 E-Cigarettes: *NOT LEGAL*
🍺 Alcohol: Prescriptive

📰 Top 5 Headlines Today:
1 - News unavailable - Please set NEWS_API_KEY
2 - Visit ThaiPBS for news
3 - Or Bangkok Post
4 - Or The Nation
5 - Press 9 for resources

💡 Press 1-5 to read more
💡 Press 9 for resources

(Still functional, shows placeholder headlines with resource links)
```

## Concurrent Usage

### Translation + News (Different Chats)

```text
Chat A (User 1): สวัสดี
Bot: Hello

Chat B (User 2): news
Bot: (News language selection)

Chat A (User 1): ฉันชื่อจอห์น
Bot: My name is John

Chat B (User 2): 1
Bot: (Thai news menu)

(Both agents work independently, no conflicts)
```

### Translation Priority Over News

```text
User: news
Bot: (Language selection)

User: ฉันต้องการข้อมูลข่าว
Bot: I need news information

(Thai text detected, translation agent takes over with priority 10)
(News session interrupted, user must type "news" again to restart)
```

## Group Chat Usage

```text
[LINE Group: Bangkok Expats]

User A: news
Bot: (Language selection)

User B: What's the weather?
(Ignored - not in news flow, not Thai text)

User A: 2
Bot: (English news menu to whole group)

User C: 1
Bot: (Shows headline 1 to whole group)

User A: 9
Bot: (Shows resources, ends news session)
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
