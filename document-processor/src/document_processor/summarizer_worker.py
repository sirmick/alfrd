"""Summarizer Worker - Generic document summarization using DB-stored prompts."""

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
from mcp_server.tools.summarize_dynamic import summarize_document_dynamic

logger = logging.getLogger(__name__)


class SummarizerWorker(BaseWorker):
    """Worker that summarizes documents using DB-stored type-specific prompts."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """
        Initialize Summarizer worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        super().__init__(
            settings=settings,
            db=db,
            worker_name="Summarizer Worker",
            source_status=DocumentStatus.SCORED_CLASSIFICATION,
            target_status=DocumentStatus.SUMMARIZED,
            concurrency=settings.summarizer_workers,
            poll_interval=settings.summarizer_poll_interval,
        )
        
        # Initialize Bedrock client for summarization
        self.bedrock_client = BedrockClient()
        logger.info("Initialized Bedrock client for summarization")
        
        # Cache for active prompts by document type
        self._prompts_cache: dict = {}
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'scored_classification' status.
        
        Args:
            status: Document status to query (DocumentStatus.SCORED_CLASSIFICATION)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
        return await self.db.get_documents_by_status(status, limit)
    
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document: summarize using type-specific prompt.
        
        This uses the DB-stored prompt for the document type to generate
        a summary with extracted structured data.
        
        Args:
            document: Document dictionary with id, filename, document_type, extracted_text
            
        Returns:
            True if summarization succeeded
            
        Raises:
            Exception: If summarization fails
        """
        doc_id = document["id"]
        doc_type = document["document_type"]
        filename = document["filename"]
        
        logger.info(f"Summarizing document {doc_id}: {filename} (type: {doc_type})")
        
        try:
            # Update status to summarizing
            await self.update_status(doc_id, DocumentStatus.SUMMARIZING)
            
            # Get active summarizer prompt for this document type
            if doc_type not in self._prompts_cache:
                self._prompts_cache[doc_type] = await self._get_active_prompt(doc_type)
            
            active_prompt = self._prompts_cache[doc_type]
            
            # Load full LLM JSON if available (for block-level data)
            llm_data = self._load_llm_json(document)
            
            # Call MCP tool for summarization
            loop = asyncio.get_event_loop()
            summary = await loop.run_in_executor(
                None,
                summarize_document_dynamic,
                document["extracted_text"],
                filename,
                doc_type,
                active_prompt["prompt_text"],
                llm_data,
                self.bedrock_client
            )
            
            # Extract one-line summary if present
            summary_text = summary.get('summary', '')
            
            # Update database with both summary text and structured data
            await self.db.update_document(
                doc_id=doc_id,
                summary=summary_text,
                structured_data=json.dumps(summary)
            )
            
            # Log with full one-line summary
            summary_preview = summary_text if len(summary_text) <= 100 else f"{summary_text[:97]}..."
            logger.info(
                f"Summarization complete for {doc_id}: "
                f"{len(summary)} fields extracted"
            )
            logger.info(f"  Summary: {summary_preview}")
            
            # Update status to summarized
            await self.update_status(doc_id, DocumentStatus.SUMMARIZED)
            
            return True
            
        except Exception as e:
            logger.error(f"Summarization failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise
    
    async def _get_active_prompt(self, document_type: str) -> dict:
        """Get the active summarizer prompt for a document type."""
        prompt = await self.db.get_active_prompt(PromptType.SUMMARIZER, document_type)
        
        if not prompt:
            # Try to get a generic summarizer prompt
            logger.warning(
                f"No specific prompt for type '{document_type}', "
                f"using generic summarizer"
            )
            prompt = await self.db.get_active_prompt(PromptType.SUMMARIZER, 'generic')
            
            if not prompt:
                raise ValueError(
                    f"No active summarizer prompt found for type: {document_type}"
                )
        
        return prompt
    
    def _load_llm_json(self, document: dict) -> Optional[dict]:
        """Load the LLM-optimized JSON with block-level data if available."""
        try:
            text_path = document.get("extracted_text_path")
            if not text_path:
                return None
            
            # Look for _llm.json file
            text_path = Path(text_path)
            llm_json_path = text_path.parent / f"{text_path.stem}_llm.json"
            
            if llm_json_path.exists():
                with open(llm_json_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load LLM JSON: {e}")
        
        return None
    


# Main execution for testing
if __name__ == "__main__":
    import sys
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    async def main():
        settings = Settings()
        worker = SummarizerWorker(settings)
        
        logger.info("Starting Summarizer Worker (test mode)")
        await worker.run()
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Summarizer Worker stopped by user")
        sys.exit(0)