# Admin Control Commands Guide

## Overview

The Admin Agent provides powerful in-chat control commands for authorized administrators to manage TeacherBOY's behavior, monitor sessions, and troubleshoot issues without needing access to the server.

## Features

✅ **Authorization System**: Only authorized LINE users can execute admin commands  
✅ **Highest Priority**: Admin commands are processed before all other agents (Priority 5)  
✅ **In-Chat Management**: Control the bot directly from LINE chats  
✅ **Session Monitoring**: View active sessions and sleeping chats  
✅ **Remote Control**: Wake/sleep chats and reset sessions remotely  

## Configuration

### Step 1: Get Your LINE User ID

Your LINE user ID is automatically logged when you send a message to the bot. To find it:

1. Send any message to the bot (e.g., "test")
2. Check the server logs for a line like:
   ```
   User ID: U1234567890abcdef
   ```

### Step 2: Add Admin User IDs

Edit your `.env` file and add the `ADMIN_USER_IDS` variable:

```bash
# Single admin
ADMIN_USER_IDS=U1234567890abcdef

# Multiple admins (comma-separated)
ADMIN_USER_IDS=U1234567890abcdef,U9876543210fedcba,Uaabbccddeeff0011
```

### Step 3: Restart the Bot

```bash
# If using Docker
docker-compose down
docker-compose up -d

# If running directly
# Stop the server (Ctrl+C) and restart
uvicorn src.main:app --reload
```

You should see in the logs:
```
✅ AdminAgent initialized with 2 authorized admin(s)
🔧 Admin Agent registered with 2 authorized admin(s)
```

## Available Commands

All admin commands start with `/admin` or `!admin`. Commands are case-insensitive.

### 📊 Status & Monitoring

#### `/admin status [chat_id]`
Get current status of a chat.

**Examples:**
```
/admin status
/admin status user_U123456
/admin status group_C789012
```

**Output:**
```
📊 Chat Status
━━━━━━━━━━━━━━━━

Chat ID: user_U1234567890abcdef

✅ Status: ACTIVE
👤 User: U1234567890abcdef
📝 Messages: 15
🕐 Started: 2025-12-12 14:30:45
```

#### `/admin sessions`
List all active translation sessions and sleeping chats.

**Example:**
```
/admin sessions
```

**Output:**
```
📊 Active Sessions
━━━━━━━━━━━━━━━━

✅ ACTIVE SESSIONS:

• user_U1234567890abcdef
  👤 User: U1234567890abcdef
  📝 Messages: 15

• group_C789012345
  👤 User: U999888777666
  📝 Messages: 42

😴 SLEEPING CHATS:

• user_U5555555555555555
  ⏰ Wake in: 18h
```

### 😴 Sleep Management

#### `/admin sleep [chat_id] [hours]`
Put a chat to sleep (bot ignores all messages).

**Parameters:**
- `chat_id` (optional): Target chat ID. Defaults to current chat.
- `hours` (optional): Sleep duration in hours (1-168). Default: 24.

**Examples:**
```
/admin sleep                    # Sleep current chat for 24h
/admin sleep 12                # Sleep current chat for 12h
/admin sleep user_U123456 48  # Sleep specific chat for 48h
```

**Output:**
```
😴 Chat user_U1234567890abcdef is now sleeping for 12 hour(s).

Use '/admin wake' to wake early.
```

#### `/admin wake [chat_id]`
Wake a sleeping chat (bot starts responding again).

**Parameters:**
- `chat_id` (optional): Target chat ID. Defaults to current chat.

**Examples:**
```
/admin wake
/admin wake user_U123456
```

**Output:**
```
☀️ Chat user_U1234567890abcdef has been woken up!

The bot is now ready to translate.
```

### 🔄 Session Control

#### `/admin reset [chat_id]`
Reset a chat to fresh state (ends session, clears history, wakes if sleeping).

**Parameters:**
- `chat_id` (optional): Target chat ID. Defaults to current chat.

**Examples:**
```
/admin reset
/admin reset group_C789012
```

**Output:**
```
🔄 Chat Reset Complete
━━━━━━━━━━━━━━━━

Chat ID: user_U1234567890abcdef

✅ Session: Ended
⏸️ Sleep: Was awake
🧹 History: Cleared

The chat is now in fresh state!
```

### 💡 Help

#### `/admin` or `/admin help`
Show help message with all available commands.

**Example:**
```
/admin
/admin help
```

**Output:**
```
🔧 Admin Commands
━━━━━━━━━━━━━━━━

📊 Status & Info:
  /admin status [chat_id]
    → Show current chat status

  /admin sessions
    → List all active sessions

😴 Sleep Management:
  /admin sleep [chat_id] [hours]
    → Put chat to sleep (default: 24h)

  /admin wake [chat_id]
    → Wake sleeping chat

🔄 Session Control:
  /admin reset [chat_id]
    → Reset chat session & history

💡 Tips:
• [chat_id] is optional - defaults to current chat
• Chat IDs format: user_U123..., group_C123...
• Use 'sessions' to see active chat IDs
```

