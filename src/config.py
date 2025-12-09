from pydantic_settings import BaseSettings
from typing import Optional, Dict, Any
import json


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # LINE Bot Configuration - Primary Agent (Brown)
    line_channel_secret: str
    line_channel_access_token: str

    # Additional Agents Configuration (JSON format)
    # Format: {"agent_name": {"channel_secret": "...", "channel_access_token": "..."}}
    additional_agents: Optional[str] = None

    # LibreTranslate API Configuration (Fallback)
    libretranslate_api_url: str = "https://libretranslate.de/translate"
    libretranslate_api_key: Optional[str] = None

    # Google Cloud Translation API (Primary - Higher Quality)
    google_translate_api_key: Optional[str] = None

    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # MCP Configuration
    mcp_server_url: Optional[str] = None

    class Config:
        env_file = ".env"
        case_sensitive = False

    def get_additional_agents(self) -> Dict[str, Dict[str, str]]:
        """Parse additional agents from JSON string."""
        if not self.additional_agents:
            return {}
        try:
            return json.loads(self.additional_agents)
        except json.JSONDecodeError:
            return {}


settings = Settings()
