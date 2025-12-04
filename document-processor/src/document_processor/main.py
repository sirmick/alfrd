"""Main document processing loop using self-improving worker pool architecture."""

import argparse
import asyncio
from pathlib import Path
from datetime import datetime, timezone
import sys
import logging

# Standalone PYTHONPATH setup - add both project root and src directory
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root for shared
sys.path.insert(0, str(Path(__file__).parent.parent))  # src for document_processor

from shared.config import Settings
from shared.database import AlfrdDatabase
from document_processor.workers import WorkerPool
from document_processor.ocr_worker import OCRWorker
from document_processor.classifier_worker import ClassifierWorker
from document_processor.scorer_workers import ClassifierScorerWorker, SummarizerScorerWorker
from document_processor.summarizer_worker import SummarizerWorker
from document_processor.file_generator_worker import FileGeneratorWorker

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def scan_inbox_and_create_pending_documents(settings: Settings, db: AlfrdDatabase):
    """
    Scan inbox for new folders and create pending database entries.
    
    This allows workers to pick them up and process them.
    Skips folders that are already registered in the database.
    """
    from document_processor.detector import FileDetector
    from shared.constants import META_JSON_FILENAME
    from shared.types import DocumentStatus
    from uuid import UUID
    import json
    import shutil
    
    detector = FileDetector()
    
    inbox = settings.inbox_path
    
    if not inbox.exists():
        logger.warning(f"Inbox does not exist: {inbox}")
        inbox.mkdir(parents=True, exist_ok=True)
        logger.info(f"Created inbox directory: {inbox}")
        return
    
    # Get all folders in inbox
    folders = [f for f in inbox.iterdir() if f.is_dir()]
    
    if not folders:
        logger.debug("No document folders found in inbox")
        return
    
    # Get list of already registered document IDs
    all_docs = await db.list_documents(limit=10000)
    existing_ids = set(doc['id'] for doc in all_docs)
    
    logger.info(f"Found {len(folders)} document folders in inbox, {len(existing_ids)} already registered")
    
    new_count = 0
    for folder_path in folders:
        try:
            # Validate folder
            is_valid, error, meta = detector.validate_document_folder(folder_path)
            
            if not is_valid:
                logger.error(f"Invalid folder {folder_path.name}: {error}")
                continue
            
            doc_id = UUID(meta.get('id'))
            
            # Skip if already registered
            if doc_id in existing_ids:
                logger.debug(f"Document {doc_id} already registered, skipping")
                continue
            
            # Create storage paths (file organization only, no DB in this section)
            now = datetime.now(timezone.utc)
            year_month = now.strftime("%Y/%m")
            base_path = settings.documents_path / year_month
            raw_path = base_path / "raw" / str(doc_id)
            text_path = base_path / "text"
            meta_path = base_path / "meta"
            
            # Create directories
            for path in [raw_path, text_path, meta_path]:
                path.mkdir(parents=True, exist_ok=True)
            
            # Copy entire folder to raw storage
            shutil.copytree(folder_path, raw_path, dirs_exist_ok=True)
            
            # Save empty text file (will be filled by OCR worker)
            text_file = text_path / f"{doc_id}.txt"
            text_file.write_text("")
            
            # Save detailed metadata
            detailed_meta = {
                'original_meta': meta,
                'processed_at': now.isoformat()
            }
            meta_file = meta_path / f"{doc_id}.json"
            meta_file.write_text(json.dumps(detailed_meta, indent=2))
            
            # Calculate total file size
            total_size = sum(f.stat().st_size for f in folder_path.rglob('*') if f.is_file())
            
            # Create document record in database using AlfrdDatabase class
            await db.create_document(
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
            
            logger.info(f"Registered new document {doc_id} in PENDING status for worker processing")
            new_count += 1
            
        except Exception as e:
            logger.error(f"Error registering folder {folder_path.name}: {e}", exc_info=True)
    
    if new_count > 0:
        logger.info(f"Registered {new_count} new document(s) for processing")
    else:
        logger.info("No new documents to register")


async def main(run_once: bool = False):
    """Main entry point for self-improving document processing pipeline.
    
    Args:
        run_once: If True, exit after processing all documents (no continuous polling)
    """
    print("\n" + "=" * 80)
    print("🚀 Document Processor - Self-Improving Worker Pool Mode")
    if run_once:
        print("   Mode: Run once and exit")
    print("=" * 80)
    
    logger.info(f"Starting document processor with self-improving worker pool (run_once={run_once})")
    
    settings = Settings()
    
    print(f"📂 Inbox: {settings.inbox_path}")
    print(f"💾 Database: {settings.database_url}")
    print(f"📁 Documents: {settings.documents_path}")
    print()
    print(f"⚙️  Worker Configuration:")
    print(f"   OCR Workers: {settings.ocr_workers} (poll every {settings.ocr_poll_interval}s)")
    print(f"   Classifier Workers: {settings.classifier_workers} (poll every {settings.classifier_poll_interval}s)")
    print(f"   Classifier Scorer Workers: {settings.classifier_scorer_workers} (poll every {settings.classifier_scorer_poll_interval}s)")
    print(f"   Summarizer Workers: {settings.summarizer_workers} (poll every {settings.summarizer_poll_interval}s)")
    print(f"   Summarizer Scorer Workers: {settings.summarizer_scorer_workers} (poll every {settings.summarizer_scorer_poll_interval}s)")
    print(f"   File Generator Workers: {getattr(settings, 'file_generator_workers', 2)} (poll every {getattr(settings, 'file_generator_poll_interval', 15)}s)")
    print()
    print(f"🧠 Prompt Evolution:")
    print(f"   Classifier Max Words: {settings.classifier_prompt_max_words}")
    print(f"   Min Docs for Scoring: {settings.min_documents_for_scoring}")
    print(f"   Update Threshold: {settings.prompt_update_threshold}")
    print()
    
    logger.info(f"Inbox: {settings.inbox_path}")
    logger.info(f"Database: {settings.database_url}")
    logger.info(f"Documents: {settings.documents_path}")
    
    # Initialize shared database connection pool
    print("🔌 Connecting to PostgreSQL database...")
    db = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=settings.db_pool_min_size,
        pool_max_size=settings.db_pool_max_size,
        pool_timeout=settings.db_pool_timeout
    )
    await db.initialize()
    logger.info("Database connection pool initialized")
    print()
    
    try:
        # Step 1: Scan inbox and create pending document entries
        print("📂 Scanning inbox for new documents...")
        await scan_inbox_and_create_pending_documents(settings, db)
        print()
        
        # Step 2: Create worker pool with new self-improving pipeline
        print("🔧 Starting self-improving worker pool...")
        pool = WorkerPool()
        
        # Add workers in pipeline order (all share the same database connection pool):
        # 1. OCR - Extract text from documents
        pool.add_worker(OCRWorker(settings, db))
        
        # 2. Classifier - Classify documents using DB prompts (can suggest new types)
        pool.add_worker(ClassifierWorker(settings, db))
        
        # 3. Classifier Scorer - Score classification and evolve prompt
        pool.add_worker(ClassifierScorerWorker(settings, db))
        
        # 4. Summarizer - Generic summarization using type-specific DB prompts
        pool.add_worker(SummarizerWorker(settings, db))
        
        # 5. Summarizer Scorer - Score summary and evolve prompt
        pool.add_worker(SummarizerScorerWorker(settings, db))
        
        # 6. File Generator - Generate summaries for file collections
        pool.add_worker(FileGeneratorWorker(settings, db))
        
        print()
        print("=" * 80)
        print("✅ Self-improving worker pipeline started!")
        print("   Pipeline: OCR → Classify → Score → Summarize → Score → Complete")
        print("   File Generator: Summarizes document collections")
        print("   Prompts evolve automatically based on performance feedback")
        print("   Press Ctrl+C to stop.")
        print("=" * 80)
        print()
        logger.info("Self-improving worker pool started with 6 workers")
        
        # Run worker pool with periodic inbox scanning
        try:
            if run_once:
                await pool.start_once()
            else:
                # Start workers
                worker_task = asyncio.create_task(pool.start())
                
                # Start periodic inbox scanner
                async def periodic_inbox_scan():
                    """Periodically scan inbox for new documents."""
                    while True:
                        await asyncio.sleep(10)  # Scan every 10 seconds
                        try:
                            logger.debug("Periodic inbox scan...")
                            await scan_inbox_and_create_pending_documents(settings, db)
                        except Exception as e:
                            logger.error(f"Error in periodic inbox scan: {e}", exc_info=True)
                
                scanner_task = asyncio.create_task(periodic_inbox_scan())
                
                # Wait for either task (worker pool runs indefinitely)
                await asyncio.gather(worker_task, scanner_task, return_exceptions=True)
        except KeyboardInterrupt:
            print("\n⏹️  Shutting down workers...")
            logger.info("Received shutdown signal")
            await pool.stop()
            print("👋 Document processor stopped")
            logger.info("Document processor stopped")
    finally:
        # Clean up database connection pool
        print("\n🔌 Closing database connection pool...")
        await db.close()
        logger.info("Database connection pool closed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ALFRD Document Processor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process all pending documents and exit (don't run continuously)"
    )
    args = parser.parse_args()
    
    asyncio.run(main(run_once=args.once))