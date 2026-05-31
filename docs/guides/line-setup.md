# LINE Setup

This guide covers creating a LINE Messaging API channel, getting credentials, and enabling the webhook.

## 1) Create the channel

1. Go to <https://developers.line.biz/console/>
2. Create (or select) a Provider.
3. Create a **Messaging API** channel.

## 2) Get credentials

In the channel’s **Messaging API** tab:

- Channel secret → set as `LINE_CHANNEL_SECRET`
- Channel access token (long-lived) → set as `LINE_CHANNEL_ACCESS_TOKEN`

Keep both as secrets (never commit them).

## 3) Enable webhooks

In the same **Messaging API** tab:

1. Set **Use webhook** = ON.
2. Set Webhook URL to:

   - `https://<your-host>/webhook`

   For Hugging Face Spaces, use the live Space host:

   - `https://<your-space-host>.hf.space/webhook`

   Do not use the Hugging Face page URL:

   - `https://huggingface.co/spaces/<owner>/<space>`

3. Click **Verify** and confirm success.

## 4) Disable competing responders (recommended)

In LINE Official Account Manager:

- Turn OFF auto-reply messages
- Turn OFF greeting messages

This avoids conflicts where LINE responds instead of your bot.

## 5) Add the bot

- Use the QR code (Messaging API tab) to add the bot as a friend.

## Troubleshooting

- Invalid signature: your `LINE_CHANNEL_SECRET` is wrong, or the request is being modified by a proxy.
- Verify fails: your URL isn’t reachable publicly over HTTPS, or your app isn’t running.
- Verify returns `404 Not Found`: you are likely using the Hugging Face page URL instead of the `hf.space` app host.
