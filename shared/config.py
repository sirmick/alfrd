"""Shared configuration module using pydantic-settings."""

from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # AWS Credentials
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    aws_region: str = "us-east-1"
    
    # API Keys (legacy - keeping for compatibility)
    claude_api_key: str = ""
    openrouter_api_key: str = ""
    
    # Paths - default to ./data for local development
    database_path: Path = Path("./data/alfrd.db")
    inbox_path: Path = Path("./data/inbox")
    documents_path: Path = Path("./data/documents")
    summaries_path: Path = Path("./data/summaries")
    exports_path: Path = Path("./data/exports")
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    mcp_port: int = 3000
    
    # Bedrock Configuration
    # bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"  # Requires authorization
    bedrock_model_id: str = "us.amazon.nova-lite-v1:0"  # Using Nova Lite inference profile
    bedrock_max_tokens: int = 4096
    
    # Logging
    log_level: str = "INFO"
    env: str = "development"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )