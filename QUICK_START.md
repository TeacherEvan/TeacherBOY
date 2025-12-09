# TeacherBOY - Smart Translation Bot Quick Start

## 🎯 What's New

### Smart Translation Mode

- **Auto-starts** when Thai text is detected
- **Continuous translation** of EVERY message
- **Exit command**: Say "thanks Brown" or "ขอบคุณ Brown"
- **Works everywhere**: 1-on-1 chats, groups, rooms

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
6. Say: `thanks Brown` → Bot exits translation mode ✅

## 🎨 How It Works

```
User sends Thai text → Bot detects Thai characters
                    ↓
          Translation mode ON 🔥
                    ↓
    Every message gets translated
    (Thai → English, English → Thai)
                    ↓
   User says "thanks Brown" or "ขอบคุณ Brown"
                    ↓
    Bot replies "ลาก่อน 👋 (Goodbye!)"
                    ↓
          Translation mode OFF
```

## 💡 Tips

### For Best Translation Quality

- Use Google Translate API (see setup above)
- Falls back to LibreTranslate if no API key

### Exit Commands

All of these work:

- `thanks Brown`
- `thank you Brown`
- `thx Brown`
- `ขอบคุณ Brown` (Thai "thank you")

### Group Chats

- Bot works in groups automatically
- Translation mode is per-chat (not global)
- Each chat has its own session

### Performance

- First message (Thai detection) starts mode
- Session persists until "thanks Brown"
- Old sessions auto-cleanup after 24h

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
- Or say "thanks Brown" then send Thai again

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
- ✅ Smart exit command

Enjoy your smart translation bot! 🚀
