"""Simple asyncio-based orchestrator (replaces Prefect flows)."""

import asyncio
import logging
from pathlib import Path
from typing import Optional
from uuid import UUID

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient

logger = logging.getLogger(__name__)


class SimpleOrchestrator:
    """Simple polling orchestrator with asyncio concurrency control."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db: Optional[AlfrdDatabase] = None
        self.bedrock: Optional[BedrockClient] = None
        
        # Semaphores for concurrency control (same as before)
        self.textract_sem = asyncio.Semaphore(settings.prefect_textract_workers)
        self.bedrock_sem = asyncio.Semaphore(settings.prefect_bedrock_workers)
        self.file_sem = asyncio.Semaphore(settings.prefect_file_generation_workers)
        
        # Flow-level semaphores
        self.doc_flow_sem = asyncio.Semaphore(settings.prefect_max_document_flows)
        self.file_flow_sem = asyncio.Semaphore(settings.prefect_max_file_flows)
    
    async def initialize(self):
        """Initialize database and Bedrock client."""
        self.db = AlfrdDatabase(self.settings.database_url)
        await self.db.initialize()
        
        self.bedrock = BedrockClient(
            aws_access_key_id=self.settings.aws_access_key_id,
            aws_secret_access_key=self.settings.aws_secret_access_key,
            aws_region=self.settings.aws_region
        )
        
        logger.info("✅ Orchestrator initialized")
    
    async def run(self, run_once: bool = False):
        """Main orchestration loop."""
        await self.initialize()
        
        try:
            iteration = 0
            while True:
                iteration += 1
                logger.info(f"🔄 Orchestrator iteration {iteration}")
                
                # Scan inbox for new documents
                new_count = await self._scan_inbox()
                if new_count > 0:
                    logger.info(f"📂 Registered {new_count} new documents from inbox")
                
                # Process pending documents
                await self._process_documents()
                
                # Process pending files
                await self._process_files()
                
                if run_once:
                    logger.info("Run-once mode: waiting for completion")
                    await asyncio.sleep(5)
                    
                    # Check for files created during document processing
                    await self._process_files()
                    break
                
                await asyncio.sleep(10)
        
        finally:
            if self.db:
                await self.db.close()
            logger.info("Orchestrator shutdown complete")
    
    async def _scan_inbox(self) -> int:
        """Scan inbox for new folders and create pending documents."""
        from document_processor.detector import FileDetector
        from shared.constants import META_JSON_FILENAME
        from datetime import datetime, timezone
        from uuid import UUID
        import json
        import shutil
        
        detector = FileDetector()
        inbox = self.settings.inbox_path
        
        if not inbox.exists():
            inbox.mkdir(parents=True, exist_ok=True)
            return 0
        
        folders = [f for f in inbox.iterdir() if f.is_dir()]
        if not folders:
            return 0
        
        # Get existing document IDs
        all_docs = await self.db.list_documents(limit=10000)
        existing_ids = set(doc['id'] for doc in all_docs)
        
        new_count = 0
        for folder_path in folders:
            is_valid, error, meta = detector.validate_document_folder(folder_path)
            
            if not is_valid:
                continue
            
            doc_id = UUID(meta.get('id'))
            
            if doc_id in existing_ids:
                continue
            
            # Create storage paths
            now = datetime.now(timezone.utc)
            year_month = now.strftime("%Y/%m")
            base_path = self.settings.documents_path / year_month
            raw_path = base_path / "raw" / str(doc_id)
            text_path = base_path / "text"
            meta_path = base_path / "meta"
            
            for path in [raw_path, text_path, meta_path]:
                path.mkdir(parents=True, exist_ok=True)
            
            # Copy folder
            shutil.copytree(folder_path, raw_path, dirs_exist_ok=True)
            
            # Create empty text file
            text_file = text_path / f"{doc_id}.txt"
            text_file.write_text("")
            
            # Save metadata
            detailed_meta = {
                'original_meta': meta,
                'processed_at': now.isoformat()
            }
            meta_file = meta_path / f"{doc_id}.json"
            meta_file.write_text(json.dumps(detailed_meta, indent=2))
            
            # Calculate size
            total_size = sum(
                f.stat().st_size
                for f in folder_path.rglob('*')
                if f.is_file()
            )
            
            # Create document record
            await self.db.create_document(
                doc_id=doc_id,
                filename=folder_path.name,
                original_path=str(folder_path),
                file_type='folder',
                file_size=total_size,
                status=DocumentStatus.PENDING,
                raw_document_path=str(raw_path),
                extracted_text_path=str(text_file),
                metadata_path=str(meta_file),
                folder_path=str(folder_path)
            )
            
            new_count += 1
        
        return new_count
    
    async def _process_documents(self):
        """Launch document processing workers."""
        docs = await self.db.get_documents_by_status(
            DocumentStatus.PENDING,
            limit=self.settings.prefect_max_document_flows * 2
        )
        
        if not docs:
            return
        
        logger.info(f"Found {len(docs)} pending documents")
        
        # Launch workers with semaphore control
        tasks = []
        for doc in docs:
            task = asyncio.create_task(
                self._process_document_with_semaphore(doc['id'])
            )
            tasks.append(task)
        
        logger.info(f"Queued {len(docs)} document workers")
        
        # Don't wait - let them run in background
        # (run_once mode waits in main loop)
    
    async def _process_document_with_semaphore(self, doc_id: UUID):
        """Process document with flow-level concurrency control."""
        async with self.doc_flow_sem:
            await self._process_document(doc_id)
    
    async def _process_document(self, doc_id: UUID):
        """Complete document processing pipeline."""
        from document_processor.tasks.document_tasks import (
            ocr_step, classify_step, score_classification_step,
            summarize_step, score_summary_step, file_step
        )
        
        try:
            doc = await self.db.get_document(doc_id)
            logger.info(f"📄 Processing: {doc['filename']} ({doc_id})")
            
            # Step 1: OCR
            extracted_text = await ocr_step(doc_id, self.db)
            
            # Step 2: Classification
            classification = await classify_step(
                doc_id, extracted_text, self.db, self.bedrock
            )
            
            # Step 3: Score classification (background)
            asyncio.create_task(
                score_classification_step(doc_id, classification, self.db, self.bedrock)
            )
            
            # Step 4: Summarization
            summary = await summarize_step(doc_id, self.db, self.bedrock)
            
            # Step 5: Score summary (background)
            asyncio.create_task(
                score_summary_step(doc_id, self.db, self.bedrock)
            )
            
            # Step 6: File into series
            file_id = await file_step(doc_id, self.db, self.bedrock)
            
            # Step 7: Mark completed
            await self.db.update_document(doc_id, status=DocumentStatus.COMPLETED)
            
            logger.info(f"✅ Document {doc_id} complete (filed into {file_id})")
            
        except Exception as e:
            logger.error(f"❌ Document {doc_id} failed: {e}", exc_info=True)
            # Error already handled in task functions
    
    async def _process_files(self):
        """Launch file generation workers."""
        files = await self.db.get_files_by_status(
            ['pending', 'outdated'],
            limit=20
        )
        
        if not files:
            return
        
        logger.info(f"Found {len(files)} pending files")
        
        tasks = []
        for file in files:
            task = asyncio.create_task(
                self._process_file_with_semaphore(file['id'])
            )
            tasks.append(task)
        
        logger.info(f"Queued {len(files)} file workers")
    
    async def _process_file_with_semaphore(self, file_id: UUID):
        """Process file with flow-level concurrency control."""
        async with self.file_flow_sem:
            await self._process_file(file_id)
    
    async def _process_file(self, file_id: UUID):
        """Generate file summary."""
        from document_processor.tasks.document_tasks import generate_file_summary_step
        
        try:
            logger.info(f"📁 Generating file summary {file_id}")
            
            # Mark as generating
            await self.db.update_file(file_id, status='generating')
            
            # Generate summary
            await generate_file_summary_step(file_id, self.db, self.bedrock)
            
            logger.info(f"✅ File {file_id} complete")
            
        except Exception as e:
            logger.error(f"❌ File {file_id} failed: {e}", exc_info=True)
            # Error already handled in task function