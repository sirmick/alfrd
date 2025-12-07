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
            
            # Initialize task lists
            tasks = []
            file_tasks = []
            
            # === Monitor Documents ===
            pending_docs = await db.get_documents_by_status(
                DocumentStatus.PENDING,
                limit=2  # Limit to 2 for easier debugging
            )
            
            if pending_docs:
                logger.info(f"Found {len(pending_docs)} pending documents")
                
                # Launch document processing flows as background tasks
                for doc in pending_docs:
                    task = asyncio.create_task(
                        process_document_flow(
                            doc_id=doc['id'],
                            db=db,
                            bedrock_client=bedrock_client
                        )
                    )
                    tasks.append(task)
                
                logger.info(f"Launched {len(pending_docs)} document flows as background tasks")
            
            # === Monitor Files ===
            pending_files = await db.get_files_by_status(
                ['pending', 'outdated'],
                limit=20
            )
            
            if pending_files:
                logger.info(f"Found {len(pending_files)} files needing generation")
                
                # Launch file generation flows as background tasks
                file_tasks = []
                for file in pending_files:
                    task = asyncio.create_task(
                        generate_file_summary_flow(
                            file_id=file['id'],
                            db=db,
                            bedrock_client=bedrock_client
                        )
                    )
                    file_tasks.append(task)
                
                logger.info(f"Launched {len(pending_files)} file generation flows as background tasks")
            
            # Exit if run-once mode
            if run_once:
                logger.info("Run-once mode: waiting for flows to complete")
                # Wait for all launched tasks to complete
                if tasks:
                    logger.info(f"Waiting for {len(tasks)} document tasks...")
                    await asyncio.gather(*tasks, return_exceptions=True)
                if file_tasks:
                    logger.info(f"Waiting for {len(file_tasks)} file tasks...")
                    await asyncio.gather(*file_tasks, return_exceptions=True)
                break
            
            # Poll interval
            await asyncio.sleep(10)
    
    finally:
        await db.close()
        logger.info("Orchestrator shutdown complete")