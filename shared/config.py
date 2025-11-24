"""Shared configuration module using pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # API Keys
    claude_api_key: str = ""
    openrouter_api_key: str = ""
    
    # Paths - default to ./data for local development
    database_path: Path = Path("./data/esec.db")
    inbox_path: Path = Path("./data/inbox")
    documents_path: Path = Path("./data/documents")
    summaries_path: Path = Path("./data/summaries")
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    mcp_port: int = 3000
    
    # Logging
    log_level: str = "INFO"
    env: str = "development"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )