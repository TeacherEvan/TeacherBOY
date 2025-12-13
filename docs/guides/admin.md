# Admin Control

TeacherBOY includes an Admin Agent (priority 5) for in-chat operations.

## Enable admin

You have two supported ways.

### Option A: Static admins (recommended)

Set `ADMIN_USER_IDS` to a comma-separated list of LINE user IDs.

### Option B: Bootstrap claim (safe for first-time setup)

1. Set `ADMIN_SETUP_KEY` to a random string (temporary).
2. In LINE, send:

   - `/admin claim <ADMIN_SETUP_KEY>`

3. The bot replies with your LINE user ID.
4. Set `ADMIN_USER_IDS=<that id>`, restart the app, and remove `ADMIN_SETUP_KEY`.

## Commands

Full command reference: [docs/ADMIN_COMMANDS.md](../ADMIN_COMMANDS.md)

Common:

- `/admin status`
- `/admin sessions`
- `/admin sleep [chat_id] [hours]`
- `/admin wake [chat_id]`
- `/admin reset [chat_id]`
