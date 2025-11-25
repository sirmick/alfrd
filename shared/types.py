"""Shared type definitions for ALFRD (Automated Ledger & Filing Research Database)."""

from enum import Enum
from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class DocumentStatus(str, Enum):
    """Document processing status - tracks pipeline progress."""
    PENDING = "pending"                         # Document folder detected
    OCR_STARTED = "ocr_started"                 # AWS Textract called
    OCR_COMPLETED = "ocr_completed"             # Text extracted
    CLASSIFYING = "classifying"                 # MCP classification in progress
    CLASSIFIED = "classified"                   # Type determined
    SCORING_CLASSIFICATION = "scoring_classification"  # Scoring classifier performance
    SCORED_CLASSIFICATION = "scored_classification"    # Classifier scored and prompt updated
    SUMMARIZING = "summarizing"                 # Generating summary
    SUMMARIZED = "summarized"                   # Summary generated
    SCORING_SUMMARY = "scoring_summary"         # Scoring summarizer performance
    COMPLETED = "completed"                     # All processing done
    FAILED = "failed"                           # Error at any stage


class DocumentType(str, Enum):
    """Document type classification (simplified)."""
    JUNK = "junk"           # Advertising, promotional materials
    BILL = "bill"           # Utility bills, service invoices
    FINANCE = "finance"     # Tax documents, bank statements, financial records


class DocumentCategory(str, Enum):
    """Document categories (legacy - keeping for compatibility)."""
    BILL = "bill"
    TAX = "tax"
    RECEIPT = "receipt"
    INSURANCE = "insurance"
    ADVERTISING = "advertising"
    OTHER = "other"


class DocumentFolderMeta(BaseModel):
    """Metadata from meta.json in document folder."""
    id: str
    created_at: datetime
    documents: List[Dict[str, Any]]  # List of {file, type, order}
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    document_type: Optional[DocumentType] = None  # Classifier result
    category: Optional[DocumentCategory] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    created_at: datetime
    classification_confidence: Optional[float] = None


class ClassificationResult(BaseModel):
    """Result from MCP document classification."""
    document_type: str  # Changed from DocumentType to allow dynamic types
    confidence: float
    reasoning: str
    suggested_type: Optional[str] = None  # New type suggestion if applicable
    secondary_tags: List[str] = Field(default_factory=list)  # Secondary classification tags


class PromptType(str, Enum):
    """Types of prompts stored in the database."""
    CLASSIFIER = "classifier"
    SUMMARIZER = "summarizer"


class PromptRecord(BaseModel):
    """Database record for a prompt."""
    id: str
    prompt_type: PromptType
    document_type: Optional[str] = None  # NULL for classifier, specific for summarizers
    prompt_text: str
    version: int = 1
    performance_score: Optional[float] = None
    performance_metrics: Optional[Dict[str, Any]] = None
    created_at: datetime
    updated_at: datetime
    is_active: bool = True
    user_id: Optional[str] = None


class ClassificationSuggestion(BaseModel):
    """Suggestion for a new document type."""
    id: str
    suggested_type: str
    document_id: Optional[str] = None
    confidence: float
    reasoning: str
    approved: bool = False
    reviewed_at: Optional[datetime] = None
    created_at: datetime
    user_id: Optional[str] = None


class ScoringResult(BaseModel):
    """Result from scoring a prompt's performance."""
    score: float  # 0.0 to 1.0
    feedback: str
    suggested_improvements: str
    metrics: Dict[str, Any] = Field(default_factory=dict)


class EventType(str, Enum):
    """Processing event types."""
    DOCUMENT_ADDED = "document_added"
    OCR_STARTED = "ocr_started"
    OCR_COMPLETED = "ocr_completed"
    OCR_FAILED = "ocr_failed"
    DOCUMENT_PROCESSED = "document_processed"
    CATEGORIZATION_COMPLETED = "categorization_completed"
    EXTRACTION_COMPLETED = "extraction_completed"
    SUMMARY_GENERATED = "summary_generated"
    ERROR = "error"


class PeriodType(str, Enum):
    """Summary period types."""
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"