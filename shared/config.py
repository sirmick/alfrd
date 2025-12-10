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
    
    # Database Configuration (PostgreSQL)
    # Unix socket connection (preferred for local dev): postgresql://user@/dbname?host=/var/run/postgresql
    # TCP connection: postgresql://user:password@host:port/dbname
    database_url: str = "postgresql://alfrd_user@/alfrd?host=/var/run/postgresql"
    postgres_password: str = "alfrd_dev_password"
    
    # Connection Pool Settings
    db_pool_min_size: int = 5
    db_pool_max_size: int = 20
    db_pool_timeout: float = 30.0  # seconds
    
    # Legacy paths - keeping for backward compatibility
    database_path: Path = Path("./data/alfrd.db")  # DuckDB (deprecated)
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
    
    # Prefect Worker Pool Configuration
    # Max concurrent document processing flows
    prefect_max_document_flows: int = 5
    
    # Max concurrent file generation flows
    prefect_max_file_flows: int = 2
    
    # Task-level concurrency limits (asyncio semaphores)
    prefect_textract_workers: int = 3  # AWS Textract API calls
    prefect_bedrock_workers: int = 5   # AWS Bedrock API calls
    prefect_file_generation_workers: int = 2  # File summary generation
    
    # ThreadPoolExecutor max workers (for blocking I/O operations)
    prefect_max_threads: int = 2  # Max threads for synchronous LLM calls
    
    # Legacy Worker Pool Configuration (deprecated - kept for compatibility)
    # OCR workers (AWS Textract concurrency limit)
    ocr_workers: int = 3
    ocr_poll_interval: int = 5  # seconds
    
    # Classifier workers (Bedrock API concurrency limit)
    classifier_workers: int = 5
    classifier_poll_interval: int = 3  # seconds
    
    # Classifier scorer workers (evaluate classification quality)
    classifier_scorer_workers: int = 3
    classifier_scorer_poll_interval: int = 5  # seconds
    
    # Summarizer workers (document-specific summarization)
    summarizer_workers: int = 3
    summarizer_poll_interval: int = 3  # seconds
    
    # Summarizer scorer workers (evaluate summary quality)
    summarizer_scorer_workers: int = 2
    summarizer_scorer_poll_interval: int = 5  # seconds
    
    # Filing workers (create LLM files based on tags)
    filing_workers: int = 3
    filing_poll_interval: int = 2  # seconds
    
    # Worker batch sizes (documents to fetch per poll)
    worker_batch_multiplier: int = 2  # batch_size = workers * multiplier
    
    # Prompt Evolution Configuration
    classifier_prompt_max_words: int = 300  # Max words for classifier prompt
    min_documents_for_scoring: int = 1  # Min documents before scoring prompts (set to 1 for testing)
    prompt_update_threshold: float = 999.0  # Min score improvement to update prompt (set to 999 to disable evolution during testing)
    
    # Recovery Configuration
    stale_timeout_minutes: int = 30  # How long before considering work stale/stuck
    recovery_check_interval_minutes: int = 5  # How often to run recovery check (periodic heartbeat)
    max_document_retries: int = 3  # Max retry attempts before marking permanently_failed
    max_file_retries: int = 3  # Max retry attempts for file generation
    
    # AWS API Caching Configuration
    aws_cache_enabled: bool = True  # Enable request caching to save money during testing
    aws_cache_max_size: int = 1000  # Maximum number of cached requests
    
    # Logging
    log_level: str = "INFO"
    env: str = "development"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"  # Allow extra env vars (like PYTHONUNBUFFERED)
    )