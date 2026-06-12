# Ms. Green Documentation

**📍 This folder is the single source of truth for all documentation.**

## Start Here

- **Quick Start:** [guides/quickstart.md](guides/quickstart.md) - Get the bot running in 5 steps
- **LINE Setup:** [guides/line-setup.md](guides/line-setup.md) - Get LINE tokens & configure webhook
- **Deployment:** [guides/deployment.md](guides/deployment.md) - Deploy to production (Docker/cloud)
- **Quick Reference:** [reference/quick-reference.md](reference/quick-reference.md) - Essential info at a glance ⚡

## Operating the Bot

- **Admin Quick Start:** [ADMIN_QUICK_START.md](ADMIN_QUICK_START.md) - 5-minute admin setup guide
- **Admin Commands:** [ADMIN_COMMANDS.md](ADMIN_COMMANDS.md) - Full `/admin` command reference
- **Tracing:** [TRACING.md](TRACING.md) - OpenTelemetry tracing with VS Code AI Toolkit

## Developer Documentation

- **System Overview:** [architecture/overview.md](architecture/overview.md) - Async design, HTTP pooling, FastAPI
- **Agent System:** [architecture/agents.md](architecture/agents.md) - Priorities, routing, adding new agents

## Feature Documentation

- **Moderator Mode:** [MODERATOR_MODE.md](MODERATOR_MODE.md) - Group moderation: kick, warn, ban, 3-strike, auto-kick, dashboard
- **Calendar & Reminders:** [CALENDAR_REMINDERS.md](CALENDAR_REMINDERS.md) - Commands, reminders, chat-scoped events
- **Google Calendar Backend:** [GOOGLE_CALENDAR.md](GOOGLE_CALENDAR.md) - Optional Google Calendar integration
- **Conversation Memory:** [CONVERSATION_MEMORY.md](CONVERSATION_MEMORY.md) - Multi-turn memory with optional HF sync
- **Document Memory:** [DOCUMENT_MEMORY.md](DOCUMENT_MEMORY.md) - PDF and DOCX storage and retrieval
- **Image Privacy:** [IMAGE_PRIVACY.md](IMAGE_PRIVACY.md) - Image retention and cleanup guarantees
- **Profiler:** [PROFILER_USAGE.md](PROFILER_USAGE.md) - Vision-based profiling workflow
- **News Agent:** [NEWS_AGENT.md](NEWS_AGENT.md) - Weather, headlines, access control, usage examples
- **News Usage Examples:** [NEWS_USAGE_EXAMPLES.md](NEWS_USAGE_EXAMPLES.md) - Detailed LINE chat interaction flows
- **KPS Assistant:** [KPS_ASSISTANT.md](KPS_ASSISTANT.md) - Staff assistant workflows
- **Incomplete Sentence Fix:** [INCOMPLETE_SENTENCE_FIX.md](INCOMPLETE_SENTENCE_FIX.md) - Translation hallucination prevention
- **LLM Provider Setup:** [GITHUB_MODELS.md](GITHUB_MODELS.md) - GitHub Models and provider priority
- **Productivity Optimizations:** [guides/PRODUCTIVITY_OPTIMIZATIONS.md](guides/PRODUCTIVITY_OPTIMIZATIONS.md) - Token reduction, summarization, cost optimization

## Reference

- **Environment Variables:** [reference/environment.md](reference/environment.md) - All settings explained
- **Quick Reference Card:** [reference/quick-reference.md](reference/quick-reference.md) - Commands, rate limits, file locations
- **Maintainer Notes:** [reference/maintainers.md](reference/maintainers.md) - Maintenance rules and architecture constraints