"""Scorer Workers - Evaluate and improve classifier and summarizer prompts."""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
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
from shared.types import DocumentStatus, PromptType, ScoringResult
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
    
    def __init__(self, settings: Settings):
        """
        Initialize Classifier Scorer worker.
        
        Args:
            settings: Application settings
        """
        super().__init__(
            settings=settings,
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
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            # Check how many classified documents we have
            count_result = conn.execute("""
                SELECT COUNT(*) 
                FROM documents 
                WHERE status = ?
            """, [status.value]).fetchone()
            
            classified_count = count_result[0] if count_result else 0
            
            # Only process if we have minimum documents for scoring
            if classified_count < self.settings.min_documents_for_scoring:
                return []
            
            # Get documents for scoring
            results = conn.execute("""
                SELECT id, filename, extracted_text, document_type, 
                       classification_confidence, classification_reasoning,
                       secondary_tags
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
                    "document_type": row[3],
                    "classification_confidence": row[4],
                    "classification_reasoning": row[5],
                    "secondary_tags": json.loads(row[6]) if row[6] else [],
                })
            
            return documents
        finally:
            conn.close()
    
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
            active_prompt = self._get_active_prompt()
            
            # Call MCP tool for scoring
            document_info = {
                "filename": document["filename"],
                "extracted_text": document["extracted_text"],
                "document_type": document["document_type"],
                "confidence": document["classification_confidence"],
                "reasoning": document["classification_reasoning"],
                "secondary_tags": document["secondary_tags"]
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
    
    def _get_active_prompt(self) -> dict:
        """Get the active classifier prompt from database."""
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            result = conn.execute("""
                SELECT id, prompt_text, version, performance_score, performance_metrics
                FROM prompts
                WHERE prompt_type = ? 
                  AND document_type IS NULL
                  AND is_active = true
                ORDER BY version DESC
                LIMIT 1
            """, [PromptType.CLASSIFIER.value]).fetchone()
            
            if not result:
                raise ValueError("No active classifier prompt found")
            
            return {
                "id": result[0],
                "prompt_text": result[1],
                "version": result[2],
                "performance_score": result[3],
                "performance_metrics": json.loads(result[4]) if result[4] else {}
            }
        finally:
            conn.close()
    
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
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            # Deactivate old prompt
            conn.execute("""
                UPDATE prompts 
                SET is_active = false 
                WHERE id = ?
            """, [active_prompt["id"]])
            
            # Insert new prompt
            new_id = str(uuid4())
            new_version = active_prompt["version"] + 1
            
            conn.execute("""
                INSERT INTO prompts 
                (id, prompt_type, document_type, prompt_text, version, 
                 performance_score, performance_metrics, is_active, created_at, updated_at)
                VALUES (?, ?, NULL, ?, ?, ?, ?, true, ?, ?)
            """, [
                new_id,
                PromptType.CLASSIFIER.value,
                new_prompt_text,
                new_version,
                score,
                json.dumps({"evolution_feedback": feedback}),
                datetime.utcnow(),
                datetime.utcnow()
            ])
            
            logger.info(
                f"Evolved classifier prompt to version {new_version} "
                f"(score: {score:.2f})"
            )
        finally:
            conn.close()


class SummarizerScorerWorker(BaseWorker):
    """Worker that scores summarizer performance and evolves prompts."""
    
    def __init__(self, settings: Settings):
        """
        Initialize Summarizer Scorer worker.
        
        Args:
            settings: Application settings
        """
        super().__init__(
            settings=settings,
            worker_name="Summarizer Scorer Worker",
            source_status=DocumentStatus.SUMMARIZED,
            target_status=DocumentStatus.COMPLETED,
            concurrency=settings.summarizer_scorer_workers,
            poll_interval=settings.summarizer_scorer_poll_interval,
        )
        
        # Initialize Bedrock client for scoring
        self.bedrock_client = BedrockClient()
        logger.info("Initialized Bedrock client for summarizer scoring")
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """Query database for documents in 'summarized' status."""
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            results = conn.execute("""
                SELECT id, filename, extracted_text, document_type, structured_data
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
                    "document_type": row[3],
                    "structured_data": json.loads(row[4]) if row[4] else {},
                })
            
            return documents
        finally:
            conn.close()
    
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
            active_prompt = self._get_active_prompt(doc_type)
            
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
    
    def _get_active_prompt(self, document_type: str) -> dict:
        """Get the active summarizer prompt for a document type."""
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            result = conn.execute("""
                SELECT id, prompt_text, version, performance_score, performance_metrics
                FROM prompts
                WHERE prompt_type = ? 
                  AND document_type = ?
                  AND is_active = true
                ORDER BY version DESC
                LIMIT 1
            """, [PromptType.SUMMARIZER.value, document_type]).fetchone()
            
            if not result:
                raise ValueError(f"No active summarizer prompt found for type: {document_type}")
            
            return {
                "id": result[0],
                "prompt_text": result[1],
                "version": result[2],
                "performance_score": result[3],
                "performance_metrics": json.loads(result[4]) if result[4] else {}
            }
        finally:
            conn.close()
    
    
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
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            conn.execute("""
                UPDATE prompts 
                SET is_active = false 
                WHERE id = ?
            """, [active_prompt["id"]])
            
            new_id = str(uuid4())
            new_version = active_prompt["version"] + 1
            
            conn.execute("""
                INSERT INTO prompts 
                (id, prompt_type, document_type, prompt_text, version, 
                 performance_score, performance_metrics, is_active, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, true, ?, ?)
            """, [
                new_id,
                PromptType.SUMMARIZER.value,
                document_type,
                new_prompt_text,
                new_version,
                score,
                json.dumps({"evolution_feedback": feedback}),
                datetime.utcnow(),
                datetime.utcnow()
            ])
            
            logger.info(
                f"Evolved {document_type} summarizer prompt to version {new_version} "
                f"(score: {score:.2f})"
            )
        finally:
            conn.close()
    
    async def _cleanup_inbox_folder(self, doc_id: str):
        """Delete inbox folder after successful processing."""
        import shutil
        
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            # Get original inbox folder path
            result = conn.execute(
                "SELECT folder_path FROM documents WHERE id = ?",
                [doc_id]
            ).fetchone()
            
            if not result or not result[0]:
                return
            
            folder_path = Path(result[0])
            
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
        finally:
            conn.close()