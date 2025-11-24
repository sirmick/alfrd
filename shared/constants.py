"""Shared constants for ALFRD (Automated Ledger & Filing Research Database)."""

# Supported file types
SUPPORTED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp"}
SUPPORTED_TEXT_TYPES = {".txt", ".text"}
ALL_SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | SUPPORTED_TEXT_TYPES

# File size limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB for Textract

# MIME type mappings
MIME_TYPE_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".bmp": "image/bmp",
    ".txt": "text/plain",
    ".text": "text/plain"
}

# AWS Textract
TEXTRACT_MAX_SIZE = 10 * 1024 * 1024  # 10MB max for Textract
TEXTRACT_TIMEOUT = 60  # seconds

# AWS Bedrock
BEDROCK_MODEL_ID = "anthropic.claude-3-5-sonnet-20241022-v2:0"
BEDROCK_REGION = "us-east-1"
BEDROCK_MAX_TOKENS = 4096

# Processing timeouts
OCR_TIMEOUT = 60  # seconds
MCP_TIMEOUT = 30  # seconds
EVENT_TIMEOUT = 10  # seconds

# Database
DB_CONNECTION_TIMEOUT = 5  # seconds

# Document storage
DOCUMENT_DATE_FORMAT = "%Y/%m"  # Year/Month directory structure
META_JSON_FILENAME = "meta.json"

# Debouncing
DEBOUNCE_SECONDS = 1  # Wait between processing files