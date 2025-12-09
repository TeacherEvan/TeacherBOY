# 🚀 Next Steps - Getting TeacherBOY Multi-Agent System Live

## Current Status ✅

Your multi-agent architecture is now complete:

- ✅ Base agent system implemented
- ✅ Agent router with priority system
- ✅ Translation agent refactored and enhanced
- ✅ New agent token stored in `.env`
- ✅ Configuration system updated
- ✅ All documentation created

## Immediate Next Steps

### 1. Rebuild Docker Image (2 minutes)

The code has changed, so rebuild the container:

```bash
cd /home/eboth/projects/TeacherBOY/TeacherBOY

# Remove old container and rebuild
docker rm -f teacherboy
docker build -t teacherboy .

# Run new container
docker run -d --name teacherboy --env-file .env -p 8000:8000 teacherboy
```

### 2. Verify Startup (30 seconds)

Check logs to see agent registration:

```bash
docker logs teacherboy
```

**Expected output:**

```
🚀 Starting up TeacherBOY Multi-Agent System...
✅ Google Cloud Translation API configured (primary)
✅ LibreTranslate configured (fallback)
📋 Registering agents...
✅ Initialized TranslationAgent: Thai/English translation with continuous session mode
✅ Registered agent: TranslationAgent (priority: 10)
✅ Registered 1 agent(s):
   - TranslationAgent: Thai/English translation with continuous session mode (priority: 10)
```

### 3. Start ngrok (if not running)

```bash
ngrok http 8000
```

Copy the HTTPS URL (e.g., `https://abc123.ngrok.io`)

### 4. Update LINE Webhook (if changed)

1. Go to: https://manager.line.biz/account/@788hwhea/setting/messaging-api
2. Set Webhook URL: `https://your-ngrok-url.ngrok.io/webhook`
3. Click **Verify** (must show "Success")

### 5. Test Multi-Agent System

**Test Translation Agent:**

1. Open LINE and find Brown (@788hwhea)
2. Send: `สวัสดีครับ`
   - ✅ Should start translation mode
   - ✅ Should see "Translation mode ON 🔥" in logs
3. Send: `Hello, how are you?`
   - ✅ Should translate to Thai
4. Send: `ขอบคุณมากครับ`
   - ✅ Should translate to English
5. Say: `thanks Brown`
   - ✅ Should end session with goodbye message

**Check Logs:**

```bash
docker logs -f teacherboy
```

Look for:

```
🔍 Routing message: 'สวัสดีครับ...'
✅ Agent TranslationAgent will handle this message
🔥 Translation session started for chat user_...
✅ Message handled successfully by TranslationAgent
```

## Optional Enhancements

### Option A: Add Google Translate API (Recommended)

**Why?** Much better translation quality for Thai-English

1. Get API key: https://console.cloud.google.com/apis/credentials
2. Enable Cloud Translation API
3. Add to `.env`:
   ```bash
   GOOGLE_TRANSLATE_API_KEY=your_key_here
   ```
4. Rebuild: `docker build -t teacherboy .`
5. Restart: `docker rm -f teacherboy && docker run -d --name teacherboy --env-file .env -p 8000:8000 teacherboy`

**Free tier:** 500,000 characters/month!

### Option B: Configure Second Agent (Optional)

If you want to activate the new agent token provided:

1. Create LINE Official Account for second agent
2. Get channel secret for that account
3. Update `.env`:
   ```bash
   ADDITIONAL_AGENTS={"secondary_agent": {"channel_secret": "your_secret", "channel_access_token": "3WMARuNsH714Po8W2nT94wOEq7hJs27x5yRm5VlVFOBzTaxa9jF2K+18xIR1nOMRz85feISDckX/wgNGuuHIv6pvBEegLEWnQAsDyzcOTomrYaALTIPQ0WNUJJ9T2cg6/PGknQAgeFrPvbXg57uulgdB04t89/1O/w1cDnyilFU="}}
   ```
4. Rebuild and restart

**Note:** Currently, the additional agents system is scaffolded but not fully implemented. You'd need to extend the codebase to support multiple webhooks or different routing logic.

## Building Your First Custom Agent

Want to add a Math Solver Agent? Here's how:

### Step 1: Create Agent File

```bash
touch src/agents/math_agent.py
```

### Step 2: Implement Agent

```python
# src/agents/math_agent.py
from .base_agent import BaseAgent
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi, ReplyMessageRequest, TextMessage
import re
import logging

logger = logging.getLogger(__name__)

class MathAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MathAgent",
            description="Solves basic math equations"
        )

    def get_priority(self) -> int:
        return 20  # Lower priority than translation

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        # Trigger on: "solve X", "calculate X", or "X + Y"
        keywords = ['solve', 'calculate', '=']
        has_keyword = any(kw in text.lower() for kw in keywords)
        has_equation = bool(re.search(r'\d+\s*[\+\-\*/]\s*\d+', text))
        return has_keyword or has_equation

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        try:
            # Extract and solve equation
            match = re.search(r'(\d+)\s*([\+\-\*/])\s*(\d+)', text)
            if match:
                a, op, b = match.groups()
                a, b = int(a), int(b)

                if op == '+': result = a + b
                elif op == '-': result = a - b
                elif op == '*': result = a * b
                elif op == '/': result = a / b if b != 0 else "Error: Division by zero"

                reply = f"🔢 {a} {op} {b} = {result}"
            else:
                reply = "I can solve equations like '5 + 3' or 'solve 10 * 4'"

            line_bot_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[TextMessage(text=reply)]
                )
            )
            logger.info(f"✅ Math equation solved: {text}")
            return True

        except Exception as e:
            logger.error(f"❌ Math agent error: {e}")
            return False
```

