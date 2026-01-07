"""
Application configuration and settings management.

This module provides type-safe, validated configuration for the Zeus application,
following production best practices for environment-based configuration management.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, HttpUrl, AliasChoices
from typing import Optional, Dict, Any
import json
import logging
import os

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Production-grade application settings with comprehensive validation.

    All settings are loaded from environment variables with sensible defaults.
    Critical settings are validated at startup to fail fast on misconfiguration.
    """

    # ============================================================================
    # LINE Bot Configuration - Primary Agent (Zeus)
    # ============================================================================
    line_channel_secret: str = Field(
        default="test_secret_for_testing_only",
        description="LINE Bot channel secret for webhook signature verification",
        min_length=10,
    )
    line_channel_access_token: str = Field(
        default="test_token_for_testing_only",
        description="LINE Bot channel access token for API authentication",
        min_length=10,
    )

    # ============================================================================
    # Multi-Agent Configuration (Optional)
    # ============================================================================
    additional_agents: Optional[str] = Field(
        default=None, description="JSON string with additional agent configurations"
    )

    # ============================================================================
    # Admin Control Configuration
    # ============================================================================
    admin_user_ids: Optional[str] = Field(
        default=None, 
        description="Comma-separated list of LINE user IDs authorized as admins"
    )

    admin_setup_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional one-time admin bootstrap key. If set, a user can run '/admin claim <key>' "
            "to reveal their LINE user ID and become an in-memory admin for the current process."
        ),
    )

    moderator_user_ids: Optional[str] = Field(
        default=None,
        description="Comma-separated list of LINE user IDs authorized as moderators (can access news directly)"
    )

    # ============================================================================
    # Translation Service Configuration
    # ============================================================================

    # Google Cloud Translation API (Primary - Professional Grade)
    google_translate_api_key: Optional[str] = Field(
        default=None,
        description="Google Cloud Translation API key for high-quality translation",
    )

    # LibreTranslate API (Fallback/Development)
    libretranslate_api_url: str = Field(
        default="https://libretranslate.com/translate",
        description="LibreTranslate API endpoint URL",
    )
    libretranslate_api_key: Optional[str] = Field(
        default=None,
        description="LibreTranslate API key (optional, for rate limit increases)",
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

    # ============================================================================
    # News Agent Configuration
    # ============================================================================
    news_api_key: Optional[str] = Field(
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
    exchange_rate_api_key: Optional[str] = Field(
        default=None,
        description="ExchangeRate-API key for currency conversion (optional; 1500 req/mo free)",
    )
    tat_api_key: Optional[str] = Field(
        default=None,
        description="Tourism Authority of Thailand (TAT) API key for events/festivals",
    )

    # ============================================================================
    # OpenRouter Configuration (LLM)
    # ============================================================================
    openrouter_api_key: Optional[str] = Field(
        default=None,
        description="OpenRouter API key for LLM access",
    )
    openrouter_default_model: str = Field(
        default="google/gemma-2-9b-it",
        description="Default model to use for OpenRouter (must be a free model)",
        validation_alias=AliasChoices("OPENROUTER_DEFAULT_MODEL", "DEFAULT_MODEL"),
    )

    llm_system_prompt: str = Field(
        default=(
            "You are Zeus, king of the Olympian gods. Your tone is wise, measured, and authoritative, "
            "yet you carry the warmth of a benevolent ruler who cares for those who seek your counsel. "
            "Be direct and insightful, but not cold. A touch of paternal wisdom is welcome. "
            "Keep answers concise. Light mythological references are fine when they add value."
        ),
        description=(
            "System prompt for the LLM agent (OpenRouter). Controls the bot's personality/tone with mythological depth."
        ),
    )

    llm_temperature: float = Field(
        default=1.15,
        ge=0.0,
        le=2.0,
        description="LLM temperature ('warmth') for Zeus responses (0-2). Higher = more creative/warm.",
    )

    # Zeus AI access control (group/room). Private chats are always allowed.
    zeus_group_access_mode: str = Field(
        default="all",
        description=(
            "Group/room access mode for Zeus AI commands. "
            "Options: 'all' (default), 'allowlist', 'denylist'."
        ),
    )
    zeus_allowed_group_ids: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated list of allowed group_id/room_id values for Zeus when "
            "ZEUS_GROUP_ACCESS_MODE=allowlist. Example: 'C123,R456'."
        ),
    )
    zeus_denied_group_ids: Optional[str] = Field(
        default=None,
        description=(
            "Comma-separated list of denied group_id/room_id values for Zeus when "
            "ZEUS_GROUP_ACCESS_MODE=denylist. Example: 'C123,R456'."
        ),
    )

    # ============================================================================
    # Search Agent Configuration
    # ============================================================================
    brave_search_api_key: Optional[str] = Field(
        default=None,
        description="Brave Search API key for web search capabilities",
    )

    # ============================================================================
    # Conversation Memory Configuration (HF Hub Persistence)
    # ============================================================================
    hf_memory_token: Optional[str] = Field(
        default=None,
        description=(
            "Hugging Face API token for conversation memory persistence. "
            "Create at https://huggingface.co/settings/tokens with 'write' scope."
        ),
    )
    hf_memory_repo_id: Optional[str] = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for storing conversation memory. "
            "Example: 'username/zeus-memory'. Will be created as private if it doesn't exist."
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
    history_log_encryption_key: Optional[str] = Field(
        default=None,
        description=(
            "Optional encryption key for sensitive log data. "
            "When set, logs are encrypted using AES (requires 'cryptography' package)."
        ),
    )
    history_log_hf_repo_id: Optional[str] = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for cloud log backup. "
            "Example: 'username/zeus-logs'. Will be created as private if it doesn't exist."
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
        description="Format error messages in Zeus's mythological, authoritative style.",
    )

    # ============================================================================
    # GitHub Models Configuration (Alternative to OpenRouter)
    # ============================================================================
    github_models_pat: Optional[str] = Field(
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
        default="github,openrouter",
        description=(
            "Comma-separated priority list for LLM providers. "
            "Options: 'github', 'openrouter'. First configured provider is used."
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
        description="Local directory for storing calendar data.",
    )
    calendar_hf_repo_id: Optional[str] = Field(
        default=None,
        description=(
            "Hugging Face dataset repo ID for calendar data backup. "
            "Example: 'username/zeus-calendar'. Uses hf_memory_token for auth."
        ),
    )
    calendar_sync_interval_seconds: int = Field(
        default=300,
        ge=60,
        le=3600,
        description="Interval in seconds for syncing calendar to HF Hub (default: 5 minutes).",
    )

    # ============================================================================
    # HTTP Client Configuration
    # ============================================================================
    http_client_timeout_seconds: int = Field(
        default=30, ge=5, le=300, description="HTTP client timeout in seconds"
    )
    http_client_max_connections: int = Field(
        default=100, ge=10, le=1000, description="Maximum concurrent HTTP connections"
    )
    http_client_max_keepalive: int = Field(
        default=20, ge=5, le=100, description="Maximum keep-alive connections"
    )

    # ============================================================================
    # Server Configuration
    # ============================================================================
    host: str = Field(default="0.0.0.0", description="Server bind host address")
    port: int = Field(default=8000, ge=1024, le=65535, description="Server bind port")
    debug: bool = Field(
        default=False, description="Enable debug mode (DO NOT use in production)"
    )

    # Performance and monitoring
    enable_request_logging: bool = Field(
        default=True, description="Enable detailed request/response logging"
    )
    enable_performance_metrics: bool = Field(
        default=True, description="Enable performance metrics collection"
    )

    # ============================================================================
    # Tracing / Observability (OpenTelemetry)
    # ============================================================================
    enable_tracing: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing (OTLP export)",
    )

    otel_service_name: str = Field(
        default="Zeus",
        description="OpenTelemetry service.name resource attribute",
    )

    otel_exporter_otlp_endpoint: str = Field(
        default="http://localhost:4318",
        description=(
            "OTLP endpoint for exporting traces. AI Toolkit trace collector defaults to http://localhost:4318"
        ),
    )

    # ============================================================================
    # MCP Configuration (Model Context Protocol)
    # ============================================================================
    mcp_server_url: Optional[str] = Field(
        default=None, description="MCP server URL for extended bot capabilities"
    )

    class Config:
        env_file = ".env"
        case_sensitive = False
        # Allow extra fields for forward compatibility
        extra = "ignore"

    @field_validator("debug", mode='before')
    @classmethod
    def validate_debug(cls, v) -> bool:
        """Convert string values to boolean for debug field."""
        if isinstance(v, str):
            # Handle common string representations of boolean
            if v.upper() in ('TRUE', '1', 'YES', 'ON', 'WARN'):
                return True
            elif v.upper() in ('FALSE', '0', 'NO', 'OFF'):
                return False
            else:
                # Default to False for unrecognized strings
                logger.warning(f"Unrecognized debug value '{v}', defaulting to False")
                return False
        return v

    @field_validator("additional_agents")
    @classmethod
    def validate_additional_agents_json(cls, v: Optional[str]) -> Optional[str]:
        """Validate that additional_agents is valid JSON if provided."""
        if v is None or v.strip() == "":
            return None
        try:
            json.loads(v)
            return v
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in additional_agents: {e}")
            raise ValueError(f"additional_agents must be valid JSON: {e}")

    def parse_additional_agents(self) -> Dict[str, Dict[str, str]]:
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

    def is_google_translate_configured(self) -> bool:
        """Check if Google Translate API is properly configured."""
        return bool(
            self.google_translate_api_key and len(self.google_translate_api_key) > 20
        )

    def is_news_api_configured(self) -> bool:
        """Check if NewsAPI.org is properly configured."""
        return bool(self.news_api_key and len(self.news_api_key) > 10)

    def is_openrouter_configured(self) -> bool:
        """Check if OpenRouter is properly configured."""
        return bool(self.openrouter_api_key and len(self.openrouter_api_key) > 10)

    def is_brave_search_configured(self) -> bool:
        """Check if Brave Search API is properly configured."""
        return bool(self.brave_search_api_key and len(self.brave_search_api_key) > 10)

    def is_github_models_configured(self) -> bool:
        """Check if GitHub Models API is properly configured with a PAT."""
        return bool(self.github_models_pat and len(self.github_models_pat) > 10)

    def is_profiler_configured(self) -> bool:
        """Check if Psychological Profiler feature is enabled and vision AI is available."""
        return bool(
            self.profiler_enabled
            and self.is_github_models_configured()  # Vision requires GitHub Models
        )

    def is_conversation_memory_configured(self) -> bool:
        """Check if Hugging Face conversation memory storage is configured."""
        return bool(
            self.conversation_memory_enabled
            and self.hf_memory_token
            and self.hf_memory_repo_id
            and len(self.hf_memory_token) > 10
        )

    def is_history_log_configured(self) -> bool:
        """Check if history logging is enabled and configured."""
        return bool(self.history_log_enabled)

    def is_history_log_hf_configured(self) -> bool:
        """Check if HF Hub backup for history logs is configured."""
        return bool(
            self.history_log_enabled
            and self.hf_memory_token  # Reuse memory token
            and self.history_log_hf_repo_id
        )

    def get_llm_provider_priority(self) -> list[str]:
        """
        Get ordered list of LLM providers to try.
        
        Returns:
            List of provider names in priority order (e.g., ['github', 'openrouter'])
        """
        if not self.llm_provider_priority:
            return ["github", "openrouter"]
        return [p.strip().lower() for p in self.llm_provider_priority.split(",") if p.strip()]

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

    def get_zeus_allowed_group_ids(self) -> set[str]:
        """Return allowed group/room IDs for Zeus AI (allowlist mode)."""
        raw = (self.zeus_allowed_group_ids or "").strip()
        if not raw:
            return set()
        return {part.strip() for part in raw.split(",") if part.strip()}

    def get_zeus_denied_group_ids(self) -> set[str]:
        """Return denied group/room IDs for Zeus AI (denylist mode)."""
        raw = (self.zeus_denied_group_ids or "").strip()
        if not raw:
            return set()
        return {part.strip() for part in raw.split(",") if part.strip()}

    def is_zeus_allowed_in_group(
        self,
        group_id: Optional[str],
        room_id: Optional[str],
        user_is_admin: bool,
    ) -> bool:
        """Return True if Zeus AI is allowed in this group/room for this user.

        Notes:
        - Admins always bypass restrictions.
        - Private chats are handled elsewhere; this is for group/room contexts.
        """
        if user_is_admin:
            return True

        chat_id = (group_id or room_id or "").strip()
        mode = (self.zeus_group_access_mode or "all").strip().lower()

        if mode == "allowlist":
            allowed = self.get_zeus_allowed_group_ids()
            return bool(chat_id) and chat_id in allowed

        if mode == "denylist":
            denied = self.get_zeus_denied_group_ids()
            return not (bool(chat_id) and chat_id in denied)

        # Default: allow everywhere.
        return True

    def get_named_user_ids(self, prefix: str = "USER_") -> Dict[str, str]:
        """Return a mapping of user aliases to LINE user IDs from environment variables.

        This supports admin-safe outbound messaging to known recipients.

        Format:
            USER_<ALIAS>=<LINE_USER_ID>

        Example:
            USER_BOSS=U1234567890abcdef

        Notes:
        - Aliases are stored case-insensitively (lowercased).
        - Values are trimmed and may be quoted.
        - Only variables with names starting with the prefix are considered.
        """
        result: Dict[str, str] = {}
        for key, value in os.environ.items():
            if not key.startswith(prefix):
                continue

            alias = key[len(prefix) :].strip()
            if not alias:
                continue

            user_id = (value or "").strip().strip("\"'")
            if not user_id:
                continue

            result[alias.lower()] = user_id

        return result

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

    def get_http_client_config(self) -> Dict[str, Any]:
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
