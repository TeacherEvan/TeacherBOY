from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # LINE Bot Configuration
    line_channel_secret: str
    line_channel_access_token: str
    
    # LibreTranslate API Configuration
    libretranslate_api_url: str = "https://libretranslate.de/translate"
    libretranslate_api_key: Optional[str] = None
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False
    
    # MCP Configuration
    mcp_server_url: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