### Step 3: Register Agent

```python
# In src/main.py, inside lifespan() function, after TranslationAgent:

from src.agents.math_agent import MathAgent

# ... existing code ...

translation_agent = TranslationAgent()
agent_router.register_agent(translation_agent)

# Add this:
math_agent = MathAgent()
agent_router.register_agent(math_agent)
```

### Step 4: Test

```bash
# Rebuild
docker build -t teacherboy .
docker rm -f teacherboy
docker run -d --name teacherboy --env-file .env -p 8000:8000 teacherboy

# Test
# Send to Brown: "solve 5 + 3"
# Expected: "🔢 5 + 3 = 8"
```

## Production Deployment

Ready for production? Choose a hosting option:

### Option 1: Heroku (Easiest)

```bash
# Install Heroku CLI
curl https://cli-assets.heroku.com/install.sh | sh

# Create app
heroku create teacherboy-production

# Set environment variables
heroku config:set LINE_CHANNEL_SECRET=your_secret
heroku config:set LINE_CHANNEL_ACCESS_TOKEN=your_token
heroku config:set GOOGLE_TRANSLATE_API_KEY=your_google_key

# Deploy
git push heroku copilot/add-line-translation-bot:main

# Get URL
heroku info
```

See **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)** for complete instructions.

### Option 2: DigitalOcean/AWS VPS

1. Create Ubuntu 22.04 droplet
2. Install Docker
3. Clone repo and build
4. Use systemd to keep running
5. Setup nginx reverse proxy
6. Get SSL certificate with Let's Encrypt

Full guide: **[DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)**

### Option 3: Render.com (Free Tier)

1. Connect GitHub repo
2. Select Docker deployment
3. Set environment variables
4. Deploy!

## Monitoring & Maintenance

### Check Health

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy"}
```

### View Logs

```bash
# Follow logs
docker logs -f teacherboy

# Last 100 lines
docker logs --tail 100 teacherboy

# Search logs
docker logs teacherboy | grep "Translation session"
```

### Restart Bot

```bash
docker restart teacherboy
```

### Update Bot

```bash
cd /home/eboth/projects/TeacherBOY/TeacherBOY
git pull
docker build -t teacherboy .
docker rm -f teacherboy
docker run -d --name teacherboy --env-file .env -p 8000:8000 teacherboy
```

## Troubleshooting

### Bot Not Responding

1. Check Docker is running: `docker ps`
2. Check logs: `docker logs teacherboy`
3. Verify ngrok is running: `ngrok http 8000`
4. Test webhook: `curl -X POST http://localhost:8000/webhook`

### Translation Not Starting

1. Send Thai text first (Thai Unicode required)
2. Check if session is already active
3. Say "thanks Brown" to reset
4. Check logs for routing decisions

### Agent Not Triggering

1. Check `should_handle()` logic
2. Verify agent is registered (check startup logs)
3. Check priority order (lower = higher priority)
4. Enable DEBUG=True in .env

### Poor Translation Quality

1. Add Google Translate API key to .env
2. Rebuild Docker container
3. Check logs confirm Google API is active

## What's Next?

🎯 **Recommended Priority:**

1. ✅ **Test the system** (30 min)

   - Verify translation works
   - Test session management
   - Check exit commands

2. ⭐ **Add Google Translate API** (15 min)

   - Get free API key
   - Add to .env
   - Rebuild

3. 🚀 **Deploy to Production** (1-2 hours)

   - Choose hosting (Heroku/VPS/Render)
   - Follow deployment guide
   - Update LINE webhook to production URL

4. 🎨 **Build Custom Agent** (1-3 hours)

   - Pick feature (math, quiz, code review)
   - Follow Multi-Agent Guide
   - Test and deploy

5. 📊 **Monitor Usage** (Ongoing)
   - Watch logs for errors
   - Track translation API usage
   - Optimize performance

## Resources

- **Documentation**: See all `.md` files in project root
- **Examples**: Check `src/agents/translation_agent.py`
- **LINE API**: https://developers.line.biz/en/docs/messaging-api/
- **Support**: GitHub Issues or LINE Developer Community

## Questions?

- **"How do I add more agents?"** → See [MULTI_AGENT_GUIDE.md](MULTI_AGENT_GUIDE.md)
- **"How do I deploy?"** → See [DEPLOYMENT_GUIDE.md](DEPLOYMENT_GUIDE.md)
- **"How does it work?"** → See [ARCHITECTURE.md](ARCHITECTURE.md)
- **"Quick setup?"** → See [QUICK_START.md](QUICK_START.md)

---

**Ready to go live? Start with Step 1 above! 🚀**
