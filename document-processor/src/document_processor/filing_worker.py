"""Filing Worker - Automatically creates series based on document metadata after summarization.

This worker:
1. Polls for documents with status='summarized'
2. Calls detect_series MCP tool to analyze document
3. Creates series if one doesn't exist for that entity + series_type
4. Adds document to document_series junction table
5. Updates document status to 'filed'
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Any
import sys
from uuid import uuid4

# Add parent directories to path
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

from shared.config import Settings
from shared.types import DocumentStatus
from shared.database import AlfrdDatabase
from document_processor.workers import BaseWorker
from mcp_server.llm import BedrockClient
from mcp_server.tools.detect_series import detect_series_with_retry

logger = logging.getLogger(__name__)


class FilingWorker(BaseWorker):
    """Worker that creates series based on document analysis."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """
        Initialize Filing worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        super().__init__(
            settings=settings,
            db=db,
            worker_name="Filing Worker (Series)",
            source_status=DocumentStatus.SUMMARIZED,
            target_status=DocumentStatus.FILED,
            concurrency=settings.filing_workers,
            poll_interval=settings.filing_poll_interval,
        )
        
        # Initialize Bedrock client for series detection
        self.bedrock_client = BedrockClient(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_region=settings.aws_region
        )
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'summarized' status with full metadata.
        
        Args:
            status: Document status to query (DocumentStatus.SUMMARIZED)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries with summary, structured_data, tags
        """
        async with self.db.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, filename, status, document_type,
                       summary, structured_data, user_id
                FROM documents
                WHERE status = $1
                ORDER BY created_at ASC
                LIMIT $2
            """, status, limit)
            
            return [dict(row) for row in rows]
    
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document with hybrid approach:
        1. Detect series and create series entity
        2. Add document to series
        3. Create series-specific tag and apply it to document
        4. Create file based on series tag
        
        Args:
            document: Document dictionary with id, summary, structured_data, etc.
            
        Returns:
            True if filing succeeded
            
        Raises:
            Exception: If filing fails
        """
        doc_id = document["id"]
        
        logger.info(f"Filing document {doc_id} into series (hybrid approach)")
        
        try:
            # Get document tags for series detection
            tags = await self._get_document_tags(doc_id)
            
            # Parse structured_data if it's a string
            structured_data = document.get("structured_data", {})
            if isinstance(structured_data, str):
                import json
                try:
                    structured_data = json.loads(structured_data)
                except (json.JSONDecodeError, TypeError):
                    structured_data = {}
            
            # Detect series using MCP tool
            series_data = await self._detect_series(
                summary=document.get("summary", ""),
                document_type=document.get("document_type", "unknown"),
                structured_data=structured_data,
                tags=tags
            )
            
            logger.info(
                f"Detected series for {doc_id}: {series_data['title']} "
                f"(entity: {series_data['entity']}, type: {series_data['series_type']})"
            )
            
            # Step 1: Find or create series entity
            series_id = await self._get_or_create_series(series_data, document.get("user_id"))
            
            # Step 2: Add document to series
            await self.db.add_document_to_series(series_id, doc_id, added_by='llm')
            logger.info(f"Document {doc_id} added to series {series_id}")
            
            # Step 3: Create and apply series-specific tag
            series_tag = await self._create_series_tag(series_id, series_data)
            await self.db.add_tag_to_document(doc_id, series_tag, created_by='llm')
            logger.info(f"Applied series tag '{series_tag}' to document {doc_id}")
            
            # Step 4: Create file based on series tag (if doesn't exist)
            file_id = await self._create_series_file(series_id, series_tag, series_data, document.get("user_id"))
            logger.info(f"Document {doc_id} filed into file {file_id}")
            
            # Update document status to 'filed'
            await self.update_status(doc_id, DocumentStatus.FILED)
            
            return True
            
        except Exception as e:
            logger.error(f"Filing failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise
    
    async def _get_document_tags(self, doc_id: str) -> List[str]:
        """
        Get all tags for a document.
        
        Args:
            doc_id: Document ID
            
        Returns:
            List of tag names
        """
        return await self.db.get_document_tags(doc_id)
    
    async def _detect_series(
        self,
        summary: str,
        document_type: str,
        structured_data: Dict[str, Any],
        tags: List[str]
    ) -> Dict[str, Any]:
        """
        Call MCP detect_series tool to identify which series this document belongs to.
        
        Args:
            summary: Document summary
            document_type: Document type
            structured_data: Extracted structured data
            tags: Document tags
            
        Returns:
            Series metadata dict from LLM
        """
        return detect_series_with_retry(
            summary=summary,
            document_type=document_type,
            structured_data=structured_data,
            tags=tags,
            bedrock_client=self.bedrock_client,
            max_retries=2
        )
    
    async def _get_or_create_series(
        self,
        series_data: Dict[str, Any],
        user_id: str = None
    ) -> str:
        """
        Find existing series or create a new one.
        
        Args:
            series_data: Series metadata from detect_series
            user_id: User ID (optional)
            
        Returns:
            Series ID (UUID)
        """
        series_id = uuid4()
        
        # Calculate expected_frequency_days based on frequency
        frequency_map = {
            'weekly': 7,
            'biweekly': 14,
            'monthly': 30,
            'quarterly': 90,
            'annual': 365,
            'yearly': 365
        }
        expected_frequency_days = frequency_map.get(
            series_data.get('frequency', '').lower(),
            None
        )
        
        # Find or create series
        series = await self.db.find_or_create_series(
            series_id=series_id,
            entity=series_data['entity'],
            series_type=series_data['series_type'],
            title=series_data['title'],
            frequency=series_data.get('frequency'),
            description=series_data.get('description'),
            metadata=series_data.get('metadata'),
            user_id=user_id
        )
        
        # Update expected_frequency_days if we created it
        if expected_frequency_days and series['id'] == series_id:
            await self.db.update_series(
                series['id'],
                expected_frequency_days=expected_frequency_days
            )
        
        return series['id']
    
    async def _create_series_tag(
        self,
        series_id: str,
        series_data: Dict[str, Any]
    ) -> str:
        """
        Create a unique tag name for this series.
        
        Format: "series:<entity>-<series_type>"
        Example: "series:state-farm-auto-insurance"
        
        Args:
            series_id: Series UUID
            series_data: Series metadata from detect_series
            
        Returns:
            Tag name (e.g., "series:state-farm-auto-insurance")
        """
        # Normalize entity and series_type for tag
        entity_slug = series_data['entity'].lower().replace(' ', '-').replace('&', 'and')
        type_slug = series_data['series_type'].replace('_', '-')
        
        # Create tag name
        tag_name = f"series:{entity_slug}"
        
        return tag_name
    
    async def _create_series_file(
        self,
        series_id: str,
        series_tag: str,
        series_data: Dict[str, Any],
        user_id: str = None
    ) -> str:
        """
        Create a file for this series (if doesn't already exist).
        
        Args:
            series_id: Series UUID
            series_tag: Series tag name
            series_data: Series metadata
            user_id: User ID (optional)
            
        Returns:
            File ID (UUID)
        """
        # Create file with series tag
        file_id = uuid4()
        
        # Use the tag as the basis for the file
        file_record = await self.db.find_or_create_file(
            file_id=file_id,
            tags=[series_tag],
            user_id=user_id
        )
        
        return file_record['id']