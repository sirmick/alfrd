"""Scorer Workers - Evaluate and improve classifier and summarizer prompts."""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import sys
import json

# Add parent directories to path for standalone execution
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))  # MCP server source

from shared.config import Settings
from shared.types import DocumentStatus, PromptType, ScoringResult
from shared.database import AlfrdDatabase
from document_processor.workers import BaseWorker

# Import MCP tools
from mcp_server.llm.bedrock import BedrockClient
from mcp_server.tools.score_performance import (
    score_classification,
    score_summarization,
    evolve_prompt
)

logger = logging.getLogger(__name__)


class ClassifierScorerWorker(BaseWorker):
    """Worker that scores classifier performance and evolves the prompt."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """
        Initialize Classifier Scorer worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        super().__init__(
            settings=settings,
            db=db,
            worker_name="Classifier Scorer Worker",
            source_status=DocumentStatus.CLASSIFIED,
            target_status=DocumentStatus.SCORED_CLASSIFICATION,
            concurrency=settings.classifier_scorer_workers,
            poll_interval=settings.classifier_scorer_poll_interval,
        )
        
        # Initialize Bedrock client for scoring
        self.bedrock_client = BedrockClient()
        logger.info("Initialized Bedrock client for classifier scoring")
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'classified' status.
        
        Only scores when we have enough documents to evaluate performance.
        
        Args:
            status: Document status to query (DocumentStatus.CLASSIFIED)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries (empty if not enough for scoring)
        """
        # Check how many classified documents we have
        docs = await self.db.get_documents_by_status(status, limit=1000)
        classified_count = len(docs)
        
        # Only process if we have minimum documents for scoring
        if classified_count < self.settings.min_documents_for_scoring:
            return []
        
        # Get documents for scoring
        documents = await self.db.get_documents_by_status(status, limit)
        
        # Ensure all expected fields are present
        for doc in documents:
            # Add default values for any missing fields
            doc.setdefault('classification_confidence', doc.get('confidence', 0.0))
            doc.setdefault('classification_reasoning', '')
        
        return documents
    
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document: score the classification and update prompt if needed.
        
        This evaluates how well the classifier performed on this document and
        provides feedback to improve the classifier prompt.
        
        Args:
            document: Document dictionary with classification results
            
        Returns:
            True if scoring succeeded
            
        Raises:
            Exception: If scoring fails
        """
        doc_id = document["id"]
        
        logger.info(f"Scoring classification for document {doc_id}")
        
        try:
            # Update status to scoring_classification
            await self.update_status(doc_id, DocumentStatus.SCORING_CLASSIFICATION)
            
            # Get active classifier prompt
            active_prompt = await self._get_active_prompt()
            
            # Call MCP tool for scoring
            document_info = {
                "filename": document.get("filename", ""),
                "extracted_text": document.get("extracted_text", ""),
                "document_type": document.get("document_type", "unknown"),
                "confidence": document.get("classification_confidence", 0.0),
                "reasoning": document.get("classification_reasoning", ""),
                "tags": document.get("tags", [])
            }
            
            loop = asyncio.get_event_loop()
            scoring = await loop.run_in_executor(
                None,
                score_classification,
                document_info,
                active_prompt["prompt_text"],
                self.bedrock_client
            )
            
            # Check if we should update the prompt
            should_update = await self._should_update_prompt(
                active_prompt, 
                scoring["score"]
            )
            
            if should_update:
                await self._evolve_prompt(
                    active_prompt,
                    scoring["feedback"],
                    scoring["suggested_improvements"],
                    scoring["score"]
                )
            
            # Update document status
            await self.update_status(doc_id, DocumentStatus.SCORED_CLASSIFICATION)
            
            logger.info(
                f"Scoring complete for {doc_id}: "
                f"score={scoring['score']:.2f}, "
                f"prompt_updated={should_update}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Scoring failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise
    
    async def _get_active_prompt(self) -> dict:
        """Get the active classifier prompt from database."""
        prompt = await self.db.get_active_prompt(PromptType.CLASSIFIER)
        if not prompt:
            raise ValueError("No active classifier prompt found")
        
        # Parse performance_metrics if it's a JSON string
        if isinstance(prompt.get('performance_metrics'), str):
            prompt['performance_metrics'] = json.loads(prompt['performance_metrics']) if prompt['performance_metrics'] else {}
        
        return prompt
    
    async def _should_update_prompt(self, active_prompt: dict, new_score: float) -> bool:
        """
        Determine if prompt should be updated based on performance.
        
        Updates if:
        1. Current score is below threshold
        2. We have improvement suggestions
        3. Enough documents have been scored
        """
        current_score = active_prompt.get("performance_score")
        
        # Always update if no score yet
        if current_score is None:
            return True
        
        # Update if score improved by threshold
        if new_score > current_score + self.settings.prompt_update_threshold:
            return True
        
        # Update if score is poor (below 0.7)
        if new_score < 0.7:
            return True
        
        return False
    
    async def _evolve_prompt(
        self, 
        active_prompt: dict, 
        feedback: str, 
        improvements: str, 
        score: float
    ):
        """Create new prompt version based on feedback using MCP tool."""
        
        # Use MCP tool to evolve prompt
        loop = asyncio.get_event_loop()
        new_prompt_text = await loop.run_in_executor(
            None,
            evolve_prompt,
            active_prompt["prompt_text"],
            "classifier",
            None,  # No document_type for classifier
            feedback,
            improvements,
            self.settings.classifier_prompt_max_words,
            self.bedrock_client
        )
        
        # Save new prompt version to database
        # Deactivate old prompt
        await self.db.deactivate_old_prompts(PromptType.CLASSIFIER, None)
        
        # Insert new prompt
        from uuid import uuid4
        new_version = active_prompt["version"] + 1
        
        await self.db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.CLASSIFIER,
            document_type=None,
            prompt_text=new_prompt_text,
            version=new_version,
            performance_score=score,
            performance_metrics=json.dumps({"evolution_feedback": feedback})
        )
        
        logger.info(
            f"Evolved classifier prompt to version {new_version} "
            f"(score: {score:.2f})"
        )


