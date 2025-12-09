# TeacherBOY Deployment Guide

Complete guide to deploying your TeacherBOY translation bot to production.

## 📋 Prerequisites

- ✅ LINE Official Account created (@788hwhea)
- ✅ Channel Secret: `ddbb096582dbf20d25090ec1292f8179`
- ✅ Channel Access Token: (configured in `.env`)
- ✅ `.env` file configured
- ✅ Docker installed (or Python 3.11+)

## 🎯 Deployment Options

### Option 1: Local Testing with ngrok (Quickest)

Perfect for testing and development.

#### Step 1: Install ngrok

```bash
# Download from https://ngrok.com/download
# Or on Linux:
wget https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar xvzf ngrok-v3-stable-linux-amd64.tgz
sudo mv ngrok /usr/local/bin/

# Sign up at ngrok.com and get your authtoken
ngrok config add-authtoken YOUR_AUTH_TOKEN
```

#### Step 2: Start Your Bot

```bash
cd /home/eboth/projects/TeacherBOY/TeacherBOY

# Option A: Docker
docker build -t teacherboy .
docker run --env-file .env -p 8000:8000 teacherboy

# Option B: Python directly
pip install -r requirements.txt
uvicorn src.main:app --host 0.0.0.0 --port 8000
```

#### Step 3: Start ngrok

```bash
# In a new terminal
ngrok http 8000

# You'll see output like:
# Forwarding https://abc123def.ngrok.io -> http://localhost:8000
```

#### Step 4: Configure LINE Webhook

1. Copy your ngrok HTTPS URL: `https://abc123def.ngrok.io`
2. Go to: https://manager.line.biz/account/@788hwhea/setting/messaging-api
3. Find **Webhook URL** field
4. Enter: `https://abc123def.ngrok.io/webhook`
5. Click **Update**
6. Click **Verify** → Should show "Success"

#### Step 5: Disable Auto-Reply

1. In the same page, scroll to **LINE Official Account features**
2. Click **Edit** (Response settings link)
3. Turn OFF:
   - Auto-reply messages
   - Greeting messages
4. Turn ON:
   - Use webhooks
5. Save

#### Step 6: Test!

1. Scan QR code in Messaging API page
2. Add bot as friend
3. Send: `สวัสดี` → Get English translation
4. Send: `Hello` → Get Thai translation

**⚠️ ngrok Limitations:**

- Free tier: URL changes when you restart ngrok
- Must update webhook URL in LINE each time
- Good for testing only

---

### Option 2: Heroku (Free/Simple Production)

Heroku provides permanent URLs and easy deployment.

#### Step 1: Install Heroku CLI

```bash
curl https://cli-assets.heroku.com/install.sh | sh
heroku login
```

#### Step 2: Prepare Project

```bash
cd /home/eboth/projects/TeacherBOY/TeacherBOY

# Create Procfile
echo "web: uvicorn src.main:app --host 0.0.0.0 --port \$PORT" > Procfile

# Heroku needs port from environment
# Update src/main.py at the bottom:
# port=int(os.getenv("PORT", 8000))
```

#### Step 3: Create Heroku App

```bash
heroku create teacherboy-translator
# You'll get: https://teacherboy-translator.herokuapp.com
```

#### Step 4: Set Environment Variables

```bash
heroku config:set LINE_CHANNEL_SECRET=ddbb096582dbf20d25090ec1292f8179
heroku config:set LINE_CHANNEL_ACCESS_TOKEN=076qI6h5UQZOBRahmdB2lqU74HCwAfssP0AI4fsQI0NMun4Aubas07LviJhw1ILDZekx2zaHtracTNtL7d8dMolfOXFqxKCJPF4Z9BfPk1yz+Hk/j4n6AsELF3u/1vQ4UDtIrNtrssiB8aWAUmUQNQdB04t89/1O/w1cDnyilFU=
heroku config:set LIBRETRANSLATE_API_URL=https://libretranslate.de/translate
heroku config:set DEBUG=False
```

#### Step 5: Deploy

```bash
git add .
git commit -m "Deploy TeacherBOY to Heroku"
git push heroku copilot/add-line-translation-bot:main
```

#### Step 6: Configure LINE Webhook

1. Your permanent URL: `https://teacherboy-translator.herokuapp.com/webhook`
2. Update in LINE Developers Console
3. Verify webhook
4. Test!

---

### Option 3: VPS (DigitalOcean, Linode, AWS EC2)

Full control, permanent deployment.

#### Step 1: Set Up VPS

