"""Prefect tasks for document processing."""

from .document_tasks import (
    ocr_task,
    classify_task,
    summarize_task,
    score_classification_task,
    score_summary_task,
    file_task,
    generate_file_summary_task
)

__all__ = [
    'ocr_task',
    'classify_task',
    'summarize_task',
    'score_classification_task',
    'score_summary_task',
    'file_task',
    'generate_file_summary_task'
]