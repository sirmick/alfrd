"""Document processing flow."""

from prefect import flow, get_run_logger
from uuid import UUID

from shared.database import AlfrdDatabase
from mcp_server.llm.bedrock import BedrockClient
from document_processor.tasks import (
    ocr_task,
    classify_task,
    score_classification_task,
    summarize_task,
    score_summary_task,
    file_task
)


@flow(name="Process Document", log_prints=True)
async def process_document_flow(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """
    Complete document processing pipeline.
    
    DAG: ocr → classify → [score_classification + summarize] →
         score_summary → file → completed
    """
    logger = get_run_logger()
    
    # Get document info for logging
    doc = await db.get_document(doc_id)
    filename = doc['filename'] if doc else str(doc_id)[:8]
    
    logger.info(f"📄 Processing: {filename} (ID: {doc_id})")
    
    # Step 1: OCR
    extracted_text = await ocr_task(doc_id, db)
    
    # Step 2: Classification
    classification = await classify_task(doc_id, extracted_text, db, bedrock_client)
    
    # Step 3: Score classification (background)
    import asyncio
    score_class_task = asyncio.create_task(
        score_classification_task(doc_id, classification, db, bedrock_client)
    )
    
    # Step 4: Summarization (serialized per-type internally)
    summary = await summarize_task(doc_id, db, bedrock_client)
    
    # Step 5: Score summary (background)
    score_summ_task = asyncio.create_task(
        score_summary_task(doc_id, db, bedrock_client)
    )
    
    # Step 6: File into series
    file_id = await file_task(doc_id, db, bedrock_client)
    
    # Wait for background scoring tasks to complete
    await score_class_task
    await score_summ_task
    
    # Step 7: Mark as completed
    from shared.types import DocumentStatus
    await db.update_document(doc_id, status=DocumentStatus.COMPLETED)
    
    logger.info(f"✅ Document {doc_id} processing complete (filed into {file_id})")
    return "completed"