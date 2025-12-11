"""
Application configuration and settings management.

This module provides type-safe, validated configuration for the TeacherBOY application,
following production best practices for environment-based configuration management.
"""

from pydantic_settings import BaseSettings
from pydantic import Field, field_validator, HttpUrl
from typing import Optional, Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Production-grade application settings with comprehensive validation.

    All settings are loaded from environment variables with sensible defaults.
    Critical settings are validated at startup to fail fast on misconfiguration.
    """

    # ============================================================================
    # LINE Bot Configuration - Primary Agent (TeacherBOY)
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
    # Translation Service Configuration
    # ============================================================================

    # Google Cloud Translation API (Primary - Professional Grade)
    google_translate_api_key: Optional[str] = Field(
        default=None, description="Google Cloud Translation API key for high-quality translation"
    )

    # LibreTranslate API (Fallback/Development)
    libretranslate_api_url: str = Field(
        default="https://libretranslate.de/translate", description="LibreTranslate API endpoint URL"
    )
    libretranslate_api_key: Optional[str] = Field(
        default=None, description="LibreTranslate API key (optional, for rate limit increases)"
    )

    # Translation Performance Optimization
    # NOTE: Caching implementation is planned for future release
    translation_cache_ttl_seconds: int = Field(
        default=3600, ge=0, description="TTL for translation cache in seconds (0 to disable) - TODO"
    )
    translation_max_retries: int = Field(
        default=3, ge=0, le=10, description="Maximum retry attempts for failed translation requests"
    )

    # ============================================================================
    # Google Calendar Integration
    # ============================================================================
    google_calendar_group_id: Optional[str] = Field(
        default=None, description="LINE Group Chat ID for calendar reminders"
    )
    calendar_timezone: str = Field(
        default="Asia/Bangkok", description="Timezone for scheduled reminders (IANA format)"
    )
    calendar_morning_hour: int = Field(
        default=7, ge=0, le=23, description="Hour for morning reminder (24-hour format)"
    )
    calendar_afternoon_hour: int = Field(
        default=14, ge=0, le=23, description="Hour for afternoon reminder (24-hour format)"
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
    debug: bool = Field(default=False, description="Enable debug mode (DO NOT use in production)")

    # Performance and monitoring
    enable_request_logging: bool = Field(
        default=True, description="Enable detailed request/response logging"
    )
    enable_performance_metrics: bool = Field(
        default=True, description="Enable performance metrics collection"
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

    @field_validator("calendar_timezone")
    @classmethod
    def validate_timezone(cls, v: str) -> str:
        """Validate that timezone is a valid IANA timezone string."""
        try:
            import pytz

            pytz.timezone(v)
            return v
        except Exception as e:
            logger.warning(f"Invalid timezone '{v}', falling back to Asia/Bangkok: {e}")
            return "Asia/Bangkok"

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
        return bool(self.google_translate_api_key and len(self.google_translate_api_key) > 20)

    def is_calendar_configured(self) -> bool:
        """Check if Google Calendar integration is properly configured."""
        return bool(self.google_calendar_group_id)

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
