# Admin Commands - Quick Start

This is a 5-minute quick start guide to get admin commands working.

## Step 1: Get Your LINE User ID (2 minutes)

1. Add your bot on LINE
2. Send any message to the bot (e.g., "test")
3. Check your server logs (Docker or terminal)
4. Look for a line like:

   ```text
   👤 User ID: U1234567890abcdef
   ```

5. Copy this user ID

## Step 2: Configure Admin Access (1 minute)

Add your user ID to `.env`:

```bash
# Single admin
ADMIN_USER_IDS=U1234567890abcdef

# Or multiple admins (comma-separated)
ADMIN_USER_IDS=U1234567890abcdef,U9876543210fedcba
```

## Step 3: Restart Bot (1 minute)

```bash
# Docker
docker-compose restart

# Direct Python
# Press Ctrl+C and run again:
uvicorn src.main:app --reload
```

Look for this in the logs:

```text
✅ AdminAgent initialized with 1 authorized admin(s)
🔧 Admin Agent registered with 1 authorized admin(s)
```

## Step 4: Test Commands (1 minute)

Send these messages to your bot on LINE:

```text
/admin help
```

You should see the admin commands menu! 🎉

Try other commands:

```text
/admin dashboard
/admin status
/admin sessions
```

The dashboard is DM-first:

- In a private chat, it replies with a Flex panel.
- In a group or room, it pushes the panel to your DM and only posts a neutral handoff message in the group.
- The panel includes direct buttons for status, sleep or wake, confirmations, and sessions.
- Reset, purge, and leave stay preview-only from the panel and still require private confirmation.

Sensitive commands use a private-preview flow. Start from a chat where you want
the action to apply, or pass an explicit chat ID:

```text
/admin reset
/admin purge
/admin leave
```

If you requested the action in a private chat with Ms. Green, the reply is:

```text
✅ Private preview sent. Review it in this chat and confirm when ready.
```

If you requested it from a group or room, the public reply stays neutral:

```text
✅ Private preview sent. Review it in your private chat to continue.
```

The private preview includes the token plus the exact commands to finish or
abort the action:

```text
/admin confirm <token>
/admin cancel <token>
```

## Common Commands

```bash
# Check bot status for current chat
/admin status

# Open the DM-first admin dashboard
/admin dashboard

# View all active sessions
/admin sessions

# Review your pending destructive previews
/admin confirmations  # private chat only

# Put bot to sleep for 12 hours
/admin sleep 12

# Wake the bot
/admin wake

# Request destructive actions; review the private preview before acting
/admin reset
/admin purge
/admin leave

# Complete or abort the pending action from a private chat with Ms. Green
/admin confirm <token>
/admin cancel <token>

# Get help anytime
/admin help
```

## Troubleshooting

**Not seeing any response?**

1. Check your user ID matches exactly: `/admin status` in logs
2. Restart the bot after changing `.env`
3. Make sure `ADMIN_USER_IDS` has no spaces around the comma
4. Check bot logs for errors: `docker logs teacherboy-app-1`

**Still not working?**

- Your LINE user ID format should be: `U` followed by 15-17 alphanumeric characters
- Check spelling: `ADMIN_USER_IDS` (plural with S)
- Verify `.env` file is in the correct location

## What's Next?

- Read the [full documentation](ADMIN_COMMANDS.md) for all features
- Learn about [chat ID formats and remote management](ADMIN_COMMANDS.md#chat-id-format)
- Explore [common use cases](ADMIN_COMMANDS.md#common-use-cases)

## Security Note

🔒 Only users in `ADMIN_USER_IDS` can execute admin commands.
Unauthorized users will see no response (silent failure for security).

---

**Need help?** Check the [full Admin Commands documentation](ADMIN_COMMANDS.md) or open an issue on GitHub.
