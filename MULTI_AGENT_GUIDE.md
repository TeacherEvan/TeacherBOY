# Multi-Agent Architecture Guide

## 🏗️ Architecture Overview

TeacherBOY uses a **modular multi-agent architecture** that allows multiple specialized agents to coexist in a single bot, each triggered by different message patterns.

### Key Components

```
┌─────────────────────────────────────────────────┐
│                  LINE Platform                   │
└───────────────────┬─────────────────────────────┘
                    │ Webhook
                    ▼
┌─────────────────────────────────────────────────┐
│              FastAPI Application                 │
│  ┌────────────────────────────────────────────┐ │
│  │          Agent Router                      │ │
│  │  (Routes messages to appropriate agent)    │ │
│  └────────────────┬───────────────────────────┘ │
│                   │                              │
│       ┌───────────┼───────────┐                 │
│       ▼           ▼           ▼                 │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐          │
│  │Translation│ │  Math   │ │  Code   │  ...    │
│  │  Agent   │ │  Agent  │ │ Review  │          │
│  └─────────┘ └─────────┘ └─────────┘          │
└─────────────────────────────────────────────────┘
```

## 🎯 Agent System Design

### Base Agent

All agents inherit from `BaseAgent` which provides:

- **should_handle()**: Determines if agent should process message
- **handle()**: Processes the message
- **get_priority()**: Priority level (lower = higher priority)
- **enable/disable()**: Toggle agent on/off

### Agent Router

The router:

1. Receives incoming messages
2. Iterates through agents by priority
3. Calls `should_handle()` on each agent
4. Routes to first matching agent
5. Handles errors gracefully

## 📋 Current Agents

### 1. Translation Agent (Priority: 10)

- **Trigger**: Thai text detected OR active session
- **Features**:
  - Auto-detects Thai characters
  - Starts continuous translation session
  - Exits with "thanks Brown"
  - Uses Google Translate (primary) + LibreTranslate (fallback)

## 🔧 Adding New Agents

### Step 1: Create Agent Class

```python
# src/agents/math_agent.py
from .base_agent import BaseAgent
from linebot.v3.webhooks import MessageEvent
from linebot.v3.messaging import MessagingApi
import re

class MathAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="MathAgent",
            description="Solves math equations and shows steps"
        )

    def get_priority(self) -> int:
        return 20  # Lower than translation

    async def should_handle(self, event: MessageEvent, text: str) -> bool:
        # Trigger on math expressions
        return bool(re.search(r'\d+\s*[\+\-\*/]\s*\d+|solve|calculate', text))

    async def handle(self, event: MessageEvent, text: str, line_bot_api: MessagingApi) -> bool:
        # Process math equation
        result = self._solve_equation(text)
        # Send reply...
        return True
```

### Step 2: Register Agent

```python
# In src/main.py lifespan function
math_agent = MathAgent()
agent_router.register_agent(math_agent)
```

### Step 3: Test

Send message with math expression → MathAgent handles it!

## 🎨 Agent Priority System

Agents are checked in priority order (lowest first):

| Priority | Agent                 | Trigger                     |
| -------- | --------------------- | --------------------------- |
| 10       | TranslationAgent      | Thai text or active session |
| 20       | MathAgent (future)    | Math expressions            |
| 30       | CodeAgent (future)    | Code blocks                 |
| 50       | DefaultAgent (future) | Fallback                    |

**Note**: First agent to return `True` from `should_handle()` processes the message.

## 🔐 Multiple Bot Instances

While the architecture supports it, **we recommend one bot with multiple agents** because:

✅ **Benefits**:

- Single webhook endpoint
- Shared context between agents
- Easier maintenance
- Better user experience

❌ **Multiple bots** would require:

- Separate LINE Official Accounts
- Multiple webhook URLs
- Users adding each bot separately
- Complex context sharing

### Configuration (if needed)

```bash
# .env
ADDITIONAL_AGENTS={"agent2": {"channel_secret": "...", "channel_access_token": "..."}}
```

## 🚀 Agent Communication

