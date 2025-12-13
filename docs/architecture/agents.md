# Agents

TeacherBOY uses a priority-based multi-agent router.

## Router contract

The router evaluates agents in ascending `get_priority()` order and stops at the first agent that returns `True` from `handle()`.

Key behaviors:

- Only text messages are routed.
- Disabled agents are skipped.
- Exceptions inside an agent do not crash the webhook; routing continues to the next agent.

## Adding a new agent

1. Create a new class implementing `BaseAgent`.
1. Implement:

   - `should_handle(event, text) -> bool`
   - `handle(event, text, line_bot_api) -> bool`

1. Choose a priority:

- Use < 10 only if your agent must preempt translation.
- Use > 10 if translation should remain the default.

1. Register it during lifespan startup in `src/main.py`.

## Example skeleton

```python
from src.agents.base_agent import BaseAgent

class ExampleAgent(BaseAgent):
    def __init__(self):
        super().__init__(name="ExampleAgent", description="Example")

    def get_priority(self) -> int:
        return 30

    async def should_handle(self, event, text: str) -> bool:
        return text.lower().startswith("/example")

    async def handle(self, event, text: str, line_bot_api) -> bool:
        # Reply via line_bot_api
        return True
```

## Best practices

- Make `should_handle` cheap and specific.
- Keep `handle` resilient: return `False` if you want the next agent to try.
- Avoid global state; use the session manager if you need per-chat state.
