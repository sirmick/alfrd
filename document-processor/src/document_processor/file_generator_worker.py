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


class FileGeneratorWorker(BaseWorker):
    """Worker to generate summaries for file collections."""
    
    def __init__(self, settings: Settings):
        """Initialize file generator worker.
        
        Args:
            settings: Application settings
        """
        super().__init__(
            name="FileGeneratorWorker",
            source_status="pending",  # Not used (we poll files table)
            target_status="pending",   # Not used
            settings=settings
        )
        self.poll_interval = getattr(settings, 'file_generator_poll_interval', 15)
        self.concurrency = getattr(settings, 'file_generator_workers', 2)
        self.bedrock = BedrockClient(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_region=settings.aws_region
        )
    
    async def run(self):
        """Main loop: poll for files needing generation."""
        await self.db.initialize()
        
        self.logger.info(f"Starting {self.name} (poll interval: {self.poll_interval}s)")
        
        while self.running:
            try:
                # Get files that need generation
                files = await self.db.get_files_by_status(
                    statuses=['pending', 'outdated'],
                    limit=self.concurrency * 2
                )
                
                if files:
                    self.logger.info(f"Found {len(files)} files needing generation")
                    
                    # Process files in parallel (up to concurrency limit)
                    tasks = [
                        self.generate_file_summary(file_record)
                        for file_record in files[:self.concurrency]
                    ]
                    
                    results = await asyncio.gather(*tasks, return_exceptions=True)
                    
                    # Log results
                    for file_record, result in zip(files[:self.concurrency], results):
                        if isinstance(result, Exception):
                            self.logger.error(
                                f"Error generating file {file_record['id']}: {result}"
                            )
                        elif result:
                            self.logger.info(f"Successfully generated file {file_record['id']}")
                
                # Sleep before next poll
                await asyncio.sleep(self.poll_interval)
                
            except Exception as e:
                self.logger.error(f"Error in {self.name} loop: {e}", exc_info=True)
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
            
            self.logger.info(
                f"Generating summary for file {file_id} "
                f"({file_record['document_type']}: {file_record['tag_signature']})"
            )
            
            # 1. Fetch all documents in file (chronologically)
            docs = await self.db.get_file_documents(
                file_id,
                order_by='created_at ASC'
            )
            
            if not docs:
                self.logger.warning(f"File {file_id} has no documents, marking as generated")
                await self.db.update_file(
                    file_id,
                    summary_text="No documents in this file yet.",
                    summary_metadata={},
                    status='generated',
                    last_generated_at=datetime.now()
                )
                return True
            
            self.logger.info(f"Found {len(docs)} documents in file {file_id}")
            
            # 2. Get active file summarizer prompt
            prompt = await self.db.get_active_prompt('file_summarizer', None)
            
            if not prompt:
                self.logger.error("No active file_summarizer prompt found")
                await self.db.update_file(file_id, status='pending')
                return False
            
            # 3. Parse tags from JSONB
            tags = file_record.get('tags')
            if isinstance(tags, str):
                try:
                    tags = json.loads(tags)
                except:
                    tags = []
            elif not isinstance(tags, list):
                tags = []
            
            # 4. Prepare document entries for summarization
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
            
            # 5. Call MCP tool to generate summary
            self.logger.info(f"Calling summarize_file for file {file_id}")
            
            result = summarize_file(
                documents=doc_entries,
                file_type=file_record['document_type'],
                tags=tags,
                prompt=prompt['prompt_text'],
                bedrock_client=self.bedrock
            )
            
            # 6. Update file record
            await self.db.update_file(
                file_id,
                summary_text=result['summary'],
                summary_metadata=result.get('metadata', {}),
                prompt_version=prompt['id'],
                status='generated',
                last_generated_at=datetime.now()
            )
            
            self.logger.info(
                f"Successfully generated summary for file {file_id} "
                f"(confidence: {result.get('confidence', 0.0):.2f})"
            )
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error generating file {file_id}: {e}", exc_info=True)
            
            # Mark as pending to retry later
            await self.db.update_file(file_id, status='pending')
            
            return False
    
    async def process_document(self, doc: dict) -> bool:
        """Not used by FileGeneratorWorker (we process files, not documents)."""
        pass


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