"""Main document processing loop using worker pool architecture."""

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
from document_processor.workflow_worker import WorkflowWorker

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
    """
    from document_processor.detector import FileDetector
    from document_processor.storage import DocumentStorage
    from shared.constants import META_JSON_FILENAME
    import json
    
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
        logger.info("No document folders found in inbox")
        return
    
    logger.info(f"Found {len(folders)} document folders to register")
    
    for folder_path in folders:
        try:
            # Validate folder
            is_valid, error, meta = detector.validate_document_folder(folder_path)
            
            if not is_valid:
                logger.error(f"Invalid folder {folder_path.name}: {error}")
                continue
            
            doc_id = meta.get('id')
            
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
            
            logger.info(f"Registered document {doc_id} in PENDING status for worker processing")
            
        except Exception as e:
            logger.error(f"Error registering folder {folder_path.name}: {e}", exc_info=True)


async def main():
    """Main entry point for worker-based document processing."""
    print("\n" + "=" * 80)
    print("🚀 Document Processor - Worker Pool Mode")
    print("=" * 80)
    
    logger.info("Starting document processor with worker pool")
    
    settings = Settings()
    
    print(f"📂 Inbox: {settings.inbox_path}")
    print(f"💾 Database: {settings.database_path}")
    print(f"📁 Documents: {settings.documents_path}")
    print()
    print(f"⚙️  Worker Configuration:")
    print(f"   OCR Workers: {settings.ocr_workers} (poll every {settings.ocr_poll_interval}s)")
    print(f"   Classifier Workers: {settings.classifier_workers} (poll every {settings.classifier_poll_interval}s)")
    print(f"   Workflow Workers: {settings.workflow_workers} (poll every {settings.workflow_poll_interval}s)")
    print()
    
    logger.info(f"Inbox: {settings.inbox_path}")
    logger.info(f"Database: {settings.database_path}")
    logger.info(f"Documents: {settings.documents_path}")
    
    # Step 1: Scan inbox and create pending document entries
    print("📂 Scanning inbox for new documents...")
    await scan_inbox_and_create_pending_documents(settings)
    print()
    
    # Step 2: Create worker pool
    print("🔧 Starting worker pool...")
    pool = WorkerPool()
    
    # Add workers
    pool.add_worker(OCRWorker(settings))
    pool.add_worker(ClassifierWorker(settings))
    pool.add_worker(WorkflowWorker(settings))
    
    print()
    print("=" * 80)
    print("✅ Workers started! Press Ctrl+C to stop.")
    print("=" * 80)
    print()
    logger.info("Worker pool started")
    
    # Run worker pool
    try:
        await pool.start()
    except KeyboardInterrupt:
        print("\n⏹️  Shutting down workers...")
        logger.info("Received shutdown signal")
        await pool.stop()
        print("👋 Document processor stopped")
        logger.info("Document processor stopped")


if __name__ == "__main__":
    asyncio.run(main())