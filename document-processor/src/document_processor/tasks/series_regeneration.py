"""Series document regeneration worker.

Handles regenerating all documents in a series when the series prompt is updated.
"""

import asyncio
import json
import logging
from uuid import UUID
from typing import Dict, Any

from shared.database import AlfrdDatabase
from shared.event_logger import get_event_logger
from mcp_server.llm.client import LLMClient

logger = logging.getLogger(__name__)


async def _regenerate_single_document(
    doc_id: UUID,
    doc: Dict[str, Any],
    series_prompt: Dict[str, Any],
    db: AlfrdDatabase,
    llm_client: LLMClient
) -> None:
    """
    Re-extract a single document using the given series prompt.

    This is a simplified extraction that does NOT trigger scoring or evolution.
    Used during regeneration to apply a fixed prompt to all documents.
    """
    from mcp_server.tools.summarize_series import summarize_with_series_prompt

    # Extract schema from performance_metrics
    perf_metrics = series_prompt.get('performance_metrics', {})
    if isinstance(perf_metrics, str):
        perf_metrics = json.loads(perf_metrics)
    schema_def = perf_metrics.get('schema_definition', {})

    # Run extraction
    loop = asyncio.get_event_loop()
    series_extraction = await loop.run_in_executor(
        None,
        summarize_with_series_prompt,
        doc['extracted_text'],
        series_prompt['prompt_text'],
        schema_def,
        llm_client
    )

    # Update document with new extraction (using the FIXED prompt)
    await db.update_document(
        doc_id,
        structured_data=json.dumps(series_extraction),
        series_prompt_id=series_prompt['id'],
        extraction_method='series'
    )

    logger.debug(f"Regenerated {doc['filename']} with prompt {series_prompt['id']}")


async def regenerate_series_documents(
    series_id: UUID,
    db: AlfrdDatabase,
    llm_client: LLMClient
) -> int:
    """Regenerate all documents in series with latest prompt.
    
    This function:
    1. Gets the series and its active prompt
    2. Finds all documents in the series
    3. Re-extracts each document using the latest series prompt
    4. Updates the document's structured_data and series_prompt_id
    5. Marks regeneration as complete
    
    Args:
        series_id: UUID of the series to regenerate
        db: Database connection
        llm_client: Bedrock client for LLM calls
        
    Returns:
        Number of documents successfully regenerated
    """
    event_logger = get_event_logger(db)

    try:
        # Get series and verify it has an active prompt
        series = await db.get_series(series_id)
        if not series:
            logger.error(f"Series {series_id} not found")
            return 0

        if not series.get('active_prompt_id'):
            logger.warning(f"Series {series_id} has no active prompt, skipping regeneration")
            return 0

        series_prompt = await db.get_prompt(series['active_prompt_id'])
        if not series_prompt:
            logger.error(f"Series prompt {series['active_prompt_id']} not found")
            return 0

        # Get all documents in series
        documents = await db.get_series_documents(series_id)

        logger.info(
            f"🔄 Starting regeneration for series '{series['title']}' "
            f"({series_id}): {len(documents)} documents, "
            f"prompt v{series_prompt['version']}"
        )

        # Log regeneration start
        await event_logger.log_processing_event(
            entity_type='series',
            entity_id=series_id,
            event_type='regeneration_started',
            task_name='regenerate_series_documents',
            details={
                'series_title': series['title'],
                'document_count': len(documents),
                'prompt_id': str(series_prompt['id']),
                'prompt_version': series_prompt['version']
            }
        )
        
        regenerated = 0
        skipped = 0
        failed = 0
        
        for i, doc_dict in enumerate(documents, 1):
            doc_id = doc_dict['id']
            
            try:
                # Get current document state
                doc = await db.get_document(doc_id)
                if not doc:
                    logger.warning(f"Document {doc_id} not found, skipping")
                    failed += 1
                    continue
                
                # Skip if already using latest prompt
                if doc.get('series_prompt_id') == series_prompt['id']:
                    logger.debug(
                        f"[{i}/{len(documents)}] Document {doc['filename']} "
                        f"already using latest prompt, skipping"
                    )
                    skipped += 1
                    continue
                
                # Re-extract with latest series prompt (NO scoring - just extraction)
                logger.info(
                    f"[{i}/{len(documents)}] Regenerating {doc['filename']} "
                    f"(old prompt: {doc.get('series_prompt_id')}, "
                    f"new prompt: {series_prompt['id']})"
                )

                # Direct extraction without triggering scoring/evolution
                await _regenerate_single_document(
                    doc_id, doc, series_prompt, db, llm_client
                )
                regenerated += 1
                
                logger.info(f"  ✅ Regenerated successfully")
                
            except Exception as e:
                logger.error(f"  ❌ Failed to regenerate {doc_id}: {e}", exc_info=True)
                failed += 1
        
        # Mark regeneration complete
        await db.update_series(series_id, regeneration_pending=False)

        logger.info(
            f"✅ Series {series_id} regeneration complete: "
            f"{regenerated} regenerated, {skipped} skipped, {failed} failed"
        )

        # Log regeneration complete
        await event_logger.log_processing_event(
            entity_type='series',
            entity_id=series_id,
            event_type='regeneration_completed',
            task_name='regenerate_series_documents',
            details={
                'series_title': series['title'],
                'regenerated': regenerated,
                'skipped': skipped,
                'failed': failed,
                'prompt_id': str(series_prompt['id'])
            }
        )

        return regenerated

    except Exception as e:
        logger.error(f"❌ Series regeneration failed for {series_id}: {e}", exc_info=True)
        # Log regeneration failure
        await event_logger.log_processing_event(
            entity_type='series',
            entity_id=series_id,
            event_type='regeneration_failed',
            task_name='regenerate_series_documents',
            details={'error': str(e)}
        )
        raise