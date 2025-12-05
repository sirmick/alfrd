"""Classifier Worker - Classifies documents using DB-stored prompts and MCP."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional
import sys
import json

# Add parent directories to path for standalone execution
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))  # MCP server source

from shared.config import Settings
from shared.types import DocumentStatus, PromptType
from shared.database import AlfrdDatabase
from document_processor.workers import BaseWorker

# Import MCP tools
from mcp_server.llm.bedrock import BedrockClient
from mcp_server.tools.classify_dynamic import classify_document_dynamic

logger = logging.getLogger(__name__)


class ClassifierWorker(BaseWorker):
    """Worker that classifies documents in 'ocr_completed' status using MCP."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """
        Initialize Classifier worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        super().__init__(
            settings=settings,
            db=db,
            worker_name="Classifier Worker",
            source_status=DocumentStatus.OCR_COMPLETED,
            target_status=DocumentStatus.CLASSIFIED,
            concurrency=settings.classifier_workers,
            poll_interval=settings.classifier_poll_interval,
        )
        
        # Initialize Bedrock client for MCP tools
        self.bedrock_client = BedrockClient()
        logger.info("Initialized Bedrock client for classification")
        
        # Cache for active classifier prompt and existing tags
        self._active_prompt: Optional[dict] = None
        self._known_types: Optional[List[str]] = None
        self._existing_tags: Optional[List[str]] = None
    
    async def _get_active_prompt(self) -> dict:
        """Get the active classifier prompt from database."""
        prompt = await self.db.get_active_prompt(PromptType.CLASSIFIER)
        if not prompt:
            raise ValueError("No active classifier prompt found in database")
        return prompt
    
    async def _get_known_types(self) -> List[str]:
        """Get list of known document types from database."""
        types = await self.db.get_document_types()
        return [t['type_name'] for t in types]
    
    async def _get_existing_tags(self) -> List[str]:
        """Get list of popular existing tags from database."""
        return await self.db.get_popular_tags(limit=50)
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'ocr_completed' status.
        
        Args:
            status: Document status to query (DocumentStatus.OCR_COMPLETED)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
        return await self.db.get_documents_by_status(status, limit)
    
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
            
            # Get active prompt, known types, and existing tags
            if not self._active_prompt:
                self._active_prompt = await self._get_active_prompt()
            if not self._known_types:
                self._known_types = await self._get_known_types()
            if not self._existing_tags:
                self._existing_tags = await self._get_existing_tags()
            
            # Call MCP tool for classification with existing tags
            loop = asyncio.get_event_loop()
            classification = await loop.run_in_executor(
                None,
                classify_document_dynamic,
                extracted_text,
                filename,
                self._active_prompt["prompt_text"],
                self._known_types,
                self._existing_tags,
                self.bedrock_client
            )
            
            # Merge user tags with LLM-generated tags
            user_tags = json.loads(document.get("folder_metadata", "{}").get("metadata", {}).get("tags", "[]")) if document.get("folder_metadata") else []
            llm_tags = classification.get("tags", [])
            
            # Update database with classification results (without tags field)
            # Log values for debugging
            logger.info(
                f"Updating document {doc_id} with classification: "
                f"type={classification['document_type']}, "
                f"suggested={classification.get('suggested_type')}, "
                f"confidence={classification['confidence']}, "
                f"reasoning_type={type(classification['reasoning'])}"
            )
            
            await self.db.update_document(
                doc_id=doc_id,
                document_type=classification["document_type"],
                suggested_type=classification.get("suggested_type"),
                classification_confidence=classification["confidence"],
                classification_reasoning=str(classification["reasoning"]) if classification.get("reasoning") else None
            )
            
            # Add document_type as a tag automatically (for easy file filtering)
            await self.db.add_tag_to_document(doc_id, classification["document_type"], created_by='system')
            
            # Add tags to junction table
            for tag in user_tags:
                await self.db.add_tag_to_document(doc_id, tag, created_by='user')
            
            for tag in llm_tags:
                await self.db.add_tag_to_document(doc_id, tag, created_by='llm')
            
            # Get merged tags for logging
            merged_tags = await self.db.get_document_tags(doc_id)
            
            # If LLM suggested a new type, record it
            if classification.get("suggested_type"):
                from uuid import uuid4
                await self.db.record_classification_suggestion(
                    suggestion_id=uuid4(),
                    suggested_type=classification["suggested_type"],
                    document_id=doc_id,
                    confidence=classification["confidence"],
                    reasoning=classification.get("suggestion_reasoning", "")
                )
            
            logger.info(
                f"Classification complete for {doc_id}: "
                f"type={classification['document_type']}, "
                f"confidence={classification['confidence']:.2%}, "
                f"tags={merged_tags}"
            )
            
            # Update status to classified
            await self.update_status(doc_id, DocumentStatus.CLASSIFIED)
            
            return True
            
        except Exception as e:
            logger.error(f"Classification failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise
    
    