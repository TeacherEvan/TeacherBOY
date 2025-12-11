# TeacherBOY - Smart Translation Bot Quick Start

## 🎯 What's New

### Smart Translation Mode

- **Auto-starts** when Thai text is detected
- **Continuous translation** of EVERY message
- **Sleep command**: Say "Thank you TeacherBoy" (sleeps 24 hours)
- **Wake command**: Say "TeacherBoy" alone to wake up
- **Works everywhere**: 1-on-1 chats, groups, rooms
- **Rate limiting**: 10 translations per minute

### Translation Quality

- **Primary**: Google Cloud Translation API (professional grade)
- **Fallback**: LibreTranslate (free, open-source)

## 🚀 Quick Setup

### 1. Get Google API Key (Optional but HIGHLY Recommended)

**Why?** Google Translate is MUCH better quality for Thai-English than LibreTranslate.

```bash
# Go to: https://console.cloud.google.com/
# 1. Create a new project (or select existing)
# 2. Enable "Cloud Translation API"
# 3. Go to "APIs & Services" > "Credentials"
# 4. Click "Create Credentials" > "API Key"
# 5. Copy the API key
```

**Pricing**: 500,000 characters FREE per month, then $20/million

### 2. Update .env

```bash
# Add your Google API key
GOOGLE_TRANSLATE_API_KEY=your_google_api_key_here

# Your LINE credentials (already configured)
LINE_CHANNEL_SECRET=ddbb096582dbf20d25090ec1292f8179
LINE_CHANNEL_ACCESS_TOKEN=076qI6h5UQZOBRahmdB2lqU74HCwAfssP0AI4fsQI0NMun4Aubas07LviJhw1ILDZekx2zaHtracTNtL7d8dMolfOXFqxKCJPF4Z9BfPk1yz+Hk/j4n6AsELF3u/1vQ4UDtIrNtrssiB8aWAUmUQNQdB04t89/1O/w1cDnyilFU=
```

### 3. Deploy

```bash
# Rebuild Docker image
docker rm -f teacherboy
docker build -t teacherboy .
docker run -d --name teacherboy --env-file .env -p 8000:8000 teacherboy

# Start ngrok (for testing)
ngrok http 8000
```

### 4. Configure LINE

1. Copy ngrok URL (e.g., `https://abc123.ngrok.io`)
2. Go to: https://manager.line.biz/account/@788hwhea/setting/messaging-api
3. Set **Webhook URL**: `https://abc123.ngrok.io/webhook`
4. Click **Verify** (must show success)
5. **Disable** auto-reply messages

### 5. Test!

1. Add bot as friend (scan QR code)
2. Send: `สวัสดีครับ` (Hello in Thai)
3. Bot enters translation mode ✅
4. Send any English: Gets translated to Thai ✅
5. Send any Thai: Gets translated to English ✅
6. Say: `Thank you TeacherBoy` → Bot sleeps for 24 hours 😴
7. Say: `TeacherBoy` → Bot wakes up! ☀️

## 🎨 How It Works

```
User sends Thai text → Bot detects Thai characters
                    ↓
          Translation mode ON 🔥
                    ↓
    Every message gets translated
    (Thai → English, English → Thai)
                    ↓
   User says "Thank you TeacherBoy"
                    ↓
        Bot sleeps for 24 hours 😴
                    ↓
   User says "TeacherBoy" (alone)
                    ↓
          Bot wakes up! ☀️
```

## 💡 Tips

### For Best Translation Quality

- Use Google Translate API (see setup above)
- Falls back to LibreTranslate if no API key

### Sleep & Wake Commands

**Sleep commands** (put bot to sleep for 24 hours):

- `Thank you TeacherBoy`
- `thanks TeacherBoy`
- `thx TeacherBoy`
- `ขอบคุณ TeacherBoy` (Thai "thank you")

**Wake command** (wake bot immediately):

- `TeacherBoy` (alone, not part of other text)

### Group Chats

- Bot works in groups automatically
- Translation mode is per-chat (not global)
- Each chat has its own session

### Performance

- First message (Thai detection) starts mode
- Session persists until sleep command
- Bot auto-wakes after 24 hours
- Rate limit: 10 translations per minute

## 📊 Translation API Comparison

| Feature          | Google Translate        | LibreTranslate |
| ---------------- | ----------------------- | -------------- |
| **Quality**      | ⭐⭐⭐⭐⭐ Professional | ⭐⭐⭐ Good    |
| **Thai-English** | Excellent               | Fair           |
| **Free Tier**    | 500K chars/month        | Unlimited      |
| **Pricing**      | $20/million after free  | Free           |
| **Setup**        | API key required        | No setup       |

## 🐛 Troubleshooting

### Bot doesn't translate

- Check if Thai text was sent (translation mode trigger)
- If sleeping, say "TeacherBoy" to wake up
- Check rate limit (10/min)

### Translation quality poor

- Add `GOOGLE_TRANSLATE_API_KEY` to `.env`
- Rebuild Docker container

### Webhook fails

- Make sure ngrok is running
- URL must be HTTPS (ngrok provides this)
- Click "Verify" in LINE console

## 📚 Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** - How everything works
- **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** - Full deployment guide
- **[README.md](README.md)** - Project overview

## 🎉 You're Ready!

Your bot now:

- ✅ Auto-detects Thai and starts translating
- ✅ Translates continuously until stopped
- ✅ Uses professional Google Translate (if configured)
- ✅ Works in groups and 1-on-1
- ✅ Beautiful Flex Message cards
- ✅ Smart sleep/wake commands
- ✅ Rate limiting (10/min)
- ✅ 24-hour sleep mode

Enjoy your smart translation bot! 🚀