class SummarizerScorerWorker(BaseWorker):
    """Worker that scores summarizer performance and evolves prompts."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """
        Initialize Summarizer Scorer worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        super().__init__(
            settings=settings,
            db=db,
            worker_name="Summarizer Scorer Worker",
            source_status=DocumentStatus.FILED,  # CHANGED: Now polls 'filed' instead of 'summarized'
            target_status=DocumentStatus.COMPLETED,
            concurrency=settings.summarizer_scorer_workers,
            poll_interval=settings.summarizer_scorer_poll_interval,
        )
        
        # Initialize Bedrock client for scoring
        self.bedrock_client = BedrockClient()
        logger.info("Initialized Bedrock client for summarizer scoring")
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """Query database for documents in 'filed' status."""
        documents = await self.db.get_documents_by_status(status, limit)
        
        # Parse structured_data from JSON string if needed
        for doc in documents:
            if isinstance(doc.get('structured_data'), str):
                doc['structured_data'] = json.loads(doc['structured_data']) if doc['structured_data'] else {}
        
        return documents
    
    async def process_document(self, document: dict) -> bool:
        """
        Score the summarization and update prompt if needed.
        
        Args:
            document: Document dictionary with summarization results
            
        Returns:
            True if scoring succeeded
        """
        doc_id = document["id"]
        doc_type = document["document_type"]
        
        logger.info(f"Scoring summarization for document {doc_id} (type: {doc_type})")
        
        try:
            # Update status to scoring_summary
            await self.update_status(doc_id, DocumentStatus.SCORING_SUMMARY)
            
            # Get active summarizer prompt for this document type
            active_prompt = await self._get_active_prompt(doc_type)
            
            # Call MCP tool for scoring
            document_info = {
                "filename": document["filename"],
                "extracted_text": document["extracted_text"],
                "document_type": document["document_type"],
                "structured_data": document["structured_data"]
            }
            
            loop = asyncio.get_event_loop()
            scoring = await loop.run_in_executor(
                None,
                score_summarization,
                document_info,
                active_prompt["prompt_text"],
                self.bedrock_client
            )
            
            # Check if we should update the prompt
            should_update = await self._should_update_prompt(
                active_prompt,
                scoring["score"]
            )
            
            if should_update:
                await self._evolve_prompt(
                    active_prompt,
                    doc_type,
                    scoring["feedback"],
                    scoring["suggested_improvements"],
                    scoring["score"]
                )
            
            # Mark document as completed
            await self.update_status(doc_id, DocumentStatus.COMPLETED)
            
            # Clean up inbox folder after successful processing
            await self._cleanup_inbox_folder(doc_id)
            
            logger.info(
                f"Scoring complete for {doc_id}: "
                f"score={scoring['score']:.2f}, "
                f"prompt_updated={should_update}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Summarizer scoring failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise
    
    async def _get_active_prompt(self, document_type: str) -> dict:
        """Get the active summarizer prompt for a document type."""
        prompt = await self.db.get_active_prompt(PromptType.SUMMARIZER, document_type)
        if not prompt:
            raise ValueError(f"No active summarizer prompt found for type: {document_type}")
        
        # Parse performance_metrics if it's a JSON string
        if isinstance(prompt.get('performance_metrics'), str):
            prompt['performance_metrics'] = json.loads(prompt['performance_metrics']) if prompt['performance_metrics'] else {}
        
        return prompt
    
    
    async def _should_update_prompt(self, active_prompt: dict, new_score: float) -> bool:
        """Determine if prompt should be updated based on performance."""
        current_score = active_prompt.get("performance_score")
        
        if current_score is None:
            return True
        
        if new_score > current_score + self.settings.prompt_update_threshold:
            return True
        
        if new_score < 0.7:
            return True
        
        return False
    
    async def _evolve_prompt(
        self,
        active_prompt: dict,
        document_type: str,
        feedback: str,
        improvements: str,
        score: float
    ):
        """Create new prompt version based on feedback using MCP tool."""
        
        # Use MCP tool to evolve prompt
        loop = asyncio.get_event_loop()
        new_prompt_text = await loop.run_in_executor(
            None,
            evolve_prompt,
            active_prompt["prompt_text"],
            "summarizer",
            document_type,
            feedback,
            improvements,
            None,  # No max_words for summarizer
            self.bedrock_client
        )
        
        # Save new prompt version
        # Deactivate old prompt
        await self.db.deactivate_old_prompts(PromptType.SUMMARIZER, document_type)
        
        # Insert new prompt
        from uuid import uuid4
        new_version = active_prompt["version"] + 1
        
        await self.db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.SUMMARIZER,
            document_type=document_type,
            prompt_text=new_prompt_text,
            version=new_version,
            performance_score=score,
            performance_metrics=json.dumps({"evolution_feedback": feedback})
        )
        
        logger.info(
            f"Evolved {document_type} summarizer prompt to version {new_version} "
            f"(score: {score:.2f})"
        )
    
    async def _cleanup_inbox_folder(self, doc_id: str):
        """Delete inbox folder after successful processing."""
        import shutil
        
        # Get original inbox folder path
        doc = await self.db.get_document(doc_id)
        if not doc or not doc.get('folder_path'):
            return
        
        folder_path = Path(doc['folder_path'])
        
        # Only delete if it's in the inbox directory
        try:
            folder_path.relative_to(self.settings.inbox_path)
            
            if folder_path.exists():
                shutil.rmtree(folder_path)
                logger.info(f"Cleaned up inbox folder: {folder_path.name}")
        except ValueError:
            # Path is not in inbox, don't delete
            logger.debug(f"Folder {folder_path} not in inbox, skipping cleanup")
        except Exception as e:
            # Don't fail the whole process if cleanup fails
            logger.warning(f"Failed to cleanup inbox folder for {doc_id}: {e}")