Agents can share data through:

1. **Session Manager**: Persistent state per chat
2. **Event Context**: LINE event object
3. **Database** (future): Shared storage

Example:

```python
# Agent A stores data
session_manager.set_data(chat_id, "math_history", [equations])

# Agent B retrieves data
history = session_manager.get_data(chat_id, "math_history")
```

## 🐛 Debugging Multi-Agent System

### Enable Debug Logging

```bash
# .env
DEBUG=True
```

### Check Agent Status

```bash
# View registered agents in startup logs
docker logs teacherboy | grep "Registered agent"
```

### Test Agent Routing

```bash
# Watch routing decisions
docker logs -f teacherboy | grep "Routing message"
```

## 📊 Performance Considerations

### Agent Selection

- **Fast checks**: Use regex, simple string matching
- **Expensive checks**: Only if likely to handle
- **Timeout**: Each agent has 30s timeout

### Memory

- Each agent instance: ~1-5 MB
- Sessions: ~1 KB per active chat
- Translation cache: Configurable

### Scaling

- **Single server**: 10-20 agents comfortably
- **Load balancing**: Use Redis for session sharing
- **Microservices**: Split agents to separate containers (if needed)

## 🎓 Best Practices

### 1. Specific Triggers

```python
# ❌ Too broad
return "hi" in text.lower()

# ✅ Specific pattern
return text.lower().strip() in ["hi brown", "hello brown"]
```

### 2. Priority Order

- Most specific patterns = Lowest priority number
- Generic fallbacks = Highest priority number

### 3. Error Handling

```python
async def handle(self, event, text, line_bot_api):
    try:
        # Your logic
        return True
    except Exception as e:
        logger.error(f"Agent error: {e}")
        return False  # Let next agent try
```

### 4. State Management

- Use `session_manager` for persistent state
- Clean up sessions when done
- Don't rely on global variables

## 📚 Example: Adding Quiz Agent

```python
# src/agents/quiz_agent.py
from .base_agent import BaseAgent

class QuizAgent(BaseAgent):
    def __init__(self):
        super().__init__(
            name="QuizAgent",
            description="Interactive vocab and grammar quizzes"
        )
        self.active_quizzes = {}

    def get_priority(self) -> int:
        return 25

    async def should_handle(self, event, text):
        chat_id = self._get_chat_id(event)
        keywords = ["quiz", "test me", "practice"]

        # Handle if quiz active OR quiz keyword
        return (chat_id in self.active_quizzes or
                any(kw in text.lower() for kw in keywords))

    async def handle(self, event, text, line_bot_api):
        # Create quiz, track answers, score
        # ...
        return True
```

## 🔮 Future Enhancements

### Planned Features

- [ ] Agent marketplace (load agents dynamically)
- [ ] Per-user agent preferences
- [ ] Agent analytics dashboard
- [ ] Multi-language agent support
- [ ] Agent chaining (agent calls another agent)

### Possible Agents

- 📐 **MathAgent**: Equation solver
- 💻 **CodeReviewAgent**: Code analysis
- 📝 **QuizAgent**: Vocabulary practice
- 🎨 **ArtAgent**: Generate images
- 📊 **DataAgent**: Parse and visualize data
- 🎯 **GoalAgent**: Track learning progress

## 🆘 Troubleshooting

### Agent Not Triggering

1. Check `should_handle()` logic
2. Verify priority order
3. Check if another agent handles first
4. Enable debug logging

### Multiple Agents Triggering

- First matching agent (by priority) handles message
- Other agents are skipped
- Design triggers to be mutually exclusive

### Performance Issues

- Profile agent `should_handle()` methods
- Cache expensive checks
- Use async operations
- Consider agent pooling

## 📖 Further Reading

- [Base Agent Implementation](../src/agents/base_agent.py)
- [Agent Router Code](../src/agents/agent_router.py)
- [Translation Agent Example](../src/agents/translation_agent.py)
- [Session Manager](../src/services/session_manager.py)

---

**Need help?** Check logs, review examples, or open an issue!
