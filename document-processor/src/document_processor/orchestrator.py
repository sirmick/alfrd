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
        
        # Recovery configuration
        self.recovery_interval_minutes = settings.recovery_check_interval_minutes
        self.stale_timeout_minutes = settings.stale_timeout_minutes
    
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
        """Main orchestration loop with periodic recovery."""
        await self.initialize()
        
        # Initial recovery on startup
        logger.info("🔍 Running startup recovery check...")
        recovered = await self.recover_stale_work()
        if recovered > 0:
            logger.warning(f"♻️ Startup recovery: {recovered} stuck items recovered")
        
        # Track all background tasks
        self.background_tasks = set()
        
        # Start periodic recovery task
        recovery_task = asyncio.create_task(self._periodic_recovery())
        
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
                
                # Process series needing regeneration
                await self._process_series_regenerations()
                
                # Process pending files
                await self._process_files()
                
                if run_once:
                    logger.info("Run-once mode: waiting for completion")
                    await asyncio.sleep(5)

                    # Check for files created during document processing
                    await self._process_files()

                    # Wait for ALL background tasks to complete (including scoring)
                    if self.background_tasks:
                        logger.info(f"Waiting for {len(self.background_tasks)} background tasks to complete...")
                        await asyncio.gather(*self.background_tasks, return_exceptions=True)
                        logger.info("✅ All background tasks complete")

                    # Process series regenerations AFTER scoring tasks complete
                    # (scoring tasks set regeneration_pending=TRUE)
                    logger.info("Checking for series needing regeneration...")
                    await self._process_series_regenerations()

                    # Wait for regeneration tasks if any were started
                    if self.background_tasks:
                        logger.info(f"Waiting for {len(self.background_tasks)} regeneration tasks...")
                        await asyncio.gather(*self.background_tasks, return_exceptions=True)

                    break
                
                await asyncio.sleep(10)
        
        finally:
            # Cancel recovery task
            recovery_task.cancel()
            try:
                await recovery_task
            except asyncio.CancelledError:
                pass
            
            # Wait for any remaining background tasks before closing DB
            if hasattr(self, 'background_tasks') and self.background_tasks:
                logger.info(f"Waiting for {len(self.background_tasks)} background tasks before shutdown...")
                await asyncio.gather(*self.background_tasks, return_exceptions=True)
            
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
        """Launch document processing workers for ALL processable states."""
        # Get documents in any non-terminal state
        statuses_to_process = ['pending', 'ocr_completed', 'classified', 'summarized', 'filed', 'series_summarized']
        
        docs = []
        for status in statuses_to_process:
            batch = await self.db.get_documents_by_status(
                status,
                limit=self.settings.prefect_max_document_flows * 2
            )
            docs.extend(batch)
        
        if not docs:
            return
        
        logger.info(f"Found {len(docs)} processable documents (states: {statuses_to_process})")
        
        # Launch workers with semaphore control
        for doc in docs:
            task = asyncio.create_task(
                self._process_document_with_semaphore(doc['id'])
            )
            # Track background task
            self.background_tasks.add(task)
            # Remove from set when done
            task.add_done_callback(self.background_tasks.discard)
        
        logger.info(f"Queued {len(docs)} document workers")
    
    async def _process_document_with_semaphore(self, doc_id: UUID):
        """Process document with flow-level concurrency control."""
        async with self.doc_flow_sem:
            await self._process_document(doc_id)
    
    async def _process_document(self, doc_id: UUID):
        """Resume document processing pipeline from current state."""
        from document_processor.tasks.document_tasks import (
            ocr_step, classify_step, score_classification_step,
            summarize_step, score_summary_step, series_summarize_step,
            score_series_extraction_step, file_step
        )
        
        try:
            doc = await self.db.get_document(doc_id)
            status = doc['status']
            logger.info(f"📄 Processing: {doc['filename']} ({doc_id}) from status={status}")
            
            extracted_text = None
            classification = None
            
            # Step 1: OCR (if needed)
            if status == 'pending':
                extracted_text = await ocr_step(doc_id, self.db)
                doc = await self.db.get_document(doc_id)  # Refresh
                status = doc['status']
            else:
                extracted_text = doc.get('extracted_text')
            
            # Step 2: Classification (if needed)
            if status in ['pending', 'ocr_completed']:
                classification = await classify_step(
                    doc_id, extracted_text, self.db, self.bedrock
                )
                
                # Step 3: Score classification (background)
                asyncio.create_task(
                    score_classification_step(doc_id, classification, self.db, self.bedrock)
                )
                
                doc = await self.db.get_document(doc_id)  # Refresh
                status = doc['status']
            
            # Step 4: Summarization (if needed)
            if status in ['pending', 'ocr_completed', 'classified']:
                summary = await summarize_step(doc_id, self.db, self.bedrock)
                
                # Step 5: Score summary (background)
                asyncio.create_task(
                    score_summary_step(doc_id, self.db, self.bedrock)
                )
                
                doc = await self.db.get_document(doc_id)  # Refresh
                status = doc['status']
            
            # Step 6: File into series (if needed) - MUST run before series summarization
            if status in ['pending', 'ocr_completed', 'classified', 'summarized']:
                file_id = await file_step(doc_id, self.db, self.bedrock)
                logger.info(f"✅ Document {doc_id} filed into {file_id}")
                doc = await self.db.get_document(doc_id)  # Refresh
                status = doc['status']
            
            # Step 7: Series-specific summarization (if needed and document has series)
            # This runs AFTER file_step creates the series
            if status in ['pending', 'ocr_completed', 'classified', 'summarized', 'filed']:
                await series_summarize_step(doc_id, self.db, self.bedrock)
                
                # Step 7b: Score series extraction (background)
                asyncio.create_task(
                    score_series_extraction_step(doc_id, self.db, self.bedrock)
                )
                
                doc = await self.db.get_document(doc_id)  # Refresh
                status = doc['status']
            
            # Step 8: Mark completed (runs for series_summarized or filed status)
            if status in ['filed', 'series_summarized']:
                await self.db.update_document(doc_id, status=DocumentStatus.COMPLETED)
                logger.info(f"✅ Document {doc_id} marked as completed")
            
            logger.info(f"✅ Document {doc_id} complete")
            
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
        
        for file in files:
            task = asyncio.create_task(
                self._process_file_with_semaphore(file['id'])
            )
            # Track background task
            self.background_tasks.add(task)
            # Remove from set when done
            task.add_done_callback(self.background_tasks.discard)
        
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
    
    async def _process_series_regenerations(self):
        """Process series marked for regeneration."""
        from document_processor.tasks.series_regeneration import regenerate_series_documents
        
        # Find series with regeneration_pending = TRUE
        series_list = await self.db.list_series(limit=100)
        pending_series = [s for s in series_list if s.get('regeneration_pending')]
        
        if not pending_series:
            return
        
        logger.info(f"🔄 Found {len(pending_series)} series needing regeneration")
        
        for series in pending_series:
            try:
                logger.info(f"Starting regeneration for series: {series['title']}")
                regenerated = await regenerate_series_documents(
                    series['id'],
                    self.db,
                    self.bedrock
                )
                logger.info(f"✅ Regenerated {regenerated} documents in series '{series['title']}'")
            except Exception as e:
                logger.error(f"❌ Failed to regenerate series {series['id']}: {e}", exc_info=True)
    
    async def _periodic_recovery(self):
        """Background task that runs recovery check every X minutes."""
        while True:
            try:
                await asyncio.sleep(self.recovery_interval_minutes * 60)
                
                logger.info(f"🔍 Running periodic recovery check (every {self.recovery_interval_minutes} min)...")
                recovered = await self.recover_stale_work()
                
                if recovered > 0:
                    logger.warning(
                        f"♻️ Periodic recovery: {recovered} stuck items recovered and queued for retry"
                    )
                else:
                    logger.debug("✅ No stuck work found")
                    
            except asyncio.CancelledError:
                logger.info("Recovery task cancelled")
                raise
            except Exception as e:
                logger.error(f"❌ Recovery check failed: {e}", exc_info=True)
    
    async def recover_stale_work(self) -> int:
        """Reset stuck documents and files to retry state.
        
        Returns:
            Number of items recovered
        """
        recovered_count = 0
        
        # Recover stale documents
        stale_docs = await self.db.get_stale_documents(timeout_minutes=self.stale_timeout_minutes)
        
        for doc in stale_docs:
            # Calculate how long it's been stuck
            from datetime import datetime, timezone
            stuck_minutes = (datetime.now(timezone.utc) - doc['updated_at']).total_seconds() / 60
            
            logger.warning({
                "event": "stale_document_detected",
                "entity_type": "document",
                "document_id": str(doc['id']),
                "filename": doc['filename'],
                "status": doc['status'],
                "stuck_duration_minutes": round(stuck_minutes, 1),
                "retry_count": doc['retry_count'],
                "max_retries": doc['max_retries'],
                "timeout_threshold_minutes": self.stale_timeout_minutes,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            await self.db.reset_document_for_retry(
                doc['id'],
                error_message=f"Recovered from stale {doc['status']} state (stuck for {stuck_minutes:.1f} min)"
            )
            recovered_count += 1
        
        # Recover stale files
        stale_files = await self.db.get_stale_files(timeout_minutes=self.stale_timeout_minutes)
        
        for file in stale_files:
            from datetime import datetime, timezone
            stuck_minutes = (datetime.now(timezone.utc) - file['updated_at']).total_seconds() / 60
            
            logger.warning({
                "event": "stale_file_detected",
                "entity_type": "file",
                "file_id": str(file['id']),
                "status": file['status'],
                "stuck_duration_minutes": round(stuck_minutes, 1),
                "retry_count": file['retry_count'],
                "max_retries": file.get('max_retries', 3),
                "timeout_threshold_minutes": self.stale_timeout_minutes,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            await self.db.reset_file_for_retry(
                file['id'],
                error_message=f"Recovered from stale {file['status']} state (stuck for {stuck_minutes:.1f} min)"
            )
            recovered_count += 1
        
        return recovered_count