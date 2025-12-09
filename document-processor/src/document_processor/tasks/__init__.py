"""Simple asyncio tasks for document processing."""

from .document_tasks import (
    ocr_step,
    classify_step,
    summarize_step,
    score_classification_step,
    score_summary_step,
    file_step,
    generate_file_summary_step
)

__all__ = [
    'ocr_step',
    'classify_step',
    'summarize_step',
    'score_classification_step',
    'score_summary_step',
    'file_step',
    'generate_file_summary_step'
]