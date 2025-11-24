"""Shared type definitions for esec Document Secretary."""

from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from uuid import UUID


class DocumentStatus(str, Enum):
    """Document processing status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class DocumentCategory(str, Enum):
    """Document categories."""
    BILL = "bill"
    TAX = "tax"
    RECEIPT = "receipt"
    INSURANCE = "insurance"
    ADVERTISING = "advertising"
    OTHER = "other"


class DocumentMetadata(BaseModel):
    """Document metadata model."""
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    category: Optional[DocumentCategory] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    created_at: datetime


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