# LINE Bot Token Setup Guide

This guide will help you set up your LINE Bot and obtain the necessary tokens for TeacherBOY translation bot.

## Prerequisites

- A LINE account
- A smartphone with LINE app installed

## Step-by-Step Setup

### 1. Create a LINE Developers Account

1. Go to [LINE Developers Console](https://developers.line.biz/console/)
2. Log in with your LINE account
3. If this is your first time, agree to the terms of service

### 2. Create a Provider

1. Click on "Create a new provider"
2. Enter a provider name (e.g., "TeacherBOY")
3. Click "Create"

### 3. Create a Messaging API Channel

1. In your provider page, click "Create a new channel"
2. Select "Messaging API"
3. Fill in the required information:
   - **Channel name**: TeacherBOY Translation Bot
   - **Channel description**: Automatic Thai/English translation bot
   - **Category**: Education or Communication
   - **Subcategory**: Choose appropriate subcategory
   - **Email address**: Your email address
4. Review and agree to the terms
5. Click "Create"

### 4. Configure Your Channel

1. In the channel settings, go to the "Messaging API" tab
2. **Channel Secret**:
   - Find "Channel secret" at the top
   - Click "Show" to reveal it
   - Copy this value - you'll need it as `LINE_CHANNEL_SECRET`

3. **Channel Access Token**:
   - Scroll down to "Channel access token (long-lived)"
   - Click "Issue"
   - Copy the generated token - you'll need it as `LINE_CHANNEL_ACCESS_TOKEN`

4. **Webhook Settings**:
   - Enable "Use webhook"
   - Set webhook URL to: `https://your-domain.com/webhook`
   - Enable "Redelivery"
   - Disable "Auto-reply messages" (optional, recommended)
   - Disable "Greeting messages" (optional, recommended)

### 5. Add Bot as Friend

1. In the "Messaging API" tab, find the QR code
2. Scan the QR code with your LINE app to add the bot as a friend

### 6. Configure Your Application

1. Copy `.env.example` to `.env`:
   ```bash
   cp .env.example .env
   ```

2. Edit `.env` and add your tokens:
   ```
   LINE_CHANNEL_SECRET=your_channel_secret_here
   LINE_CHANNEL_ACCESS_TOKEN=your_channel_access_token_here
   ```

3. Configure LibreTranslate API (optional):
   - Default: Uses public LibreTranslate.de instance
   - For better performance, set up your own LibreTranslate instance
   - Or use a paid API key from a LibreTranslate provider

### 7. Deploy Your Bot

#### Using Docker Compose (Recommended)

```bash
docker-compose up -d
```

#### Using Docker

```bash
docker build -t teacherboy .
docker run -p 8000:8000 --env-file .env teacherboy
```

#### Local Development

```bash
pip install -r requirements.txt
python -m src.main
```

### 8. Set Up Webhook URL

1. Deploy your application to a public server with HTTPS
2. Update the webhook URL in LINE Developers Console
3. Test the webhook using the "Verify" button

**Important**: LINE requires HTTPS for webhook URLs. You can use:
- ngrok for local testing: `ngrok http 8000`
- A cloud provider with SSL (AWS, Google Cloud, Heroku, etc.)

### 9. Test Your Bot

1. Open LINE app
2. Send a message to your bot
3. Try sending:
   - Thai text (will be translated to English)
   - English text (will be translated to Thai)

## Troubleshooting

### Bot Doesn't Respond

- Check webhook URL is correct and accessible
- Verify tokens are correctly set in `.env`
- Check application logs: `docker-compose logs -f`
- Verify webhook is enabled in LINE Developers Console

### Translation Not Working

- Check LibreTranslate API URL is accessible
- Verify API key if using a private instance
- Check application logs for translation errors

### Invalid Signature Error

- Verify `LINE_CHANNEL_SECRET` is correct
- Check that webhook URL matches your deployed URL

## MCP Server Configuration

The bot is configured to work with `line-bot-mcp-server` for Docker MCP integration.

### Setting Up MCP Server

1. Install line-bot-mcp-server Docker image:
   ```bash
   docker pull line-bot-mcp-server
   ```

2. The MCP configuration is located in `mcp/config.json`

3. Environment variables are automatically passed from your `.env` file

## Additional Resources

- [LINE Messaging API Documentation](https://developers.line.biz/en/docs/messaging-api/)
- [LibreTranslate API Documentation](https://libretranslate.com/docs/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/)

## Support

For issues or questions:
- GitHub Issues: https://github.com/TeacherEvan/TeacherBOY/issues
- User: ewaldt91