```bash
# SSH into your server
ssh user@your-server-ip

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
```

#### Step 2: Clone and Configure

```bash
git clone https://github.com/TeacherEvan/TeacherBOY.git
cd TeacherBOY

# Create .env file
cat > .env << 'EOF'
LINE_CHANNEL_SECRET=ddbb096582dbf20d25090ec1292f8179
LINE_CHANNEL_ACCESS_TOKEN=076qI6h5UQZOBRahmdB2lqU74HCwAfssP0AI4fsQI0NMun4Aubas07LviJhw1ILDZekx2zaHtracTNtL7d8dMolfOXFqxKCJPF4Z9BfPk1yz+Hk/j4n6AsELF3u/1vQ4UDtIrNtrssiB8aWAUmUQNQdB04t89/1O/w1cDnyilFU=
LIBRETRANSLATE_API_URL=https://libretranslate.de/translate
DEBUG=False
EOF
```

#### Step 3: Deploy with Docker

```bash
docker build -t teacherboy .
docker run -d --name teacherboy --env-file .env -p 8000:8000 --restart unless-stopped teacherboy
```

#### Step 4: Set Up Nginx (HTTPS)

```bash
# Install Nginx and Certbot
sudo apt update
sudo apt install nginx certbot python3-certbot-nginx -y

# Configure Nginx
sudo nano /etc/nginx/sites-available/teacherboy

# Add this config:
server {
    listen 80;
    server_name your-domain.com;  # Replace with your domain

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# Enable site
sudo ln -s /etc/nginx/sites-available/teacherboy /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx

# Get SSL certificate (HTTPS)
sudo certbot --nginx -d your-domain.com
```

#### Step 5: Configure LINE Webhook

1. Your URL: `https://your-domain.com/webhook`
2. Update in LINE Developers Console
3. Verify and test

---

### Option 4: Render.com (Easy, Free Tier)

Simple alternative to Heroku.

#### Step 1: Sign Up

- Go to https://render.com
- Sign up (free tier available)

#### Step 2: Create Web Service

1. Click **New +** → **Web Service**
2. Connect your GitHub repo
3. Settings:
   - **Name:** teacherboy
   - **Environment:** Docker
   - **Instance Type:** Free
4. Add environment variables:
   ```
   LINE_CHANNEL_SECRET=ddbb096582dbf20d25090ec1292f8179
   LINE_CHANNEL_ACCESS_TOKEN=076qI6h5UQZOBRahmdB2lqU74HCwAfssP0AI4fsQI0NMun4Aubas07LviJhw1ILDZekx2zaHtracTNtL7d8dMolfOXFqxKCJPF4Z9BfPk1yz+Hk/j4n6AsELF3u/1vQ4UDtIrNtrssiB8aWAUmUQNQdB04t89/1O/w1cDnyilFU=
   LIBRETRANSLATE_API_URL=https://libretranslate.de/translate
   ```
5. Deploy!

Your URL: `https://teacherboy.onrender.com/webhook`

---

## 🔧 Post-Deployment Configuration

### Configure LINE Webhook (All Options)

1. **Go to LINE Developers Console**

   - https://developers.line.biz/console/

2. **Navigate to Your Channel**

   - Click provider (TeacherEvan)
   - Click channel (Brown @788hwhea)
   - Click **Messaging API** tab

3. **Set Webhook URL**

   - Find **Webhook settings** section
   - Click **Edit**
   - Enter your URL:
     ```
     ngrok:    https://abc123.ngrok.io/webhook
     Heroku:   https://your-app.herokuapp.com/webhook
     VPS:      https://your-domain.com/webhook
     Render:   https://your-app.onrender.com/webhook
     ```
   - Click **Update**

4. **Verify Webhook**

   - Click **Verify** button
   - Should show: ✅ "Success"
   - If fails, check:
     - Server is running
     - URL is correct
     - Port is accessible
     - HTTPS (required for production)

5. **Enable Webhooks**

   - Toggle **Use webhook** to ON

6. **Disable Auto-Reply**
   - Scroll to **LINE Official Account features**
   - Click **Edit** link (opens Response settings)
   - Set:
     - ❌ Auto-reply messages: OFF
     - ❌ Greeting messages: OFF (optional)
     - ✅ Webhooks: ON
   - Click **Save**

### Test Your Deployment

1. **Health Check**

   ```bash
   curl https://your-url.com/health
   # Should return: {"status":"healthy"}
   ```

2. **Webhook Endpoint**

   ```bash
   curl https://your-url.com/
   # Should return bot info
   ```

3. **Add Bot as Friend**

   - In Messaging API page, find QR code
   - Scan with LINE app
   - Add as friend

4. **Send Test Messages**
   - Thai: `สวัสดีครับ` → Should get English
   - English: `Good morning` → Should get Thai
   - Check for Flex Message cards with flags

---

## 📊 Monitoring & Logs

### Docker Logs

```bash
# View real-time logs
docker logs -f teacherboy

# View last 100 lines
docker logs --tail 100 teacherboy
```

### Heroku Logs

```bash
heroku logs --tail
```

### VPS Logs

```bash
# Docker container logs
docker logs -f teacherboy

# Nginx logs
sudo tail -f /var/log/nginx/access.log
sudo tail -f /var/log/nginx/error.log
```

---

## 🐛 Troubleshooting

### Bot Doesn't Respond

**Check 1: Server Running?**

```bash
curl https://your-url.com/health
# Should return: {"status":"healthy"}
```

**Check 2: Webhook Verified?**

- LINE Console → Messaging API → Verify button
- Should be green/success

**Check 3: Auto-Reply Disabled?**

- Response settings → Auto-reply OFF

**Check 4: Logs**

```bash
docker logs teacherboy
# Look for errors
```

### Webhook Verification Fails

**Issue:** "Failed to verify webhook"

**Solutions:**

1. Make sure server is running
2. Check URL is correct (include `/webhook`)
3. Use HTTPS (not HTTP) for production
4. Check firewall allows incoming connections
5. For ngrok: Make sure tunnel is active

### Translation Doesn't Work

**Issue:** Bot responds but translation fails

**Solutions:**

1. Check LibreTranslate API:
   ```bash
   curl -X POST https://libretranslate.de/translate \
     -H "Content-Type: application/json" \
     -d '{"q":"Hello","source":"en","target":"th","format":"text"}'
   ```
2. Check logs for API errors
3. Try different LibreTranslate instance in `.env`

### Port Issues (VPS)

**Issue:** Can't connect to server

**Solutions:**

```bash
# Check if port 8000 is accessible
sudo netstat -tulpn | grep 8000

# Open firewall (Ubuntu/Debian)
sudo ufw allow 8000
sudo ufw allow 80
sudo ufw allow 443

# For nginx, only need 80/443
```

---

## 🔐 Security Best Practices

1. **Never commit `.env` file**

   ```bash
   # Already in .gitignore
   git rm --cached .env  # If accidentally added
   ```

2. **Use HTTPS in production**

   - Ngrok: Automatic
   - Heroku: Automatic
   - VPS: Use Let's Encrypt (certbot)

3. **Rotate tokens periodically**

   - LINE Console → Issue new token
   - Update `.env` and redeploy

4. **Monitor logs for suspicious activity**
   ```bash
   docker logs teacherboy | grep "Invalid signature"
   ```

---

## 🚀 Scaling & Performance

### If Bot Gets Popular

1. **Use Docker Compose**

   ```bash
   docker-compose up -d --scale web=3
   # Runs 3 instances
   ```

2. **Add Redis for rate limiting**

   ```python
   # Prevent spam/abuse
   ```

3. **Self-host LibreTranslate**

   ```bash
   docker run -d -p 5000:5000 libretranslate/libretranslate
   # Update .env: LIBRETRANSLATE_API_URL=http://localhost:5000/translate
   ```

4. **Use load balancer**
   - nginx upstream for multiple instances
   - Cloud load balancers (AWS ELB, etc.)

---

## 📚 Additional Resources

- **LINE Messaging API Docs:** https://developers.line.biz/en/docs/messaging-api/
- **LibreTranslate:** https://github.com/LibreTranslate/LibreTranslate
- **FastAPI Docs:** https://fastapi.tiangolo.com/
- **ngrok Docs:** https://ngrok.com/docs

---

## ✅ Deployment Checklist

- [ ] Bot code running locally
- [ ] `.env` file configured with tokens
- [ ] Deployment method chosen (ngrok/Heroku/VPS/Render)
- [ ] Server deployed and accessible
- [ ] Health check endpoint works
- [ ] Webhook URL configured in LINE
- [ ] Webhook verified (green checkmark)
- [ ] Auto-reply disabled
- [ ] Webhooks enabled
- [ ] Bot added as friend
- [ ] Test message sent (Thai)
- [ ] Test message sent (English)
- [ ] Logs monitored for errors
- [ ] HTTPS enabled (production)
- [ ] Tokens secured (not in git)

---

**Need help?** Check logs first, then refer to troubleshooting section above!
