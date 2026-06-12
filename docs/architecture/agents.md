# Agents

Ms. Green uses a priority-based multi-agent router.

## Default agents (current)

The router evaluates agents in ascending priority (lower runs first).
Registration happens in `src/main.py`, and some agents are conditional on configuration.

<!-- markdownlint-disable MD060 -->

| Priority | Agent Class | Conditional | Trigger Pattern | Description |
|----------|------------|-------------|-----------------|-------------|
| 4 | `ModModeAgent` | Yes* | `activate mod mode`, `/modmode ...` | Group moderation: kick, warn, ban, 3-strike, auto-kick, harmful detection, Flex dashboard |
| 5 | `HelpAgent` | No | `help`, `/help`, `Ms. Green help` | Interactive help and command discovery |
| 5 | `AdminAgent` | Yes | `/admin`, `/mod` | Administrative commands and privileged control |
| 6 | `CalendarAgent` | Yes | `Ms. Green calendar`, `Ms. Green add`, `Ms. Green events` | Event scheduling, reminders, scraping |
| 6 | `HannibalProfileAgent` | Yes | `hannibal profile`, `analyze messages` | Psychological profiling from message history |
| 7 | `ProfilerAgent` | Yes | Image profile triggers | Image-based behavioral profiling |
| 7 | `ImageAnalyzerAgent` | Yes | `Ms. Green analyze`, image follow-up flow | General image Q&A and date extraction |
| 8 | `DocumentMemoryAgent` | Yes | File uploads, `Ms. Green doc`, `Ms. Green docs` | PDF/DOCX storage and retrieval |
| 8 | `SearchAgent` | No | `Ms. Green search <query>` | Web search via Brave Search API |
| 9 | `LLMAgent` | No | `Ms. Green <prompt>` | General LLM conversation |
| 10 | `TranslationAgent` | No | Default/fallback | Thai-English bidirectional translation |
| 12 | `SpecialNewsAgent` | No | `/special news` | Tourism, sports, and international news |
| 15 | `NewsAgent` | No | `news`, `ข่าว` | Weather, air quality, headlines, markets |

* `ModModeAgent` only activates in groups where an admin has said `activate mod mode`. It intercepts ALL messages in that group before any other agent.

<!-- markdownlint-enable MD060 -->

## Router contract

The router evaluates agents in ascending `get_priority()` order and stops at the first agent that returns `True` from `handle()`.

Key behaviors:

- Only text messages are routed.
- Image and file events can still be handled by agents that inspect non-text payloads.
- Disabled agents are skipped.
- Exceptions inside an agent do not crash the webhook; routing continues to the next agent.
- **ModModeAgent (Priority 4) intercepts ALL messages in groups where mod mode is active** — it returns `True` from `should_handle()` for any message in a mod-enabled group, ensuring moderation runs before translation/LLM agents.

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
- Match new priorities to the existing routing contract in `src/main.py`.
