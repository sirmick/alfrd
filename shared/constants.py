"""Shared constants for esec."""

from typing import Set

# Supported file types
SUPPORTED_IMAGE_TYPES: Set[str] = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORTED_DOCUMENT_TYPES: Set[str] = {".pdf"}
SUPPORTED_FILE_TYPES: Set[str] = SUPPORTED_IMAGE_TYPES | SUPPORTED_DOCUMENT_TYPES

# File size limits
MAX_FILE_SIZE: int = 50 * 1024 * 1024  # 50MB

# Database
DEFAULT_DB_PATH: str = "/data/esec.db"

# Directories
DEFAULT_INBOX_PATH: str = "/data/inbox"
DEFAULT_DOCUMENTS_PATH: str = "/data/documents"
DEFAULT_SUMMARIES_PATH: str = "/data/summaries"

# API
DEFAULT_API_HOST: str = "0.0.0.0"
DEFAULT_API_PORT: int = 8000
DEFAULT_MCP_PORT: int = 3000

# Processing
DEBOUNCE_SECONDS: float = 1.0  # Wait time after file creation
BATCH_SIZE: int = 10  # Number of documents to process in batch

# LLM
DEFAULT_MODEL: str = "claude-3-5-sonnet-20241022"
MAX_TOKENS: int = 4096
TEMPERATURE: float = 0.0  # Deterministic for extraction tasks