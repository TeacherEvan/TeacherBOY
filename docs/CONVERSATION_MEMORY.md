# Conversation Memory

Zeus supports multi-turn conversations with context retention using Hugging Face Hub for persistent storage.

## Overview

The conversation memory feature allows Zeus to:

- **Remember previous messages** within a chat session
- **Maintain context** across multiple exchanges
- **Persist conversations** to Hugging Face Hub (optional)
- **Respect privacy** by hashing chat IDs before storage

## Quick Start

### In-Memory Only (No Configuration Required)

Conversation memory works out of the box with in-memory storage:

```bash
# Just enable the feature (enabled by default)
CONVERSATION_MEMORY_ENABLED=true
```

### Persistent Storage (Hugging Face Hub)

For persistence across restarts:

1. **Create a Hugging Face token** at <https://huggingface.co/settings/tokens>
   - Select "write" permissions

2. **Add to environment**:

   ```bash
   HF_MEMORY_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   HF_MEMORY_REPO_ID=your-username/zeus-memory
   ```

3. The repo will be created automatically as a private dataset if it doesn't exist

## Configuration

| Variable                      | Default | Description                                   |
| ----------------------------- | ------- | --------------------------------------------- |
| `CONVERSATION_MEMORY_ENABLED` | `true`  | Enable/disable conversation memory            |
| `HF_MEMORY_TOKEN`             | -       | Hugging Face API token (optional)             |
| `HF_MEMORY_REPO_ID`           | -       | Dataset repo ID, e.g., `username/zeus-memory` |
| `CONVERSATION_MAX_MESSAGES`   | `20`    | Max messages per session (5-50)               |
| `CONVERSATION_TTL_HOURS`      | `24`    | Session expiration in hours (1-168)           |

## Usage

### Normal Conversation

Simply chat with Zeus - context is automatically maintained:

```text
User: Zeus who was the first president of the United States?
Zeus: The first President of the United States was George Washington...

User: Zeus when was he born?
Zeus: George Washington was born on February 22, 1732...
         ↑ Zeus remembers "he" refers to George Washington
```

### Clear Memory

To start fresh:

```text
User: Zeus clear
Zeus: 🧹 Conversation memory cleared. I've forgotten our previous chat. Start fresh!
```

Alternative commands:

- `Zeus forget`
- `Zeus reset`

## How It Works

### Storage Architecture

```text
                    ┌─────────────────┐
                    │   LINE Message  │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │   LLM Agent     │
                    └────────┬────────┘
                             │
              ┌──────────────┴──────────────┐
              │   ConversationMemoryService │
              └──────────────┬──────────────┘
                             │
         ┌───────────────────┴───────────────────┐
         │                                       │
┌────────▼────────┐                   ┌──────────▼──────────┐
│  In-Memory      │                   │  Hugging Face Hub   │
│  (OrderedDict)  │                   │  (CommitScheduler)  │
└─────────────────┘                   └─────────────────────┘
```

### Privacy Features

- **Chat IDs are hashed** using SHA-256 before storage
- **No personally identifiable information** is stored in filenames
- **HF repos are created as private** by default
- **Conversations auto-expire** after configured TTL

### Token Management

The service automatically:

- Estimates token usage for messages (~1 token per 4 chars)
- Trims old messages when approaching context limits
- Keeps most recent messages for best context

## API Reference

### ConversationMemoryService

```python
from src.services.conversation_memory_service import get_conversation_memory

memory = get_conversation_memory()

# Add a message
await memory.add_message(chat_id, "user", "Hello!", user_id)
await memory.add_message(chat_id, "assistant", "Hi there!")

# Get context for LLM prompt
context = await memory.get_context_messages(chat_id)
# Returns: [{"role": "user", "content": "..."}, {"role": "assistant", ...}]

# Clear conversation
await memory.clear_conversation(chat_id)

# Get summary
summary = await memory.get_conversation_summary(chat_id)
# Returns: {"message_count": 5, "last_activity": datetime, ...}
```

## Troubleshooting

### Memory Not Persisting

1. **Check HF token permissions** - needs "write" scope
2. **Verify repo ID format** - should be `username/repo-name`
3. **Check logs** for `💭` emoji messages indicating memory operations

### Context Not Being Used

1. **Verify memory is enabled**: `CONVERSATION_MEMORY_ENABLED=true`
2. **Check session hasn't expired**: default TTL is 24 hours
3. **Clear and retry**: `Zeus clear` then start new conversation

### HF Hub Sync Issues

The service uses `CommitScheduler` which batches uploads every 5 minutes:

- Immediate memory operations use local storage
- Hub sync happens asynchronously
- On shutdown, remaining data is flushed

## Integration with LLM Agent

The LLM agent automatically:

1. **Records user messages** before calling the LLM
2. **Retrieves conversation context** to build the prompt
3. **Records assistant responses** after receiving them
4. **Handles memory commands** (clear/forget/reset)

```python
# In llm_agent.py handle() method:
memory = get_conversation_memory()

# Add user message to memory
await memory.add_message(chat_id, "user", query, user_id)

# Get context for multi-turn conversation
context_messages = await memory.get_context_messages(chat_id)

# Build prompt with context
messages = [{"role": "system", "content": system_prompt}]
messages.extend(context_messages[:-1])  # Previous exchanges
messages.append({"role": "user", "content": query})  # Current query

# Call LLM
response = await llm_provider.chat_completion(messages)

# Save response to memory
await memory.add_message(chat_id, "assistant", response)
```

## Best Practices

1. **Set appropriate TTL** - shorter for high-traffic bots
2. **Monitor storage usage** - check HF Hub dashboard periodically
3. **Use memory commands** to reset stuck contexts
4. **Configure max messages** based on your LLM's context window
