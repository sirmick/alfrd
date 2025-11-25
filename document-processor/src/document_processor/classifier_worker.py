"""Classifier Worker - Classifies documents using MCP classify_document tool."""

import asyncio
import logging
from pathlib import Path
from typing import List
import sys
import duckdb

# Add parent directories to path for standalone execution
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))  # MCP server source

from shared.config import Settings
from shared.types import DocumentStatus
from document_processor.workers import BaseWorker

# Import MCP tools
from mcp_server.llm.bedrock import BedrockClient
from mcp_server.tools.classify_document import classify_document_with_retry

logger = logging.getLogger(__name__)


class ClassifierWorker(BaseWorker):
    """Worker that classifies documents in 'ocr_completed' status using MCP."""
    
    def __init__(self, settings: Settings):
        """
        Initialize Classifier worker.
        
        Args:
            settings: Application settings
        """
        super().__init__(
            settings=settings,
            worker_name="Classifier Worker",
            source_status=DocumentStatus.OCR_COMPLETED,
            target_status=DocumentStatus.CLASSIFIED,
            concurrency=settings.classifier_workers,
            poll_interval=settings.classifier_poll_interval,
        )
        
        # Initialize Bedrock client for MCP tools
        self.bedrock_client = BedrockClient()
        logger.info("Initialized Bedrock client for classification")
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'ocr_completed' status.
        
        Args:
            status: Document status to query (DocumentStatus.OCR_COMPLETED)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            results = conn.execute("""
                SELECT id, filename, extracted_text
                FROM documents
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT ?
            """, [status.value, limit]).fetchall()
            
            documents = []
            for row in results:
                documents.append({
                    "id": row[0],
                    "filename": row[1],
                    "extracted_text": row[2],
                })
            
            return documents
        finally:
            conn.close()
    
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document: classify using MCP.
        
        This uses the MCP classify_document tool to determine document type.
        
        Args:
            document: Document dictionary with id, filename, extracted_text
            
        Returns:
            True if classification succeeded
            
        Raises:
            Exception: If classification fails
        """
        doc_id = document["id"]
        filename = document["filename"]
        extracted_text = document["extracted_text"]
        
        logger.info(f"Classifying document {doc_id}: {filename}")
        
        if not extracted_text:
            raise ValueError(f"No extracted text for document {doc_id}")
        
        try:
            # Update status to classifying
            await self.update_status(doc_id, DocumentStatus.CLASSIFYING)
            
            # Call MCP classify_document tool
            # Note: We run the sync function in thread pool to not block async loop
            loop = asyncio.get_event_loop()
            classification = await loop.run_in_executor(
                None,
                classify_document_with_retry,
                extracted_text,
                filename,
                self.bedrock_client
            )
            
            # Update database with classification results
            conn = duckdb.connect(str(self.settings.database_path))
            try:
                from datetime import datetime
                
                conn.execute("""
                    UPDATE documents 
                    SET document_type = ?,
                        classification_confidence = ?,
                        classification_reasoning = ?,
                        updated_at = ?
                    WHERE id = ?
                """, [
                    classification.document_type.value,
                    classification.confidence,
                    classification.reasoning,
                    datetime.utcnow(),
                    doc_id
                ])
                
                logger.info(
                    f"Classification complete for {doc_id}: "
                    f"type={classification.document_type.value}, "
                    f"confidence={classification.confidence:.2%}"
                )
            finally:
                conn.close()
            
            # Update status to classified
            await self.update_status(doc_id, DocumentStatus.CLASSIFIED)
            
            return True
            
        except Exception as e:
            logger.error(f"Classification failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise