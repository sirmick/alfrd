"""Workflow Worker - Processes classified documents with type-specific handlers."""

import asyncio
import logging
from pathlib import Path
from typing import List, Optional, Dict, Any
import sys
import json
import duckdb
from datetime import datetime

# Add parent directories to path
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))

from shared.config import Settings
from shared.types import DocumentStatus, DocumentType
from document_processor.workers import BaseWorker
from mcp_server.llm import BedrockClient
from mcp_server.tools.summarize_bill import summarize_bill_with_retry

logger = logging.getLogger(__name__)


class WorkflowHandler:
    """Base class for type-specific workflow handlers."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
    
    async def handle(self, document: dict) -> Dict[str, Any]:
        """
        Handle workflow processing for a document.
        
        Args:
            document: Document dictionary with id, extracted_text, etc.
            
        Returns:
            Dict with structured_data to store in database
            
        Raises:
            Exception: If workflow processing fails
        """
        raise NotImplementedError("Subclasses must implement handle()")


class BillHandler(WorkflowHandler):
    """Handler for bill documents - extracts structured bill information."""
    
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.bedrock_client = BedrockClient()
    
    async def handle(self, document: dict) -> Dict[str, Any]:
        """
        Extract structured bill information using MCP.
        
        Args:
            document: Document dictionary with extracted_text and extracted_text_path
            
        Returns:
            Dict with bill summary data
        """
        doc_id = document["id"]
        filename = document.get("filename", "unknown")
        extracted_text_path = document.get("extracted_text_path", "")
        
        logger.info(f"BillHandler processing document {doc_id}")
        
        # Load LLM-formatted JSON with full blocks structure
        llm_data = None
        if extracted_text_path:
            # Try to read the _llm.json file (stored alongside text file)
            text_path = Path(extracted_text_path)
            llm_json_path = text_path.parent / f"{doc_id}_llm.json"
            
            if llm_json_path.exists():
                try:
                    with open(llm_json_path, 'r') as f:
                        llm_data = json.load(f)
                    logger.info(f"Loaded LLM-formatted data from {llm_json_path}")
                except Exception as e:
                    logger.warning(f"Failed to load LLM data: {e}, falling back to plain text")
        
        # Fallback to plain text if LLM data not available
        if not llm_data:
            extracted_text = document.get("extracted_text", "")
            if not extracted_text:
                raise ValueError(f"No extracted text found for document {doc_id}")
            llm_data = {"full_text": extracted_text}
        
        # Call MCP to summarize bill with full structure
        bill_summary = summarize_bill_with_retry(
            llm_data=llm_data,
            filename=filename,
            bedrock_client=self.bedrock_client,
        )
        
        # Convert to dictionary
        structured_data = bill_summary.to_dict()
        
        # Also update vendor, amount, due_date at top level for easier querying
        vendor = structured_data.get("vendor", "")
        amount = structured_data.get("amount", 0.0)
        due_date = structured_data.get("due_date", "")
        
        logger.info(
            f"Bill summarized: {vendor}, ${amount:.2f}, due {due_date}"
        )
        
        return {
            "structured_data": structured_data,
            "vendor": vendor,
            "amount": amount,
            "due_date": due_date if due_date else None,
        }


class FinanceHandler(WorkflowHandler):
    """Handler for finance documents - placeholder for future implementation."""
    
    async def handle(self, document: dict) -> Dict[str, Any]:
        """
        Process finance document.
        
        For now, just mark as completed without additional processing.
        Future: Extract account numbers, balances, transactions, etc.
        """
        doc_id = document["id"]
        logger.info(f"FinanceHandler processing document {doc_id} (placeholder)")
        
        return {
            "structured_data": {
                "handler": "finance",
                "status": "placeholder_complete",
            }
        }


class JunkHandler(WorkflowHandler):
    """Handler for junk documents - minimal processing."""
    
    async def handle(self, document: dict) -> Dict[str, Any]:
        """
        Process junk document.
        
        Just mark as completed - no additional processing needed.
        """
        doc_id = document["id"]
        logger.info(f"JunkHandler processing document {doc_id} (marking as complete)")
        
        return {
            "structured_data": {
                "handler": "junk",
                "status": "complete",
            }
        }


class WorkflowWorker(BaseWorker):
    """Worker that processes classified documents with type-specific handlers."""
    
    def __init__(self, settings: Settings):
        """
        Initialize workflow worker.
        
        Args:
            settings: Application settings
        """
        super().__init__(
            settings=settings,
            worker_name="Workflow Worker",
            source_status=DocumentStatus.CLASSIFIED,
            target_status=DocumentStatus.COMPLETED,
            concurrency=settings.workflow_workers,
            poll_interval=settings.workflow_poll_interval,
        )
        
        # Initialize handlers
        self.handlers = {
            DocumentType.BILL: BillHandler(settings),
            DocumentType.FINANCE: FinanceHandler(settings),
            DocumentType.JUNK: JunkHandler(settings),
        }
        
        logger.info(f"WorkflowWorker initialized with {len(self.handlers)} handlers")
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'classified' status.
        
        Args:
            status: Document status to query (DocumentStatus.CLASSIFIED)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            results = conn.execute("""
                SELECT id, filename, document_type, extracted_text, extracted_text_path
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
                    "document_type": row[2],
                    "extracted_text": row[3],
                    "extracted_text_path": row[4],
                })
            
            return documents
        finally:
            conn.close()
    
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document: route to appropriate handler.
        
        Args:
            document: Document dictionary with id, document_type, extracted_text
            
        Returns:
            True if workflow processing succeeded
            
        Raises:
            Exception: If workflow processing fails
        """
        doc_id = document["id"]
        doc_type_str = document.get("document_type", "")
        
        logger.info(f"Workflow processing document {doc_id} (type: {doc_type_str})")
        
        try:
            # Update status to processing
            await self.update_status(doc_id, DocumentStatus.PROCESSING)
            
            # Get document type enum
            try:
                doc_type = DocumentType(doc_type_str.lower())
            except ValueError:
                logger.warning(
                    f"Unknown document type '{doc_type_str}' for {doc_id}, "
                    f"treating as junk"
                )
                doc_type = DocumentType.JUNK
            
            # Get handler
            handler = self.handlers.get(doc_type)
            if not handler:
                raise ValueError(f"No handler found for type: {doc_type}")
            
            # Process with handler
            result = await handler.handle(document)
            
            # Update database with results
            conn = duckdb.connect(str(self.settings.database_path))
            try:
                structured_data = result.get("structured_data", {})
                vendor = result.get("vendor")
                amount = result.get("amount")
                due_date = result.get("due_date")
                
                # Convert structured_data to JSON string
                structured_data_json = json.dumps(structured_data)
                
                conn.execute("""
                    UPDATE documents 
                    SET structured_data = ?,
                        vendor = ?,
                        amount = ?,
                        due_date = ?,
                        updated_at = ?
                    WHERE id = ?
                """, [
                    structured_data_json,
                    vendor,
                    amount,
                    due_date,
                    datetime.utcnow(),
                    doc_id
                ])
                
                logger.info(f"Workflow complete for {doc_id}")
            finally:
                conn.close()
            
            # Update status to completed
            await self.update_status(doc_id, DocumentStatus.COMPLETED)
            
            return True
            
        except Exception as e:
            logger.error(f"Workflow failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise


# Standalone execution for testing
async def main():
    """Test workflow worker."""
    import logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    settings = Settings()
    worker = WorkflowWorker(settings)
    
    logger.info("Starting WorkflowWorker test...")
    try:
        await worker.run()
    except KeyboardInterrupt:
        logger.info("Stopping WorkflowWorker...")
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())