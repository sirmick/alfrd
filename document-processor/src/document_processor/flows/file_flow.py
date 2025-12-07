"""File generation flow (separate from document processing)."""

from prefect import flow, get_run_logger
from uuid import UUID

from shared.database import AlfrdDatabase
from mcp_server.llm.bedrock import BedrockClient
from document_processor.tasks import generate_file_summary_task


@flow(name="Generate File Summary", log_prints=True)
async def generate_file_summary_flow(
    file_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """
    Generate summary for a file collection.
    
    This is a SEPARATE flow from document processing.
    Limited to 2 concurrent executions via Prefect.
    """
    logger = get_run_logger()
    logger.info(f"Generating file summary for {file_id}")
    
    summary = await generate_file_summary_task(file_id, db, bedrock_client)
    
    logger.info(f"File {file_id} summary generated")
    return summary