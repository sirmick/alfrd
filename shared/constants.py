"""Shared constants for esec Document Secretary."""

# Supported file types
SUPPORTED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORTED_DOCUMENT_TYPES = {".pdf"}
ALL_SUPPORTED_TYPES = SUPPORTED_IMAGE_TYPES | SUPPORTED_DOCUMENT_TYPES

# File size limits
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
MAX_IMAGE_SIZE = 20 * 1024 * 1024  # 20MB
MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB

# MIME type mappings
MIME_TYPE_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".pdf": "application/pdf"
}

# Claude Vision API
CLAUDE_VISION_MODEL = "claude-3-5-sonnet-20241022"
CLAUDE_MAX_TOKENS = 4096

# Processing timeouts
OCR_TIMEOUT = 60  # seconds
MCP_TIMEOUT = 30  # seconds
EVENT_TIMEOUT = 10  # seconds

# Database
DB_CONNECTION_TIMEOUT = 5  # seconds

# Document storage
DOCUMENT_DATE_FORMAT = "%Y/%m"  # Year/Month directory structure