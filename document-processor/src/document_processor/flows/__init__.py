"""Prefect flows for document processing."""

from .document_flow import process_document_flow
from .file_flow import generate_file_summary_flow

__all__ = [
    'process_document_flow',
    'generate_file_summary_flow'
]