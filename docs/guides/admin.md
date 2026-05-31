# Admin Control

This page is a compact pointer to the maintained admin docs.

## Use these docs

- [ADMIN_QUICK_START.md](../ADMIN_QUICK_START.md) for first-time setup in a few minutes
- [ADMIN_COMMANDS.md](../ADMIN_COMMANDS.md) for the full `/admin` reference

## Supported setup paths

### Option A: Static admins

Set `ADMIN_USER_IDS` to a comma-separated list of LINE user IDs.

### Option B: Bootstrap claim

1. Set `ADMIN_SETUP_KEY` to a temporary random string.
2. In LINE, send `/admin claim <ADMIN_SETUP_KEY>`.
3. Add the returned user ID to `ADMIN_USER_IDS`.
4. Restart the app and remove `ADMIN_SETUP_KEY`.

## Most-used commands

- `/admin status`
- `/admin sessions`
- `/admin sleep [chat_id] [hours]`
- `/admin wake [chat_id]`
- `/admin reset [chat_id]`
