"""Classifier Worker - Classifies documents using DB-stored prompts and MCP."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional
import sys
import duckdb
import json
from uuid import uuid4
from datetime import datetime

# Add parent directories to path for standalone execution
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))  # MCP server source

from shared.config import Settings
from shared.types import DocumentStatus, PromptType
from document_processor.workers import BaseWorker

# Import MCP tools
from mcp_server.llm.bedrock import BedrockClient
from mcp_server.tools.classify_dynamic import classify_document_dynamic

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
        
        # Cache for active classifier prompt
        self._active_prompt: Optional[dict] = None
        self._known_types: Optional[List[str]] = None
    
    def _get_active_prompt(self) -> dict:
        """Get the active classifier prompt from database."""
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            result = conn.execute("""
                SELECT id, prompt_text, version, performance_score
                FROM prompts
                WHERE prompt_type = ?
                  AND document_type IS NULL
                  AND is_active = true
                ORDER BY version DESC
                LIMIT 1
            """, [PromptType.CLASSIFIER.value]).fetchone()
            
            if not result:
                raise ValueError("No active classifier prompt found in database")
            
            return {
                "id": result[0],
                "prompt_text": result[1],
                "version": result[2],
                "performance_score": result[3]
            }
        finally:
            conn.close()
    
    def _get_known_types(self) -> List[str]:
        """Get list of known document types from database."""
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            results = conn.execute("""
                SELECT type_name
                FROM document_types
                WHERE is_active = true
                ORDER BY usage_count DESC
            """).fetchall()
            
            return [row[0] for row in results]
        finally:
            conn.close()
    
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
            
            # Get active prompt and known types
            if not self._active_prompt:
                self._active_prompt = self._get_active_prompt()
            if not self._known_types:
                self._known_types = self._get_known_types()
            
            # Call MCP tool for classification
            loop = asyncio.get_event_loop()
            classification = await loop.run_in_executor(
                None,
                classify_document_dynamic,
                extracted_text,
                filename,
                self._active_prompt["prompt_text"],
                self._known_types,
                self.bedrock_client
            )
            
            # Update database with classification results
            conn = duckdb.connect(str(self.settings.database_path))
            try:
                conn.execute("""
                    UPDATE documents
                    SET document_type = ?,
                        suggested_type = ?,
                        secondary_tags = ?,
                        classification_confidence = ?,
                        classification_reasoning = ?,
                        updated_at = ?
                    WHERE id = ?
                """, [
                    classification["document_type"],
                    classification.get("suggested_type"),
                    json.dumps(classification.get("secondary_tags", [])),
                    classification["confidence"],
                    classification["reasoning"],
                    datetime.utcnow(),
                    doc_id
                ])
                
                # If LLM suggested a new type, record it
                if classification.get("suggested_type"):
                    self._record_suggestion(
                        conn,
                        classification["suggested_type"],
                        doc_id,
                        classification["confidence"],
                        classification.get("suggestion_reasoning", "")
                    )
                
                logger.info(
                    f"Classification complete for {doc_id}: "
                    f"type={classification['document_type']}, "
                    f"confidence={classification['confidence']:.2%}, "
                    f"tags={classification.get('secondary_tags', [])}"
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
    
    
    def _record_suggestion(self, conn, suggested_type: str, doc_id: str, confidence: float, reasoning: str):
        """Record a classification suggestion for review."""
        suggestion_id = str(uuid4())
        conn.execute("""
            INSERT INTO classification_suggestions
            (id, suggested_type, document_id, confidence, reasoning, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [suggestion_id, suggested_type, doc_id, confidence, reasoning, datetime.utcnow()])
        
        logger.info(f"Recorded new type suggestion: {suggested_type} for document {doc_id}")