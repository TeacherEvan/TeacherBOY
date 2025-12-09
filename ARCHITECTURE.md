# TeacherBOY Architecture & How It Works

## 🎯 What TeacherBOY Does

TeacherBOY is an **automatic translation bot** for LINE that translates messages between Thai and English. When users send a message in Thai, the bot replies with English. When they send English, the bot replies with Thai.

## 🔄 How the Translation Flow Works

```
User sends message in LINE
        ↓
LINE Platform receives message
        ↓
LINE sends webhook POST to your server → https://your-server.com/webhook
        ↓
TeacherBOY FastAPI receives webhook
        ↓
Validates LINE signature (security)
        ↓
Detects language (Thai or English)
        ↓
Sends text to LibreTranslate API
        ↓
Receives translation
        ↓
Creates beautiful Flex Message card
        ↓
Sends reply back to LINE Platform
        ↓
LINE delivers translated message to user
```

## 🏗️ Architecture Components

### 1. **Your Server (FastAPI App)**

- **What it does:** Receives webhooks from LINE, processes messages, sends replies
- **Location:** Your computer (local), cloud server, or container
- **Port:** 8000 (default)
- **Endpoint:** `/webhook` - This is where LINE sends messages

### 2. **LINE Platform (LINE Servers)**

- **What it does:** Manages all LINE messaging, stores messages, handles delivery
- **Your role:** Register your bot, configure webhook URL
- **Connection:** LINE sends HTTP POST requests to your webhook URL

### 3. **LibreTranslate API**

- **What it does:** Performs the actual translation (Thai ↔ English)
- **Default:** Uses public instance at https://libretranslate.de
- **Alternative:** Can self-host for better privacy/performance

### 4. **Your Bot's Brain (Python Code)**

```
src/
├── main.py                    # FastAPI app (receives webhooks)
├── config.py                  # Loads .env configuration
├── handlers/
│   └── message_handler.py     # Processes messages, coordinates translation
├── services/
│   └── translation_service.py # Detects language & calls LibreTranslate
└── utils/
    └── flex.py                # Creates beautiful message cards
```

## 🌐 What is a Webhook?

A **webhook** is a URL on YOUR server that LINE calls when events happen.

### Without a Webhook:

❌ Your bot can't receive messages  
❌ LINE doesn't know where to send events  
❌ No real-time interaction

### With a Webhook:

✅ LINE sends a POST request to `https://your-domain.com/webhook`  
✅ Your bot receives the message instantly  
✅ Your bot processes and replies

**Think of it as:** Your phone number in the messaging world. LINE needs to know where to "call" when someone messages your bot.

## 🚀 How to Get a Webhook URL

### Option 1: **ngrok (Testing/Development)**

Ngrok creates a temporary public URL that tunnels to your local computer.

```bash
# Install ngrok (if not installed)
# Download from https://ngrok.com/download

# Run your bot locally
uvicorn src.main:app --host 0.0.0.0 --port 8000

# In another terminal, start ngrok
ngrok http 8000

# You'll get a URL like:
# https://abc123.ngrok.io
```

**Your webhook URL becomes:** `https://abc123.ngrok.io/webhook`

⚠️ **Note:** ngrok URLs change every time you restart (free tier). Good for testing only.

### Option 2: **Cloud Deployment (Production)**

Deploy to a cloud provider with a permanent URL:

- **Heroku:** `https://yourapp.herokuapp.com/webhook`
- **AWS/Google Cloud/Azure:** `https://your-domain.com/webhook`
- **DigitalOcean/Linode:** `http://your-ip:8000/webhook` (use reverse proxy)
- **Render/Railway:** `https://yourapp.onrender.com/webhook`

### Option 3: **Docker on VPS**

```bash
# On your server
docker run --env-file .env -p 8000:8000 -d teacherboy

# Your webhook URL
https://your-server-ip-or-domain.com/webhook
```

## 🔧 Complete Setup Guide

### Step 1: Get Your Bot Running

```bash
# Clone and navigate to project
cd /home/eboth/projects/TeacherBOY/TeacherBOY

# Your .env is already configured with:
# LINE_CHANNEL_SECRET=ddbb096582dbf20d25090ec1292f8179
# LINE_CHANNEL_ACCESS_TOKEN=076qI6h5UQZOBRahmdB2lqU74HCwAfssP0AI4fsQI0NMun4Aubas07LviJhw1ILDZekx2zaHtracTNtL7d8dMolfOXFqxKCJPF4Z9BfPk1yz+Hk/j4n6AsELF3u/1vQ4UDtIrNtrssiB8aWAUmUQNQdB04t89/1O/w1cDnyilFU=

# Run with Docker
docker build -t teacherboy .
docker run --env-file .env -p 8000:8000 teacherboy

# OR run locally
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

### Step 2: Expose Your Server (Choose One)

#### Option A: Using ngrok (Testing)

```bash
# In a new terminal
ngrok http 8000

# Copy the HTTPS URL (e.g., https://abc123.ngrok.io)
```

#### Option B: Using a VPS

```bash
# Make sure your server is publicly accessible
# Your webhook URL: http://your-server-ip:8000/webhook
# Better: Use nginx reverse proxy for HTTPS
```

### Step 3: Configure LINE Webhook

1. **Go to LINE Developers Console:** https://developers.line.biz/console/
2. **Click your provider** (e.g., TeacherEvan)
3. **Click your channel** (Brown @788hwhea)
4. **Click "Messaging API" tab**
5. **Find "Webhook URL" section**
6. **Enter your URL:**
   ```
   https://your-ngrok-url.ngrok.io/webhook
   OR
   https://your-domain.com/webhook
   ```
7. **Click "Update"**
8. **Click "Verify"** - Should show "Success"

### Step 4: Configure Bot Behavior

Still in the Messaging API page:

1. **Scroll down to "LINE Official Account features"**
2. **Click "Edit" next to "Response settings"**
3. **Settings to change:**
   - ✅ **Use webhooks:** ON
   - ❌ **Auto-reply messages:** OFF (let your bot handle all messages)
   - ❌ **Greeting messages:** OFF (optional)
4. **Click "Save"**

### Step 5: Test Your Bot

1. **In Messaging API page, find QR code**
2. **Scan with LINE app on your phone**
3. **Add bot as friend**
4. **Send a message:**
   - Send: `สวัสดี` (Thai for "Hello")
   - Bot replies: English translation in a beautiful card
   - Send: `Good morning`
   - Bot replies: Thai translation `สวัสดีตอนเช้า`

## 🎨 What Gets Created (Features Implemented)

### 1. **Automatic Language Detection**

```python
# src/services/translation_service.py
async def detect_language(text: str) -> Optional[str]:
    # Detects if message is Thai ('th') or English ('en')
    # Uses langdetect library for accuracy
```

### 2. **Translation Service**

```python
# Sends text to LibreTranslate API
async def translate(text, source_lang, target_lang) -> str:
    # Thai → English or English → Thai
    # Returns translated text
```

### 3. **Beautiful Message Cards**

```python
# src/utils/flex.py
def create_translation_flex(...) -> dict:
    # Creates LINE Flex Message with:
    # - Original text with flag (🇹🇭 or 🇬🇧)
    # - Translated text with flag
    # - "Powered by LibreTranslate" footer
```

### 4. **Group Chat Support** (New!)

```python
# src/handlers/message_handler.py
# - handle_join_event: Welcome message when bot joins group
# - handle_leave_event: Cleanup when bot is removed
# - handle_member_joined_event: Welcome new members
# - handle_member_left_event: Log member departures
```

### 5. **FastAPI Webhook Endpoint**

```python
# src/main.py
@app.post("/webhook")
async def webhook(request: Request):
    # 1. Validates LINE signature (security)
    # 2. Parses events
    # 3. Routes to appropriate handler
    # 4. Returns OK to LINE
```

## 🔐 Security Features

1. **Signature Validation:** Every webhook is verified using your channel secret
2. **Environment Variables:** Sensitive data never hardcoded
3. **HTTPS Required:** LINE requires secure webhooks in production
4. **No Data Storage:** Stateless - doesn't store messages

## 📊 Data Flow Example

```
User: "สวัสดีครับ" (Hello in Thai)
                ↓
        LINE Platform
                ↓
POST /webhook {
  "events": [{
    "type": "message",
    "message": {"text": "สวัสดีครับ"},
    "replyToken": "abc123..."
  }]
}
                ↓
      TeacherBOY (Your Server)
                ↓
    detect_language("สวัสดีครับ") → 'th'
                ↓
    translate("สวัสดีครับ", 'th', 'en') → "Hello"
                ↓
    create_translation_flex(...) → Flex Message JSON
                ↓
    reply_message(replyToken, flexMessage)
                ↓
        LINE Platform
                ↓
User sees: Beautiful card with original Thai and English translation
```

## 🐛 Troubleshooting

### Bot doesn't respond

- ✅ Check webhook URL is correct
- ✅ Verify webhook with LINE console
- ✅ Check your server is running (`curl http://localhost:8000/health`)
- ✅ View logs: `docker logs container-name`
- ✅ Ensure auto-reply is disabled

### Translation fails

- ✅ Check LibreTranslate API is reachable
- ✅ Try different API URL in .env
- ✅ Check logs for API errors

### Webhook verification fails

- ✅ Make sure URL is publicly accessible
- ✅ Use HTTPS (ngrok provides this automatically)
- ✅ Check firewall settings

## 🚀 Next Steps

1. **Deploy to production** (Heroku, AWS, etc.)
2. **Get a permanent domain** (yourbot.com)
3. **Set up HTTPS** (Let's Encrypt)
4. **Monitor logs** (Docker logs, cloud logging)
5. **Scale** (Add load balancer, multiple instances)

## 📚 Related Documentation

- `docs/LINE_SETUP.md` - Detailed LINE configuration
- `DEPLOYMENT_GUIDE.md` - Production deployment steps
- `README.md` - Quick start guide
- `.env.example` - Configuration template