## Chat ID Format

TeacherBOY uses the following chat ID formats:

- **1-on-1 chats**: `user_U1234567890abcdef`
- **Group chats**: `group_C1234567890abcdef`
- **Room chats**: `room_R1234567890abcdef`

You can see chat IDs in:
1. Server logs when messages are received
2. Output of `/admin status` (shows current chat ID)
3. Output of `/admin sessions` (shows all active chat IDs)

## Common Use Cases

### Troubleshooting a Stuck Session

If a user reports the bot isn't responding:

```
/admin status user_U123456     # Check if sleeping or active
/admin reset user_U123456      # Reset to fresh state
```

### Emergency Stop for a Chat

If the bot is misbehaving in a specific chat:

```
/admin sleep group_C789012 168  # Sleep for 1 week (max)
```

### Monitor Bot Activity

```
/admin sessions  # See all active chats and their message counts
```

### Wake Bot After "Thank you TeacherBoy"

Users can put the bot to sleep with "Thank you TeacherBoy". To override:

```
/admin wake user_U123456
```

### Clear State Before Testing

When testing new features:

```
/admin reset              # Fresh state in current chat
```

## Security

### Authorization

- Only users listed in `ADMIN_USER_IDS` can execute admin commands
- Unauthorized users see no response (commands are silently ignored)
- Authorization is checked on every command

### Logging

All admin commands are logged for audit purposes:

```
🔧 Admin command executed by U1234567890abcdef in chat user_U9999: /admin reset
```

### Best Practices

1. **Limit Admin Access**: Only add trusted users to `ADMIN_USER_IDS`
2. **Regular Audits**: Review logs periodically for admin command usage
3. **Secure .env**: Keep your `.env` file secure and never commit it to version control
4. **Rotate IDs**: If an admin leaves the team, remove their ID immediately

## Priority System

Admin commands have the **highest priority (5)** in the agent routing system:

```
Priority 5:  AdminAgent (highest - processed first)
Priority 10: TranslationAgent
Priority 20: CalendarAgent
```

This ensures admin commands are **always processed first**, even if the translation agent would normally handle the message.

## Limitations

1. **No Retroactive Control**: Admin commands can't undo already-sent messages
2. **Local State Only**: Session management is in-memory (resets on bot restart)
3. **No Message History**: Admin commands can't access message content or history
4. **Single Bot Instance**: Commands only affect the bot instance they're sent to

## Testing

A comprehensive test suite (`tests/test_admin_agent.py`) covers:

- ✅ Authorization checks (authorized/unauthorized users)
- ✅ Command parsing and validation
- ✅ Status monitoring (active, inactive, sleeping)
- ✅ Sleep/wake functionality
- ✅ Session reset operations
- ✅ Chat ID extraction (user, group, room)
- ✅ Priority system validation

Run tests:
```bash
pytest tests/test_admin_agent.py -v
```

## Troubleshooting

### Admin commands not working?

1. **Check ADMIN_USER_IDS is set**:
   ```bash
   echo $ADMIN_USER_IDS
   ```

2. **Verify your LINE user ID is in the list**:
   - Send a message to the bot
   - Check logs for your user ID
   - Compare with ADMIN_USER_IDS

3. **Check bot logs for errors**:
   ```bash
   docker logs teacherboy-app-1 | grep -i admin
   ```

4. **Restart the bot** after changing .env:
   ```bash
   docker-compose restart
   ```

### Not seeing any response?

- Admin commands from **unauthorized users are silently ignored**
- This is by design for security (no error messages)
- Make sure your user ID is in `ADMIN_USER_IDS`

### Chat ID format issues?

- Always use the full chat ID as shown in `/admin status` or logs
- Format: `user_U123...`, `group_C123...`, `room_R123...`
- No spaces or extra characters

## Future Enhancements

Potential features for future versions:

- [ ] `/admin broadcast` - Send message to all active sessions
- [ ] `/admin stats` - Show overall bot statistics
- [ ] `/admin rate-limit` - Adjust rate limits per chat
- [ ] `/admin ban` - Block specific users
- [ ] `/admin logs` - Get recent error logs
- [ ] Persistent state (Redis/database) for cross-instance control
- [ ] Web dashboard for admin management

## Support

For issues or questions:

1. Check this documentation
2. Review server logs for error messages
3. Test with a fresh session (`/admin reset`)
4. Check GitHub issues for known problems

---

**Version:** 1.0.0  
**Last Updated:** December 12, 2025  
**License:** MIT
