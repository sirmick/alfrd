"""Main document processing loop using self-improving worker pool architecture."""

import argparse
import asyncio
from pathlib import Path
import sys
import logging

# Standalone PYTHONPATH setup - add both project root and src directory
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root for shared
sys.path.insert(0, str(Path(__file__).parent.parent))  # src for document_processor

from shared.config import Settings
from document_processor.workers import WorkerPool
from document_processor.ocr_worker import OCRWorker
from document_processor.classifier_worker import ClassifierWorker
from document_processor.scorer_workers import ClassifierScorerWorker, SummarizerScorerWorker
from document_processor.summarizer_worker import SummarizerWorker

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def scan_inbox_and_create_pending_documents(settings: Settings):
    """
    Scan inbox for new folders and create pending database entries.
    
    This allows workers to pick them up and process them.
    Skips folders that are already registered in the database.
    """
    from document_processor.detector import FileDetector
    from document_processor.storage import DocumentStorage
    from shared.constants import META_JSON_FILENAME
    import json
    import duckdb
    
    detector = FileDetector()
    storage = DocumentStorage(settings)
    
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
    conn = duckdb.connect(str(settings.database_path))
    try:
        existing_ids = set(row[0] for row in conn.execute("SELECT id FROM documents").fetchall())
    finally:
        conn.close()
    
    logger.info(f"Found {len(folders)} document folders in inbox, {len(existing_ids)} already registered")
    
    new_count = 0
    for folder_path in folders:
        try:
            # Validate folder
            is_valid, error, meta = detector.validate_document_folder(folder_path)
            
            if not is_valid:
                logger.error(f"Invalid folder {folder_path.name}: {error}")
                continue
            
            doc_id = meta.get('id')
            
            # Skip if already registered
            if doc_id in existing_ids:
                logger.debug(f"Document {doc_id} already registered, skipping")
                continue
            
            # Store document folder (creates DB entry with PENDING status)
            extracted_documents = []
            llm_formatted = {
                'full_text': '',
                'blocks_by_document': None,
                'document_count': 0,
                'total_chars': 0,
                'avg_confidence': 0.0
            }
            
            await storage.store_document_folder(
                folder_path=folder_path,
                doc_id=doc_id,
                meta=meta,
                extracted_documents=extracted_documents,
                llm_formatted=llm_formatted
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
    print(f"💾 Database: {settings.database_path}")
    print(f"📁 Documents: {settings.documents_path}")
    print()
    print(f"⚙️  Worker Configuration:")
    print(f"   OCR Workers: {settings.ocr_workers} (poll every {settings.ocr_poll_interval}s)")
    print(f"   Classifier Workers: {settings.classifier_workers} (poll every {settings.classifier_poll_interval}s)")
    print(f"   Classifier Scorer Workers: {settings.classifier_scorer_workers} (poll every {settings.classifier_scorer_poll_interval}s)")
    print(f"   Summarizer Workers: {settings.summarizer_workers} (poll every {settings.summarizer_poll_interval}s)")
    print(f"   Summarizer Scorer Workers: {settings.summarizer_scorer_workers} (poll every {settings.summarizer_scorer_poll_interval}s)")
    print()
    print(f"🧠 Prompt Evolution:")
    print(f"   Classifier Max Words: {settings.classifier_prompt_max_words}")
    print(f"   Min Docs for Scoring: {settings.min_documents_for_scoring}")
    print(f"   Update Threshold: {settings.prompt_update_threshold}")
    print()
    
    logger.info(f"Inbox: {settings.inbox_path}")
    logger.info(f"Database: {settings.database_path}")
    logger.info(f"Documents: {settings.documents_path}")
    
    # Step 1: Scan inbox and create pending document entries
    print("📂 Scanning inbox for new documents...")
    await scan_inbox_and_create_pending_documents(settings)
    print()
    
    # Step 2: Create worker pool with new self-improving pipeline
    print("🔧 Starting self-improving worker pool...")
    pool = WorkerPool()
    
    # Add workers in pipeline order:
    # 1. OCR - Extract text from documents
    pool.add_worker(OCRWorker(settings))
    
    # 2. Classifier - Classify documents using DB prompts (can suggest new types)
    pool.add_worker(ClassifierWorker(settings))
    
    # 3. Classifier Scorer - Score classification and evolve prompt
    pool.add_worker(ClassifierScorerWorker(settings))
    
    # 4. Summarizer - Generic summarization using type-specific DB prompts
    pool.add_worker(SummarizerWorker(settings))
    
    # 5. Summarizer Scorer - Score summary and evolve prompt
    pool.add_worker(SummarizerScorerWorker(settings))
    
    print()
    print("=" * 80)
    print("✅ Self-improving worker pipeline started!")
    print("   Pipeline: OCR → Classify → Score → Summarize → Score → Complete")
    print("   Prompts evolve automatically based on performance feedback")
    print("   Press Ctrl+C to stop.")
    print("=" * 80)
    print()
    logger.info("Self-improving worker pool started with 5 workers")
    
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
                        await scan_inbox_and_create_pending_documents(settings)
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ALFRD Document Processor")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process all pending documents and exit (don't run continuously)"
    )
    args = parser.parse_args()
    
    asyncio.run(main(run_once=args.once))