"""Main orchestrator: monitors DB and launches flows."""

from prefect import flow, get_run_logger
import asyncio

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient
from document_processor.flows import (
    process_document_flow,
    generate_file_summary_flow
)

# Global semaphores for flow-level concurrency control
_document_flow_semaphore = None
_file_flow_semaphore = None


async def scan_inbox_and_create_pending(settings: Settings):
    """
    Scan inbox for new folders and create pending database entries.
    
    This function is called periodically by the orchestrator to detect
    new documents added to the inbox.
    """
    from document_processor.detector import FileDetector
    from shared.constants import META_JSON_FILENAME
    from datetime import datetime, timezone
    from uuid import UUID
    import json
    import shutil
    
    detector = FileDetector()
    inbox = settings.inbox_path
    
    if not inbox.exists():
        inbox.mkdir(parents=True, exist_ok=True)
        return 0
    
    folders = [f for f in inbox.iterdir() if f.is_dir()]
    if not folders:
        return 0
    
    # Get existing document IDs
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    try:
        all_docs = await db.list_documents(limit=10000)
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
            base_path = settings.documents_path / year_month
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
            
            new_count += 1
        
        return new_count
    
    finally:
        await db.close()


@flow(name="Orchestrator", log_prints=True)
async def main_orchestrator_flow(
    settings: Settings,
    run_once: bool = False
):
    """
    Main orchestrator: monitors DB and launches flows.
    
    Replaces worker polling architecture.
    Runs continuously unless run_once=True.
    """
    logger = get_run_logger()
    logger.info("Starting ALFRD orchestrator")
    
    # Initialize semaphores for flow-level concurrency control
    global _document_flow_semaphore, _file_flow_semaphore
    if _document_flow_semaphore is None:
        _document_flow_semaphore = asyncio.Semaphore(settings.prefect_max_document_flows)
        logger.info(f"Document flow concurrency limit: {settings.prefect_max_document_flows}")
    if _file_flow_semaphore is None:
        _file_flow_semaphore = asyncio.Semaphore(settings.prefect_max_file_flows)
        logger.info(f"File flow concurrency limit: {settings.prefect_max_file_flows}")
    
    # Initialize database
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    # Initialize Bedrock client (shared across flows)
    bedrock_client = BedrockClient(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_region=settings.aws_region
    )
    
    iteration = 0
    try:
        while True:
            iteration += 1
            logger.info(f"Orchestrator iteration {iteration}")
            
            # === Scan Inbox for New Documents ===
            # This ensures documents added via add-document script are picked up
            new_docs = await scan_inbox_and_create_pending(settings)
            if new_docs > 0:
                logger.info(f"📂 Registered {new_docs} new document(s) from inbox")
            
            # Initialize task lists
            tasks = []
            file_tasks = []
            
            # === Monitor Documents ===
            pending_docs = await db.get_documents_by_status(
                DocumentStatus.PENDING,
                limit=settings.prefect_max_document_flows * 2  # Fetch more than limit to queue up
            )
            
            if pending_docs:
                logger.info(f"Found {len(pending_docs)} pending documents")
                
                # Launch document processing flows as background tasks
                # Semaphore ensures max concurrent flows
                for doc in pending_docs:
                    async def process_with_semaphore(doc_id):
                        async with _document_flow_semaphore:
                            await process_document_flow(
                                doc_id=doc_id,
                                db=db,
                                bedrock_client=bedrock_client
                            )
                    
                    task = asyncio.create_task(process_with_semaphore(doc['id']))
                    tasks.append(task)
                
                logger.info(f"Queued {len(pending_docs)} document flows (max concurrent: {settings.prefect_max_document_flows})")
            
            # === Monitor Files ===
            # Query for pending and outdated files only
            # Do NOT query 'generating' - those are actively being processed
            # Files stuck in 'generating' for >5 minutes can be manually reset
            pending_files = await db.get_files_by_status(
                ['pending', 'outdated'],
                limit=20
            )
            
            if pending_files:
                logger.info(f"Found {len(pending_files)} files needing generation")
                
                # Launch file generation flows as background tasks
                # Semaphore ensures max concurrent flows
                file_tasks = []
                for file in pending_files:
                    # NOTE: Status updated to 'generating' INSIDE the flow (not here)
                    # This matches document workflow pattern
                    async def generate_with_semaphore(file_id):
                        async with _file_flow_semaphore:
                            await generate_file_summary_flow(
                                file_id=file_id,
                                db=db,
                                bedrock_client=bedrock_client
                            )
                    
                    task = asyncio.create_task(generate_with_semaphore(file['id']))
                    file_tasks.append(task)
                
                logger.info(f"Queued {len(pending_files)} file generation flows (max concurrent: {settings.prefect_max_file_flows})")
            
            # Exit if run-once mode
            if run_once:
                logger.info("Run-once mode: waiting for flows to complete")
                # Wait for all launched tasks to complete
                if tasks:
                    logger.info(f"Waiting for {len(tasks)} document tasks...")
                    await asyncio.gather(*tasks, return_exceptions=True)
                
                # CRITICAL: Check for files created by document tasks
                # Document processing might have created new files via file_task
                pending_files_after = await db.get_files_by_status(
                    ['pending', 'outdated'],
                    limit=20
                )
                
                if pending_files_after and not file_tasks:
                    logger.info(f"Found {len(pending_files_after)} files created during document processing")
                    file_tasks = []
                    for file in pending_files_after:
                        # NOTE: Status updated to 'generating' INSIDE the flow (not here)
                        # This matches document workflow pattern
                        async def generate_with_semaphore(file_id):
                            async with _file_flow_semaphore:
                                await generate_file_summary_flow(
                                    file_id=file_id,
                                    db=db,
                                    bedrock_client=bedrock_client
                                )
                        
                        task = asyncio.create_task(generate_with_semaphore(file['id']))
                        file_tasks.append(task)
                    
                    logger.info(f"Queued {len(pending_files_after)} file generation flows")
                
                if file_tasks:
                    logger.info(f"Waiting for {len(file_tasks)} file tasks...")
                    await asyncio.gather(*file_tasks, return_exceptions=True)
                break
            
            # Poll interval
            await asyncio.sleep(10)
    
    finally:
        await db.close()
        logger.info("Orchestrator shutdown complete")