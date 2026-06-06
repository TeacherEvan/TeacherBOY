"""
Application configuration and settings management.

This module provides type-safe, validated configuration for the TeacherBOY/Ms. Green application,
following production best practices for environment-based configuration management.
"""

import json
import logging
import os
from typing import Any

from pydantic import AliasChoices, Field, HttpUrl, field_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Production-grade application settings with comprehensive validation.

    All settings are loaded from environment variables with sensible defaults.
    Critical settings are validated at startup to fail fast on misconfiguration.
    """

    # ============================================================================
    # LINE Bot Configuration - Primary Agent (Ms. Green)
    # ============================================================================
    line_channel_secret: str | None = Field(
        default=None,
        min_length=10,
        description="LINE Bot channel secret for webhook signature verification",
    )
    line_channel_access_token: str | None = Field(
        default=None,
        min_length=10,
        description="LINE Bot channel access token for API authentication",
    )

    # ============================================================================
    # Multi-Agent Configuration (Optional)
    # ============================================================================
    additional_agents: str | None = Field(default=None, description="JSON string with additional agent configurations")

    # ============================================================================
    # Admin Control Configuration
    # ============================================================================
    admin_user_ids: str | None = Field(default=None, description="Comma-separated list of LINE user IDs authorized as admins")

    admin_setup_key: str | None = Field(
        default=None,
        description=(
            "Optional one-time admin bootstrap key. If set, a user can run '/admin claim <key>' "
            "to reveal their LINE user ID and become an in-memory admin for the current process."
        ),
    )

    moderator_user_ids: str | None = Field(
        default=None, description="Comma-separated list of LINE user IDs authorized as moderators (can access news directly)"
    )

    bot_identity_storage_path: str = Field(
        default="./data/bot_identity/profile.json",
        description="Local JSON storage for runtime bot name and aliases.",
    )
    bot_identity_default_name: str = Field(
        default="Ms. Green",
        description="Default runtime display name before admin changes.",
    )
    bot_identity_default_aliases: str = Field(
        default="ms. green,ms green",
        description="Comma-separated default wake/prefix aliases.",
    )

    # ============================================================================
    # Translation Service Configuration
    # ============================================================================
    google_translate_api_key: str | None = Field(
        default=None,
        description="Google Translate API key retained for startup compatibility.",
    )

    # Translation Performance Optimization
    # NOTE: Caching implementation is planned for future release
    translation_cache_ttl_seconds: int = Field(
        default=3600,
        ge=0,
        description="TTL for translation cache in seconds (0 to disable) - TODO",
    )
    translation_max_retries: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum retry attempts for failed translation requests",
    )
    translation_detect_incomplete: bool = Field(
        default=True,
        description="Auto-detect incomplete sentences and append '...' to prevent hallucination",
    )

    libretranslate_api_url: str | None = Field(
        default=None,
        description="LibreTranslate API endpoint URL",
        validation_alias=AliasChoices("LIBRETRANSLATE_API_URL"),
    )
    libretranslate_api_key: str | None = Field(
        default=None,
        description="LibreTranslate API key",
        validation_alias=AliasChoices("LIBRETRANSLATE_API_KEY"),
    )

    # ============================================================================
    # News Agent Configuration
    # ============================================================================
    news_api_key: str | None = Field(
        default=None,
        description="DEPRECATED: NewsAPI.org key (now using RSS feeds)",
    )
    weather_cache_ttl_seconds: int = Field(
        default=1800,
        ge=300,
        le=7200,
        description="Weather data cache TTL in seconds (default: 30 minutes)",
    )
    news_cache_ttl_seconds: int = Field(
        default=3600,
        ge=600,
        le=14400,
        description="News headlines cache TTL in seconds (default: 1 hour)",
    )

    # ============================================================================
    # Extended News Agent Configuration (Optional APIs)
    # ============================================================================
    exchange_rate_api_key: str | None = Field(
        default=None,
        description="ExchangeRate-API key for currency conversion (optional; 1500 req/mo free)",
    )
    tat_api_key: str | None = Field(
        default=None,
        description="Tourism Authority of Thailand (TAT) API key for events/festivals",
    )

    # ============================================================================
    # Hermes / OpenAI-compatible fallback Configuration
    # ============================================================================
    hermes_api_key: str | None = Field(
        default=None,
        description="Hermes / OpenAI-compatible provider API key (Bearer token)",
    )
    hermes_base_url: str | None = Field(
        default=None,
        description="Base URL for Hermes/OpenAI-compatible provider API (e.g., https://your-hermes-host/v1)",
    )
    hermes_model: str | None = Field(
        default=None,
        description="Fallback Hermes/OpenAI-compatible model identifier",
    )

    # ============================================================================
    # Fallback / provider priority Configuration (LLM)
    # ============================================================================
    llm_fallback_provider_priority: str = Field(
        default="hermes,openrouter,github",
        description=(
            "Comma-separated priority list for LLM providers and fallback chain. "
            "Options: hermes, openrouter, github. First configured provider is used; "
            "if that fails, the next configured provider is tried."
        ),
    )

    # ============================================================================
    # OpenRouter Configuration (LLM)
    # ============================================================================
    openrouter_api_key: str | None = Field(
        default=None,
        description="OpenRouter API key for LLM access",
    )
    openrouter_default_model: str = Field(
        default="google/gemma-2-9b-it",
        description="Default model to use for OpenRouter (must be a free model)",
        validation_alias=AliasChoices("OPENROUTER_DEFAULT_MODEL", "DEFAULT_MODEL"),
    )
    openrouter_translation_model: str | None = Field(
        default=None,
        description="Optional OpenRouter model override for translation fallback only",
    )

    llm_system_prompt: str = Field(
        default=(
            "You are Ms. Green, a gentle and exceptionally wise assistant. Speak with calm authority, "
            "patience, and clear judgment. Your manner should feel composed and dignified, like an "
            "ancient elven counselor, but without fairy-tale lore, theatrical magic, or ornamental "
            "fantasy language. Be warm, grounded, and concise. When asked to introduce yourself or "
            "identify who you are, answer as Ms. Green."
        ),
        description=(
            "System prompt for the LLM agent (OpenRouter). Controls the bot's personality/tone with a calm, wise Ms. Green persona."
        ),
    )

    llm_temperature: float = Field(
        default=1.15,
        ge=0.0,
        le=2.0,
        description="LLM temperature ('warmth') for TeacherBOY responses (0-2). Higher = more creative/warm.",
    )

    # AI group access control (group/room). Private chats are always allowed.
    zeus_group_access_mode: str = Field(
        default="all",
        description=("Group/room access mode for group command usage. Options: 'all' (default), 'allowlist', 'denylist'."),
    )
    zeus_allowed_group_ids: str | None = Field(
        default=None,
        description=("Comma-separated list of allowed group_id/room_id values in allowlist mode. Example: 'C123,R456'."),
    )
    zeus_denied_group_ids: str | None = Field(
        default=None,
        description=("Comma-separated list of denied group_id/room_id values in denylist mode. Example: 'C123,R456'."),
    )

    # ============================================================================
    # Search Agent Configuration
    # ============================================================================
    brave_search_api_key: str | None = Field(
        default=None,
        description="Brave Search API key for web search capabilities",
    )

    # ============================================================================
    # Conversation Memory Configuration (HF Hub Persistence)
    # ============================================================================
    hf_memory_token: str | None = Field(
        default=None,
        description=(
            "Hugging Face API token for conversation memory persistence. "
            "Create at https://huggingface.co/settings/tokens with 'write' scope."
        ),
    )
    hf_memory_repo_id: str | None = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for storing conversation memory. "
            "Example: 'username/teacherboy-memory'. Will be created as private if it doesn't exist."
        ),
    )
    conversation_memory_enabled: bool = Field(
        default=True,
        description="Enable conversation memory for contextual multi-turn LLM conversations.",
    )
    conversation_max_messages: int = Field(
        default=20,
        ge=5,
        le=50,
        description="Maximum messages to retain per conversation session.",
    )
    conversation_ttl_hours: int = Field(
        default=24,
        ge=1,
        le=168,
        description="Hours before conversation session expires (1-168, default: 24).",
    )
    conversation_storage_path: str = Field(
        default="./data/conversations",
        description="Local directory for conversation memory persistence and HF sync cache.",
    )

    # ============================================================================
    # Review Agent Configuration
    # ============================================================================
    staff_memory_storage_path: str = Field(
        default="./data/staff_memory/staff_memory.json",
        description="Local JSON storage for review-agent staff memory.",
    )

    # ==========================================================================
    # Document Memory Configuration (PDF/DOCX persistence)
    # ==========================================================================
    document_memory_enabled: bool = Field(
        default=True,
        description="Enable document memory for PDF/DOCX uploads.",
    )
    document_storage_path: str = Field(
        default="./data/documents",
        description="Local directory for document storage.",
    )
    document_hf_repo_id: str | None = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for document storage. "
            "Example: 'username/teacherboy-documents'. Will be created as private if it doesn't exist."
        ),
    )
    document_max_file_size_mb: float = Field(
        default=10.0,
        ge=1.0,
        le=50.0,
        description="Max document file size in MB (1-50).",
    )
    document_max_text_chars: int = Field(
        default=80000,
        ge=1000,
        le=500000,
        description="Max extracted text chars stored per document.",
    )

    # ============================================================================
    # History Logging Configuration
    # ============================================================================
    history_log_enabled: bool = Field(
        default=True,
        description="Enable comprehensive history logging for audit trails.",
    )
    history_log_path: str = Field(
        default="./data/logs",
        description="Local directory for storing history logs.",
    )
    history_log_encryption_key: str | None = Field(
        default=None,
        description=(
            "Optional encryption key for sensitive log data. "
            "When set, logs are encrypted using AES (requires 'cryptography' package)."
        ),
    )
    history_log_hf_repo_id: str | None = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for cloud log backup. "
            "Example: 'username/teacherboy-logs'. Will be created as private if it doesn't exist."
        ),
    )
    history_log_rotation_days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Days before old logs are archived (1-30, default: 7).",
    )
    zeus_error_style: bool = Field(
        default=True,
        description="Format error messages in the bot persona's consistent style.",
    )

    # ============================================================================
    # GitHub Models Configuration (Alternative to OpenRouter)
    # ============================================================================
    github_models_pat: str | None = Field(
        default=None,
        description=(
            "GitHub Personal Access Token (PAT) with 'models:read' scope for GitHub Models API. "
            "Create at https://github.com/settings/tokens"
        ),
    )
    github_models_default_model: str = Field(
        default="openai/gpt-4o",
        description=(
            "Default model for GitHub Models API. Options include: "
            "openai/gpt-4o, openai/gpt-4o-mini, xai/grok-3, deepseek/deepseek-r1, "
            "meta/llama-3.3-70b-instruct. See https://github.com/marketplace/models"
        ),
    )
    llm_provider_priority: str = Field(
        default="hermes,openrouter,github",
        description=(
            "Comma-separated priority list for LLM providers. "
            "Options: 'hermes', 'openrouter', 'github'. First configured provider is used."
        ),
    )

    # ============================================================================
    # Psychological Profiler Configuration (Vision AI)
    # ============================================================================
    profiler_enabled: bool = Field(
        default=True,
        description="Enable psychological profiling of photos using vision AI.",
    )
    profiler_model: str = Field(
        default="openai/gpt-4o",
        description=(
            "Model for vision-based psychological profiling. "
            "Must support multimodal/vision input. Options: openai/gpt-4o, openai/gpt-4o-mini"
        ),
    )
    profiler_analysis_type: str = Field(
        default="full",
        description=(
            "Analysis depth: 'full' (FBI+Ekman+Navarro), 'quick' (basic emotions only), "
            "'body' (body language focus), 'facial' (micro-expressions focus)."
        ),
    )
    profiler_analysis_depth: str = Field(
        default="standard",
        description=(
            "Token optimization level for profiler: 'quick' (~800 tokens), "
            "'standard' (~1,800 tokens), 'full' (~2,400 tokens). "
            "Overrides profiler_analysis_type when use_optimized_prompts=true."
        ),
    )
    profiler_rate_limit_per_hour: int = Field(
        default=3,
        ge=1,
        le=20,
        description="Maximum photo analyses per hour per chat (1-20, default: 3).",
    )
    profiler_max_image_size_mb: float = Field(
        default=10.0,
        ge=1.0,
        le=20.0,
        description="Maximum image file size in MB for analysis (1-20, default: 10).",
    )

    # Cache TTLs for new menu items
    color_cache_ttl_seconds: int = Field(
        default=86400,
        ge=3600,
        le=86400,
        description="Thai lucky color cache TTL (default: 24 hours)",
    )
    sunset_cache_ttl_seconds: int = Field(
        default=86400,
        ge=3600,
        le=86400,
        description="Sunset/sunrise times cache TTL (default: 24 hours)",
    )
    holiday_cache_ttl_seconds: int = Field(
        default=604800,
        ge=86400,
        le=604800,
        description="Thai holidays cache TTL (default: 7 days)",
    )
    bitcoin_cache_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Bitcoin price cache TTL (default: 5 minutes; volatile data)",
    )
    exchange_cache_ttl_seconds: int = Field(
        default=3600,
        ge=300,
        le=14400,
        description="Exchange rate cache TTL (default: 1 hour)",
    )
    friend_cache_ttl_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Friend status cache TTL in seconds (default: 5 minutes)",
    )

    # ============================================================================
    # Productivity Optimization Configuration
    # ============================================================================
    use_optimized_prompts: bool = Field(
        default=True,
        description="Enable modular prompt system for 60-70% token reduction in vision tasks.",
    )
    enable_conversation_summarization: bool = Field(
        default=True,
        description="Enable automatic conversation summarization to reduce memory token usage by 60-80%.",
    )
    conversation_summary_interval: int = Field(
        default=10,
        ge=5,
        le=30,
        description="Number of messages before triggering automatic summarization (5-30, default: 10).",
    )
    conversation_messages_to_keep_full: int = Field(
        default=6,
        ge=3,
        le=15,
        description="Number of recent messages to keep in full after summarization (3-15, default: 6).",
    )

    # ============================================================================
    # Calendar and Reminders Configuration
    # ============================================================================
    calendar_enabled: bool = Field(
        default=True,
        description="Enable calendar and reminder features.",
    )
    calendar_reminder_hour: int = Field(
        default=8,
        ge=0,
        le=23,
        description="Hour of day (0-23) to send reminder notifications (default: 8 AM).",
    )
    calendar_data_path: str = Field(
        default="./data/calendar",
        description="Local directory for storing calendar data (legacy).",
    )
    calendar_hf_repo_id: str | None = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for calendar data backup. "
            "Example: 'username/teacherboy-calendar'. Uses hf_memory_token for auth."
        ),
    )
    calendar_sync_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Interval in seconds for syncing calendar to HF Hub (default: 5 minutes).",
    )
    calendar_encryption_key: str | None = Field(
        default=None,
        description=(
            "AES encryption key for local calendar data (32 bytes base64). "
            "If set, all calendar events stored locally will be encrypted at rest. "
            "Generate with: python -c 'import secrets; print(secrets.token_urlsafe(32))'"
        ),
    )
    calendar_max_events_per_user: int = Field(
        default=100,
        ge=10,
        le=1000,
        description="Maximum number of events allowed per user (spam prevention).",
    )
    calendar_max_title_length: int = Field(
        default=200,
        ge=10,
        le=500,
        description="Maximum length for event titles.",
    )
    calendar_max_description_length: int = Field(
        default=1000,
        ge=50,
        le=5000,
        description="Maximum length for event descriptions.",
    )

    # ============================================================================
    # Google Calendar Integration (Recommended)
    # ============================================================================
    google_calendar_enabled: bool = Field(
        default=False,
        description="Enable Google Calendar integration (overrides local storage).",
    )
    google_calendar_credentials_file: str = Field(
        default="data/google_credentials.json",
        description=(
            "Path to Google OAuth client credentials JSON file. "
            "Download from: https://console.cloud.google.com/apis/credentials"
        ),
    )
    google_calendar_token_file: str = Field(
        default="data/google_token.json",
        description="Path to store Google OAuth token after authorization.",
    )
    google_calendar_id: str = Field(
        default="primary",
        description="Google Calendar ID to use (default: 'primary' for user's main calendar).",
    )

    # ============================================================================
    # Structured Persistence Configuration
    # ============================================================================
    persistence_backend: str = Field(
        default="local",
        description="Persistence backend selection: local or convex.",
    )
    convex_deployment_url: HttpUrl | None = Field(
        default=None,
        description="Convex HTTP deployment URL for structured persistence.",
    )
    convex_sync_token: str | None = Field(
        default=None,
        description="Bearer token used for Convex HTTP sync requests.",
    )
    convex_request_timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=60,
        description="Timeout in seconds for Convex HTTP requests.",
    )
    convex_require_healthcheck_on_startup: bool = Field(
        default=False,
        description="Require a successful Convex health check during startup.",
    )

    # ============================================================================
    # HTTP Client Configuration
    # ============================================================================
    http_client_timeout_seconds: int = Field(default=30, ge=5, le=300, description="HTTP client timeout in seconds")
    http_client_max_connections: int = Field(default=100, ge=10, le=1000, description="Maximum concurrent HTTP connections")
    http_client_max_keepalive: int = Field(default=20, ge=5, le=100, description="Maximum keep-alive connections")

    # ============================================================================
    # Server Configuration
    # ============================================================================
    host: str = Field(default="0.0.0.0", description="Server bind host address")
    port: int = Field(default=8000, ge=1024, le=65535, description="Server bind port")
    debug: bool = Field(default=False, description="Enable debug mode (DO NOT use in production)")

    # Performance and monitoring
    enable_request_logging: bool = Field(default=True, description="Enable detailed request/response logging")
    enable_performance_metrics: bool = Field(default=True, description="Enable performance metrics collection")

    # ============================================================================
    # Tracing / Observability (OpenTelemetry)
    # ============================================================================
    enable_tracing: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing (OTLP export)",
    )

    otel_service_name: str = Field(
        default="Ms. Green",
        description="OpenTelemetry service.name resource attribute",
    )

    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description=("OTLP endpoint for exporting traces. AI Toolkit trace collector defaults to http://localhost:4318"),
    )

    # ============================================================================
    # MCP Configuration (Model Context Protocol)
    # ============================================================================
    mcp_server_url: str | None = Field(default=None, description="MCP server URL for extended bot capabilities")

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow extra fields for forward compatibility
        extra = "ignore"

    @field_validator("line_channel_secret")
    @classmethod
    def reject_placeholder_secret(cls, value: str | None) -> str | None:
        if isinstance(value, str) and value.startswith("test_"):
            raise ValueError("LINE channel secret appears to be a placeholder; set a real value in environment config")
        return value

    @field_validator("line_channel_access_token")
    @classmethod
    def reject_placeholder_token(cls, value: str | None) -> str | None:
        if isinstance(value, str) and value.startswith("test_"):
            raise ValueError("LINE channel access token appears to be a placeholder; set a real value in environment config")
        return value

    @field_validator("debug", mode="before")
    @classmethod
    def validate_debug(cls, v) -> bool:
        """Convert string values to boolean for debug field."""
        if isinstance(v, str):
            # Handle common string representations of boolean
            if v.upper() in ("TRUE", "1", "YES", "ON", "WARN"):
                return True
            elif v.upper() in ("FALSE", "0", "NO", "OFF"):
                return False
            else:
                # Default to False for unrecognized strings
                logger.warning(f"Unrecognized debug value '{v}', defaulting to False")
                return False
        return v

    @field_validator("additional_agents")
    @classmethod
    def validate_additional_agents_json(cls, v: str | None) -> str | None:
        """Validate that additional_agents is valid JSON if provided."""
        if v is None or v.strip() == "":
            return None
        try:
            json.loads(v)
            return v
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in additional_agents: {e}")
            raise ValueError(f"additional_agents must be valid JSON: {e}")

    @field_validator("persistence_backend", mode="before")
    @classmethod
    def validate_persistence_backend(cls, v: Any) -> Any:
        """Normalize and validate the structured persistence backend selection."""
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized not in {"local", "convex"}:
                raise ValueError("persistence_backend must be one of: local, convex")
            return normalized
        return v

    @field_validator("convex_deployment_url", mode="before")
    @classmethod
    def normalize_convex_deployment_url(cls, v: Any) -> Any:
        """Trim Convex deployment URLs and treat blank values as unset."""
        if isinstance(v, str):
            normalized = v.strip()
            return normalized or None
        return v

    def parse_additional_agents(self) -> dict[str, dict[str, str]]:
        """
        Parse additional agents configuration from JSON string.

        Returns:
            Dictionary mapping agent names to their configuration.
            Returns empty dict if not configured or invalid.
        """
        if not self.additional_agents:
            return {}
        try:
            agents = json.loads(self.additional_agents)
            if not isinstance(agents, dict):
                logger.error("additional_agents must be a JSON object/dict")
                return {}
            return agents
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse additional_agents: {e}")
            return {}

    def is_news_api_configured(self) -> bool:
        """Check if NewsAPI.org is properly configured."""
        return bool(self.news_api_key and len(self.news_api_key) > 10)

    def is_google_translate_configured(self) -> bool:
        """Check if the legacy Google Translate configuration is available."""
        return bool(self.google_translate_api_key and len(self.google_translate_api_key) > 10)

    def is_openrouter_configured(self) -> bool:
        """Check if OpenRouter is properly configured."""
        return bool(self.openrouter_api_key and len(self.openrouter_api_key) > 10)

    def is_brave_search_configured(self) -> bool:
        """Check if Brave Search API is properly configured."""
        return bool(self.brave_search_api_key and len(self.brave_search_api_key) > 10)

    def is_github_models_configured(self) -> bool:
        """Check if GitHub Models API is properly configured with a PAT."""
        return bool(self.github_models_pat and len(self.github_models_pat) > 10)

    def is_hermes_configured(self) -> bool:
        """Check if Hermes fallback is configured with base URL and key."""
        return bool(
            (self.hermes_base_url or "").strip()
            and (self.hermes_api_key or "").strip()
            and len((self.hermes_api_key or "").strip()) > 10
        )

    def get_fallback_llm_providers(self) -> list[str]:
        """
        Return provider order list with one highest-priority configured provider
        selected from each configured group: github / openrouter / hermes.
        """
        configured: list[str] = []
        if self.is_github_models_configured() and "github" not in configured:
            configured.append("github")
        if self.is_openrouter_configured() and "openrouter" not in configured:
            configured.append("openrouter")
        if self.is_hermes_configured() and "hermes" not in configured:
            configured.append("hermes")
        return configured or ["github", "openrouter", "hermes"]

    def get_llm_provider_priority(self) -> list[str]:
        """
        Get ordered list of LLM providers to try.

        Returns:
            List of provider names in priority order (e.g., ['github','openrouter','hermes'])
        """
        raw = (self.llm_fallback_provider_priority or "github,openrouter,hermes").strip()
        order = [p.strip().lower() for p in raw.split(",") if p.strip()]
        seen: list[str] = []
        for p in order:
            if p not in seen:
                seen.append(p)
        return seen

    def get_admin_user_ids(self) -> list[str]:
        """
        Get list of authorized admin user IDs.

        Returns:
            List of LINE user IDs authorized as admins, or empty list if none configured.
        """
        if not self.admin_user_ids:
            return []
        return [uid.strip() for uid in self.admin_user_ids.split(",") if uid.strip()]

    def get_moderator_user_ids(self) -> list[str]:
        """
        Get list of authorized moderator user IDs.

        Returns:
            List of LINE user IDs authorized as moderators, or empty list if none configured.
        """
        if not self.moderator_user_ids:
            return []
        return [uid.strip() for uid in self.moderator_user_ids.split(",") if uid.strip()]

    def get_bot_identity_default_aliases(self) -> list[str]:
        """Return configured default bot aliases as a normalized list."""
        raw = (self.bot_identity_default_aliases or "").strip()
        if not raw:
            return []
        return [alias.strip().lower() for alias in raw.split(",") if alias.strip()]

    def get_zeus_allowed_group_ids(self) -> set[str]:
        """Return allowed group/room IDs for legacy Zeus-style group access."""
        raw = (self.zeus_allowed_group_ids or "").strip()
        if not raw:
            return set()
        return {part.strip() for part in raw.split(",") if part.strip()}

    def get_allowed_group_ids(self) -> set[str]:
        """Return allowed group/room IDs for TeacherBOY AI (allowlist mode)."""
        raw = (self.zeus_allowed_group_ids or "").strip()
        if not raw:
            return set()
        return {part.strip() for part in raw.split(",") if part.strip()}

    def get_zeus_denied_group_ids(self) -> set[str]:
        """Return denied group/room IDs for legacy Zeus-style group access."""
        raw = (self.zeus_denied_group_ids or "").strip()
        if not raw:
            return set()
        return {part.strip() for part in raw.split(",") if part.strip()}

    def get_denied_group_ids(self) -> set[str]:
        """Return denied group/room IDs for TeacherBOY AI (denylist mode)."""
        raw = (self.zeus_denied_group_ids or "").strip()
        if not raw:
            return set()
        return {part.strip() for part in raw.split(",") if part.strip()}

    def is_zeus_allowed_in_group(
        self,
        group_id: str | None,
        room_id: str | None,
        user_is_admin: bool,
    ) -> bool:
        """Return True when Zeus features should be available in a group/room.

        The bot is being standardized so every group sees the same feature set.
        The parameters are kept for compatibility with older call sites, but the
        current policy is universal group access.
        """
        return True

    def is_conversation_memory_configured(self) -> bool:
        """Check if conversation memory is configured and ready for use."""
        return bool(self.conversation_memory_enabled)

    def is_document_memory_configured(self) -> bool:
        """Check if document memory is configured and ready for use."""
        return bool(self.document_memory_enabled)

    def is_history_log_configured(self) -> bool:
        """Check if history logging is configured and enabled."""
        return bool(self.history_log_enabled)

    def is_history_log_hf_configured(self) -> bool:
        """Check if HF Hub backup for history logs is configured."""
        return bool(self.history_log_enabled and self.hf_memory_token and self.history_log_hf_repo_id)

    def is_profiler_configured(self) -> bool:
        """Check if the psychological profiler feature is enabled."""
        return bool(self.profiler_enabled)

    def is_calendar_configured(self) -> bool:
        """Check if calendar feature is enabled."""
        return bool(self.calendar_enabled)

    def is_calendar_hf_configured(self) -> bool:
        """Check if HF Hub backup for calendar is configured."""
        return bool(
            self.calendar_enabled
            and self.hf_memory_token  # Reuse memory token
            and self.calendar_hf_repo_id
        )

    def is_google_calendar_configured(self) -> bool:
        """Check if Google Calendar integration is enabled and configured."""
        return bool(self.google_calendar_enabled and os.path.exists(self.google_calendar_credentials_file))

    def is_convex_configured(self) -> bool:
        """Check if Convex structured persistence is configured."""
        return bool(self.convex_deployment_url and (self.convex_sync_token or "").strip())

    def is_convex_primary_backend(self) -> bool:
        """Check if Convex is the selected primary persistence backend."""
        return self.persistence_backend == "convex"

    def get_mcp_server_url(self) -> str | None:
        url = (self.mcp_server_url or "").strip()
        return url or None

    def get_http_client_config(self) -> dict[str, Any]:
        """
        Get HTTP client configuration for httpx.AsyncClient.

        Returns:
            Dictionary with httpx client configuration parameters.
        """
        return {
            "timeout": self.http_client_timeout_seconds,
            "limits": {
                "max_connections": self.http_client_max_connections,
                "max_keepalive_connections": self.http_client_max_keepalive,
            },
            "http2": True,  # Enable HTTP/2 for better performance
        }


# Global settings instance
settings = Settings()
