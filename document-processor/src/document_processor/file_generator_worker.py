"""File Generator Worker - Generates summaries for file collections.

This worker:
1. Polls for files with status='pending' or 'outdated'
2. Fetches all documents in the file (chronologically)
3. Calls MCP summarize_file tool
4. Updates file with generated summary
5. Sets status='generated'
"""

import asyncio
import json
import logging
from pathlib import Path
from uuid import uuid4
from datetime import datetime
from typing import List, Optional

# Add project root to path
import sys
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

from shared.database import AlfrdDatabase
from shared.config import Settings
from document_processor.workers import BaseWorker
from mcp_server.llm.bedrock import BedrockClient
from mcp_server.tools.summarize_file import summarize_file

logger = logging.getLogger(__name__)


class FileGeneratorWorker(BaseWorker):
    """Worker to generate summaries for file collections."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """Initialize file generator worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        from shared.types import DocumentStatus
        
        super().__init__(
            settings=settings,
            db=db,
            worker_name="File Generator Worker",
            source_status=DocumentStatus.COMPLETED,  # Not actually used for file generation
            target_status=DocumentStatus.COMPLETED,   # Not used
            concurrency=getattr(settings, 'file_generator_workers', 2),
            poll_interval=getattr(settings, 'file_generator_poll_interval', 15)
        )
        self.bedrock = BedrockClient(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_region=settings.aws_region
        )
    
    async def run(self):
        """Main loop: poll for files needing generation."""
        self.running = True
        logger.info(f"{self.worker_name} started")
        
        while self.running:
            try:
                # Get files that need generation
                files = await self.db.get_files_by_status(
                    statuses=['pending', 'outdated'],
                    limit=self.concurrency * 2
                )
                
                if files:
                    logger.info(
                        f"{self.worker_name} found {len(files)} files needing generation, "
                        f"processing {min(len(files), self.concurrency)} in parallel"
                    )
                    
                    # Process files in parallel (up to concurrency limit)
                    tasks = [
                        self.generate_file_summary(file_record)
                        for file_record in files[:self.concurrency]
                    ]
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log results
                    successes = sum(1 for r in results if r is True)
                    failures = sum(1 for r in results if isinstance(r, Exception))
                    
                    logger.info(
                        f"{self.worker_name} batch complete: "
                        f"{successes} succeeded, {failures} failed"
                    )
                
                # Sleep before next poll
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                logger.error(f"{self.worker_name} error in main loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)
    
    async def generate_file_summary(self, file_record: dict) -> bool:
        """Generate summary for a file.
        
        Args:
            file_record: File record dict
            
        Returns:
            True if successful, False otherwise
        """
        file_id = file_record['id']
        
        try:
            # Mark as regenerating
            await self.db.update_file(file_id, status='regenerating')
            
            logger.info(
                f"Generating summary for file {file_id} "
                f"(tags: {file_record['tag_signature']})"
            )
            
            # 1. Parse tags from JSONB
            tags = file_record.get('tags')
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except:
                    tags = []
            elif not isinstance(tags, list):
                tags = []
            
            # 2. Fetch ALL documents matching the file's tags (reverse chronological)
            # Query documents table for matching tags
            docs = await self.db.get_documents_by_tags(
                tags=tags,
                order_by='created_at DESC'  # Reverse chronological
            )
            
            if not docs:
                logger.warning(f"File {file_id} has no matching documents, marking as generated")
                await self.db.update_file(
                    file_id,
                    summary_text="No documents found matching these tags yet.",
                    summary_metadata={},
                    aggregated_content="",
                    status='generated',
                    last_generated_at=datetime.now()
                )
                return True
            
            logger.info(f"Found {len(docs)} documents matching tags {tags} for file {file_id}")
            
            # 3. Build aggregated content text (reverse chronological)
            aggregated_lines = []
            aggregated_lines.append(f"File: {', '.join(tags)}")
            aggregated_lines.append(f"Total Documents: {len(docs)}")
            aggregated_lines.append("")
            aggregated_lines.append("=" * 80)
            aggregated_lines.append("")
            
            for i, doc in enumerate(docs, 1):
                doc_date = doc.get('created_at')
                if isinstance(doc_date, datetime):
                    doc_date_str = doc_date.strftime('%Y-%m-%d %H:%M')
                else:
                    doc_date_str = str(doc_date)
                
                aggregated_lines.append(f"Document #{i}: {doc.get('filename', 'Unknown')}")
                aggregated_lines.append(f"Date: {doc_date_str}")
                aggregated_lines.append(f"Type: {doc.get('document_type', 'N/A')}")
                
                # Include structured data if available
                structured = doc.get('structured_data')
                if structured:
                    if isinstance(structured, str):
                        aggregated_lines.append(f"Data: {structured}")
                    else:
                        aggregated_lines.append(f"Data: {json.dumps(structured, indent=2)}")
                
                # Include summary
                summary = doc.get('summary')
                if summary:
                    aggregated_lines.append(f"Summary: {summary}")
                
                aggregated_lines.append("-" * 80)
                aggregated_lines.append("")
            
            aggregated_content = "\n".join(aggregated_lines)
            
            logger.info(f"Aggregated content length: {len(aggregated_content)} chars for file {file_id}")
            
            # 4. Get active file summarizer prompt
            prompt = await self.db.get_active_prompt('file_summarizer', None)
            
            if not prompt:
                logger.error("No active file_summarizer prompt found")
                await self.db.update_file(file_id, status='pending')
                return False
            
            # 5. Prepare document entries for LLM summarization
            doc_entries = []
            for doc in docs:
                entry = {
                    'created_at': doc['created_at'],
                    'filename': doc['filename'],
                    'summary': doc.get('summary'),
                    'structured_data': doc.get('structured_data'),
                    'document_type': doc.get('document_type')
                }
                doc_entries.append(entry)
            
            # 6. Call MCP tool to generate summary
            logger.info(f"Calling summarize_file for file {file_id} with {len(doc_entries)} documents")
            
            result = summarize_file(
                documents=doc_entries,
                file_type=None,  # No longer using file_type
                tags=tags,
                prompt=prompt['prompt_text'],
                bedrock_client=self.bedrock
            )
            
            # 7. Update file record with aggregated content AND summary
            await self.db.update_file(
                file_id,
                aggregated_content=aggregated_content,
                summary_text=result['summary'],
                summary_metadata=result.get('metadata', {}),
                prompt_version=prompt['id'],
                status='generated',
                last_generated_at=datetime.now()
            )
            
            logger.info(
                f"Successfully generated summary for file {file_id} "
                f"(confidence: {result.get('confidence', 0.0):.2f})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Error generating file {file_id}: {e}", exc_info=True)
            
            # Mark as pending to retry later
            await self.db.update_file(file_id, status='pending')
            
            return False
    
    async def get_documents(self, status, limit: int) -> List[dict]:
        """Not used by FileGeneratorWorker (we poll files table directly)."""
        return []
    
    async def process_document(self, doc: dict) -> bool:
        """Not used by FileGeneratorWorker (we process files, not documents)."""
        return True


async def main():
    """Main entry point for standalone execution."""
    settings = Settings()
    
    print("=" * 60)
    print("ALFRD File Generator Worker")
    print("=" * 60)
    print(f"Poll interval: {getattr(settings, 'file_generator_poll_interval', 15)}s")
    print(f"Concurrency: {getattr(settings, 'file_generator_workers', 2)}")
    print()
    
    worker = FileGeneratorWorker(settings)
    
    try:
        await worker.run()
    except KeyboardInterrupt:
        print("\nShutting down gracefully...")
        worker.stop()


if __name__ == "__main__":
    asyncio.run(main())