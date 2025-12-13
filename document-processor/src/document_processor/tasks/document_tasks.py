"""Document processing tasks with asyncio concurrency control."""

from uuid import UUID
import logging
import asyncio
import time
from typing import Dict, Any
import json
from pathlib import Path

from shared.database import AlfrdDatabase
from shared.types import DocumentStatus, PromptType
from shared.config import Settings
from shared.event_logger import EventLogger, get_event_logger
from mcp_server.llm.bedrock import BedrockClient
from document_processor.utils.locks import document_type_lock, series_prompt_lock

logger = logging.getLogger(__name__)

# Load settings for configurable worker limits
_settings = Settings()

# Asyncio semaphores for concurrency enforcement (works without Prefect Server)
# These ensure limits are respected even in standalone/dev mode
# Configured via environment variables
_textract_semaphore = asyncio.Semaphore(_settings.prefect_textract_workers)
_bedrock_semaphore = asyncio.Semaphore(_settings.prefect_bedrock_workers)
_file_gen_semaphore = asyncio.Semaphore(_settings.prefect_file_generation_workers)

# In-memory locks for series prompt creation (one process, asyncio coordination)
# NOTE: Series prompt locks now use PostgreSQL advisory locks via series_prompt_lock()
# This ensures cross-task safety even with concurrent asyncio tasks


async def ocr_step(doc_id: UUID, db: AlfrdDatabase) -> str:
    """
    Extract text using AWS Textract.
    
    Limited to 3 concurrent executions via asyncio semaphore.
    """
    async with _textract_semaphore:
        return await _ocr_task_impl(doc_id, db)


async def _ocr_task_impl(doc_id: UUID, db: AlfrdDatabase) -> str:
    """Implementation of OCR task (extracted for semaphore wrapping)."""
    from document_processor.extractors.aws_textract import TextractExtractor
    from document_processor.extractors.text import TextExtractor
    from shared.constants import META_JSON_FILENAME
    from shared.database import utc_now

    event_logger = get_event_logger(db)

    doc = await db.get_document(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")

    old_status = doc.get('status')
    await db.update_document(
        doc_id,
        status=DocumentStatus.OCR_IN_PROGRESS,
        processing_started_at=utc_now()
    )

    # Log state transition
    await event_logger.log_state_change(
        entity_type='document',
        entity_id=doc_id,
        old_status=old_status,
        new_status=DocumentStatus.OCR_IN_PROGRESS,
        task_name='ocr_step',
        details={'filename': doc.get('filename')}
    )
    
    logger.info(f"OCR processing document {doc_id}")
    
    try:
        # Get folder path
        folder_path = Path(doc['folder_path']) if doc['folder_path'] else Path(doc['original_path'])
        
        # Read meta.json
        meta_file = folder_path / META_JSON_FILENAME
        if not meta_file.exists():
            raise FileNotFoundError(f"No {META_JSON_FILENAME} found in {folder_path}")
        
        with open(meta_file, 'r') as f:
            meta = json.load(f)
        
        documents_list = meta.get('documents', [])
        if not documents_list:
            raise ValueError("No documents listed in meta.json")
        
        # Process each file
        all_extracted = []
        combined_text = []
        combined_blocks = []
        total_confidence = 0
        
        for doc_item in sorted(documents_list, key=lambda x: x.get('order', 0)):
            file_name = doc_item['file']
            file_type = doc_item['type']
            file_path = folder_path / file_name
            
            if not file_path.exists():
                logger.warning(f"File not found: {file_path}, skipping")
                continue
            
            # Extract based on type
            if file_type == 'image':
                extractor = TextractExtractor()
                extracted = await extractor.extract_text(file_path)
                # Cache status logged in aws_clients.py
            elif file_type == 'text':
                extractor = TextExtractor()
                extracted = await extractor.extract_text(file_path)
            else:
                logger.warning(f"Unknown file type '{file_type}' for {file_name}")
                continue
            
            # Add to combined data
            all_extracted.append({
                'file': file_name,
                'type': file_type,
                'order': doc_item.get('order', 0),
                'extracted_text': extracted['extracted_text'],
                'confidence': extracted['confidence'],
                'metadata': extracted['metadata']
            })
            
            # Build combined text
            combined_text.append(f"--- Document: {file_name} ---")
            combined_text.append(extracted['extracted_text'])
            combined_text.append("")  # Blank line separator
            
            # Add blocks if available (from Textract)
            if 'blocks' in extracted:
                combined_blocks.append({
                    'file': file_name,
                    'blocks': extracted['blocks']
                })
            
            total_confidence += extracted['confidence']
            
            logger.info(
                f"Extracted {len(extracted['extracted_text'])} chars from {file_name} "
                f"with {extracted['confidence']:.2%} confidence"
            )
        
        if not all_extracted:
            raise ValueError("No documents were successfully extracted")
        
        # Create LLM-optimized format
        avg_confidence = total_confidence / len(all_extracted)
        full_text = '\n'.join(combined_text).strip()
        
        llm_formatted = {
            'full_text': full_text,
            'blocks_by_document': combined_blocks if combined_blocks else None,
            'document_count': len(all_extracted),
            'total_chars': len(full_text),
            'avg_confidence': avg_confidence
        }
        
        # Store extracted data
        now = utc_now()
        year_month = now.strftime("%Y/%m")
        
        # Get documents path from settings
        from shared.config import Settings
        settings = Settings()
        base_path = settings.documents_path / year_month
        text_path = base_path / "text"
        text_path.mkdir(parents=True, exist_ok=True)
        
        # Save LLM-formatted data
        llm_file = text_path / f"{doc_id}_llm.json"
        llm_file.write_text(json.dumps(llm_formatted, indent=2))
        
        # Save full text
        text_file = text_path / f"{doc_id}.txt"
        text_file.write_text(full_text)
        
        # Update database
        await db.update_document(
            doc_id=doc_id,
            extracted_text=full_text,
            extracted_text_path=str(text_file),
            status=DocumentStatus.OCR_COMPLETED
        )

        # Log OCR completion event
        await event_logger.log_state_change(
            entity_type='document',
            entity_id=doc_id,
            old_status=DocumentStatus.OCR_IN_PROGRESS,
            new_status=DocumentStatus.OCR_COMPLETED,
            task_name='ocr_step',
            details={
                'text_length': len(full_text),
                'avg_confidence': avg_confidence,
                'document_count': len(all_extracted)
            }
        )

        logger.info(
            f"OCR complete for {doc_id}: {len(full_text)} chars, "
            f"{avg_confidence:.2%} confidence"
        )

        return full_text

    except Exception as e:
        logger.error(f"OCR failed for {doc_id}: {e}", exc_info=True)

        # Log error event
        await event_logger.log_error_event(
            entity_type='document',
            entity_id=doc_id,
            error_message=str(e),
            task_name='ocr_step'
        )

        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='ocr_task')

        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def classify_step(
    doc_id: UUID,
    extracted_text: str,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """Classify document using Bedrock LLM."""
    async with _bedrock_semaphore:
        return await _classify_task_impl(doc_id, extracted_text, db, bedrock_client)


async def _classify_task_impl(
    doc_id: UUID,
    extracted_text: str,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """Implementation of classify task (extracted for semaphore wrapping)."""
    from mcp_server.tools.classify_dynamic import classify_document_dynamic

    event_logger = get_event_logger(db)

    logger.info(f"Classifying document {doc_id}")

    try:
        # Get active prompt and known types
        prompt = await db.get_active_prompt(PromptType.CLASSIFIER)
        if not prompt:
            raise ValueError("No active classifier prompt found")

        known_types = [t['type_name'] for t in await db.get_document_types()]

        # Get existing tag combinations for context injection (prevents duplicates)
        existing_tags = await db.get_popular_tags(limit=50)

        doc = await db.get_document(doc_id)

        logger.info(f"Classifying with {len(existing_tags)} existing tags for context")

        # Run in executor (MCP tools are synchronous) with timing
        loop = asyncio.get_event_loop()
        start_time = time.time()
        classification = await loop.run_in_executor(
            None,
            classify_document_dynamic,
            extracted_text,
            doc['filename'],
            prompt['prompt_text'],
            known_types,
            existing_tags,
            bedrock_client
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # Log LLM classification event
        await event_logger.log_llm_call(
            entity_type='document',
            entity_id=doc_id,
            event_type='llm_classify',
            model=bedrock_client.model_id,
            prompt=prompt['prompt_text'][:2000],  # Truncate for storage
            response=json.dumps(classification),
            latency_ms=latency_ms,
            task_name='classify_step',
            details={
                'document_type': classification.get('document_type'),
                'confidence': classification.get('confidence'),
                'tags': classification.get('tags', [])
            }
        )
        
        # Save results
        await db.update_document(
            doc_id,
            document_type=classification['document_type'],
            classification_confidence=classification['confidence'],
            classification_reasoning=str(classification.get('reasoning', '')),
            suggested_type=classification.get('suggested_type'),
            status=DocumentStatus.CLASSIFIED
        )
        
        # Add document_type as tag
        await db.add_tag_to_document(
            doc_id,
            classification['document_type'],
            created_by='system'
        )
        
        # Add LLM-generated tags
        for tag in classification.get('tags', []):
            await db.add_tag_to_document(doc_id, tag, created_by='llm')
        
        # Add user tags from folder metadata
        folder_metadata = doc.get('folder_metadata')
        if folder_metadata:
            if isinstance(folder_metadata, str):
                folder_metadata = json.loads(folder_metadata)
            user_tags = folder_metadata.get('metadata', {}).get('tags', [])
            for tag in user_tags:
                await db.add_tag_to_document(doc_id, tag, created_by='user')
        
        # Record new type suggestion if present
        if classification.get('suggested_type'):
            from uuid import uuid4
            await db.record_classification_suggestion(
                suggestion_id=uuid4(),
                suggested_type=classification['suggested_type'],
                document_id=doc_id,
                confidence=classification['confidence'],
                reasoning=classification.get('suggestion_reasoning', '')
            )
        
        # Log state transition
        await event_logger.log_state_change(
            entity_type='document',
            entity_id=doc_id,
            old_status=DocumentStatus.OCR_COMPLETED,
            new_status=DocumentStatus.CLASSIFIED,
            task_name='classify_step',
            details={
                'document_type': classification['document_type'],
                'confidence': classification['confidence']
            }
        )

        logger.info(
            f"Classified {doc_id}: {classification['document_type']} "
            f"(confidence: {classification['confidence']:.2%})"
        )
        return classification

    except Exception as e:
        logger.error(f"Classification failed for {doc_id}: {e}", exc_info=True)

        # Log error event
        await event_logger.log_error_event(
            entity_type='document',
            entity_id=doc_id,
            error_message=str(e),
            task_name='classify_step'
        )

        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='classify_task')

        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def summarize_step(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """
    Summarize document with PostgreSQL advisory lock serialization.
    
    CRITICAL: Only ONE document of each type can be summarized at a time
    to prevent prompt evolution conflicts.
    """
    async with _bedrock_semaphore:
        return await _summarize_task_impl(doc_id, db, bedrock_client)


async def _summarize_task_impl(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """Implementation of summarize task (extracted for semaphore wrapping)."""
    event_logger = get_event_logger(db)

    doc = await db.get_document(doc_id)
    document_type = doc['document_type']

    logger.info(f"Summarizing document {doc_id} (type={document_type})")
    
    try:
        # SERIALIZE using PostgreSQL advisory lock
        async with document_type_lock(db, document_type):
            logger.info(
                f"Processing {doc_id} (type={document_type}) - "
                f"EXCLUSIVE LOCK HELD"
            )
            
            # Get type-specific prompt
            prompt = await db.get_active_prompt(
                PromptType.SUMMARIZER,
                document_type
            )
            if not prompt:
                logger.warning(
                    f"No summarizer prompt for {document_type}, trying generic"
                )
                prompt = await db.get_active_prompt(
                    PromptType.SUMMARIZER,
                    'generic'
                )
                
                # If still no prompt, create a basic one for this new type
                if not prompt:
                    from uuid import uuid4
                    logger.warning(
                        f"No generic prompt found, creating basic summarizer for {document_type}"
                    )
                    
                    # Create a basic generic summarizer prompt
                    basic_prompt = f"""Extract key information from this {document_type} document.

Return a JSON object with:
- summary: Brief summary of the document
- key_fields: Dictionary of important fields extracted from the document

Focus on dates, amounts, names, and other relevant details."""
                    
                    await db.create_prompt(
                        prompt_id=uuid4(),
                        prompt_type=PromptType.SUMMARIZER,
                        document_type=document_type,
                        prompt_text=basic_prompt,
                        version=1,
                        performance_score=0.5  # Low initial score to encourage evolution
                    )
                    
                    # Fetch the newly created prompt
                    prompt = await db.get_active_prompt(
                        PromptType.SUMMARIZER,
                        document_type
                    )
                    
                    logger.info(f"Created basic summarizer prompt for {document_type}")
            
            # Load LLM JSON if available
            llm_data = None
            text_path = doc.get("extracted_text_path")
            if text_path:
                llm_json_path = Path(text_path).parent / f"{Path(text_path).stem}_llm.json"
                if llm_json_path.exists():
                    with open(llm_json_path, 'r') as f:
                        llm_data = json.load(f)
            
            # Summarize with timing
            from mcp_server.tools.summarize_dynamic import summarize_document_dynamic
            loop = asyncio.get_event_loop()
            start_time = time.time()
            summary_result = await loop.run_in_executor(
                None,
                summarize_document_dynamic,
                doc['extracted_text'],
                doc['filename'],
                document_type,
                prompt['prompt_text'],
                llm_data,
                bedrock_client
            )
            latency_ms = int((time.time() - start_time) * 1000)

            # Log LLM summarization event
            await event_logger.log_llm_call(
                entity_type='document',
                entity_id=doc_id,
                event_type='llm_summarize',
                model=bedrock_client.model_id,
                prompt=prompt['prompt_text'][:2000],  # Truncate for storage
                response=json.dumps(summary_result)[:5000],  # Truncate response
                latency_ms=latency_ms,
                task_name='summarize_step',
                details={
                    'document_type': document_type,
                    'summary_length': len(summary_result.get('summary', ''))
                }
            )

            # Save generic extraction
            await db.update_document(
                doc_id,
                summary=summary_result.get('summary', ''),
                structured_data_generic=json.dumps(summary_result),  # Generic goes to _generic field
                status=DocumentStatus.SUMMARIZED
            )

            # Log state transition
            await event_logger.log_state_change(
                entity_type='document',
                entity_id=doc_id,
                old_status=DocumentStatus.CLASSIFIED,
                new_status=DocumentStatus.SUMMARIZED,
                task_name='summarize_step',
                details={'document_type': document_type}
            )

            logger.info(f"Summarized {doc_id} (lock releasing)")
            return summary_result.get('summary', '')
            
    except Exception as e:
        logger.error(f"Summarization failed for {doc_id}: {e}", exc_info=True)

        # Log error event
        await event_logger.log_error_event(
            entity_type='document',
            entity_id=doc_id,
            error_message=str(e),
            task_name='summarize_step',
            details={'document_type': doc.get('document_type')}
        )

        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='summarize_task',
                     context={'document_type': doc.get('document_type')})

        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def score_classification_step(
    doc_id: UUID,
    classification: Dict[str, Any],
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score classification quality and update prompt if improved."""
    async with _bedrock_semaphore:
        return await _score_classification_task_impl(doc_id, classification, db, bedrock_client)


async def _score_classification_task_impl(
    doc_id: UUID,
    classification: Dict[str, Any],
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Implementation of score classification task (extracted for semaphore wrapping)."""
    from mcp_server.tools.score_performance import score_classification
    from uuid import uuid4
    from shared.config import Settings
    
    settings = Settings()
    
    logger.info(f"Scoring classification for {doc_id}")
    
    try:
        # Get documents count for this type
        docs = await db.list_documents(
            document_type=classification['document_type'],
            limit=1000
        )
        
        # Skip if too few documents
        if len(docs) < settings.min_documents_for_scoring:
            logger.info(f"Skipping scoring - only {len(docs)} documents")
            await db.update_document(
                doc_id,
                status=DocumentStatus.SCORED_CLASSIFICATION
            )
            return 0.0
        
        # Score
        doc = await db.get_document(doc_id)
        prompt = await db.get_active_prompt(PromptType.CLASSIFIER)
        
        # Check if prompt can evolve (STATIC prompts never evolve)
        can_evolve = prompt.get('can_evolve', True)  # Default to True for backward compatibility
        
        if not can_evolve:
            logger.info(f"Classifier prompt is STATIC (can_evolve=false), skipping evolution")
            await db.update_document(
                doc_id,
                status=DocumentStatus.SCORED_CLASSIFICATION
            )
            return prompt.get('performance_score') or 0.0
        
        # Build document_info dict for scoring
        document_info = {
            'extracted_text': doc['extracted_text'],
            'filename': doc['filename'],
            'document_type': classification['document_type'],
            'confidence': classification['confidence'],
            'reasoning': classification.get('reasoning', ''),
            'tags': classification.get('tags', [])
        }
        
        loop = asyncio.get_event_loop()
        score_result = await loop.run_in_executor(
            None,
            score_classification,
            document_info,
            prompt['prompt_text'],
            bedrock_client
        )
        
        # Check score ceiling (stop evolution if reached)
        score_ceiling = prompt.get('score_ceiling')
        current_score = prompt.get('performance_score') or 0
        
        if score_ceiling and current_score >= score_ceiling:
            logger.info(
                f"Classifier prompt at ceiling ({current_score:.2f} >= {score_ceiling}), "
                f"skipping evolution"
            )
            await db.update_document(
                doc_id,
                status=DocumentStatus.SCORED_CLASSIFICATION
            )
            return score_result['score']
        
        # Update prompt if significantly improved
        if score_result['score'] > (current_score + settings.prompt_update_threshold):
            # Evolve the prompt using the scoring feedback
            from mcp_server.tools.score_performance import evolve_prompt
            
            loop = asyncio.get_event_loop()
            new_prompt_text = await loop.run_in_executor(
                None,
                evolve_prompt,
                prompt['prompt_text'],
                'classifier',
                None,  # document_type (None for classifier)
                score_result.get('feedback', ''),
                score_result.get('suggested_improvements', ''),
                300,  # max_words
                bedrock_client
            )
            
            await db.deactivate_old_prompts(PromptType.CLASSIFIER)
            await db.create_prompt(
                prompt_id=uuid4(),
                prompt_type=PromptType.CLASSIFIER,
                prompt_text=new_prompt_text,
                version=prompt['version'] + 1,
                performance_score=score_result['score']
            )
            logger.info(
                f"Updated classifier prompt: "
                f"v{prompt['version']+1}, score={score_result['score']:.2f}"
            )
        
        # Don't update status here - let the orchestrator proceed to summarize step
        # The document is already in 'classified' status which triggers summarization
        return score_result['score']
        
    except Exception as e:
        logger.error(f"Classification scoring failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='score_classification_task')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def score_summary_step(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score summary quality and update prompt if improved."""
    async with _bedrock_semaphore:
        return await _score_summary_task_impl(doc_id, db, bedrock_client)


async def _score_summary_task_impl(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Implementation of score summary task (extracted for semaphore wrapping)."""
    from mcp_server.tools.score_performance import score_summarization
    from uuid import uuid4
    from shared.config import Settings
    
    settings = Settings()
    
    logger.info(f"Scoring summary for {doc_id}")
    
    try:
        doc = await db.get_document(doc_id)
        document_type = doc['document_type']
        
        prompt = await db.get_active_prompt(PromptType.SUMMARIZER, document_type)
        if not prompt:
            # Don't skip to FILED - let orchestrator proceed to series step
            return 0.0
        
        # Check if prompt can evolve
        can_evolve = prompt.get('can_evolve', True)
        
        if not can_evolve:
            logger.info(f"Generic summarizer prompt is STATIC (can_evolve=false), skipping evolution")
            return prompt.get('performance_score') or 0.0
        
        # Parse structured data
        structured_data = doc.get('structured_data', {})
        if isinstance(structured_data, str):
            structured_data = json.loads(structured_data)
        
        # Build document_info dict for scoring
        document_info = {
            'extracted_text': doc['extracted_text'],
            'filename': doc['filename'],
            'document_type': document_type,
            'structured_data': structured_data
        }
        
        # Score
        loop = asyncio.get_event_loop()
        score_result = await loop.run_in_executor(
            None,
            score_summarization,
            document_info,
            prompt['prompt_text'],
            bedrock_client
        )
        
        # Check score ceiling (0.95 for generic summarizer)
        score_ceiling = prompt.get('score_ceiling', 0.95)
        current_score = prompt.get('performance_score') or 0
        
        if current_score >= score_ceiling:
            logger.info(
                f"Generic summarizer at ceiling ({current_score:.2f} >= {score_ceiling}), "
                f"skipping evolution"
            )
            return score_result['score']
        
        # Update prompt if improved
        if score_result['score'] > (current_score + settings.prompt_update_threshold):
            # Evolve the prompt using the scoring feedback
            from mcp_server.tools.score_performance import evolve_prompt
            
            loop = asyncio.get_event_loop()
            new_prompt_text = await loop.run_in_executor(
                None,
                evolve_prompt,
                prompt['prompt_text'],
                'summarizer',
                document_type,
                score_result.get('feedback', ''),
                score_result.get('suggested_improvements', ''),
                None,  # max_words (None for summarizer)
                bedrock_client
            )
            
            await db.deactivate_old_prompts(PromptType.SUMMARIZER, document_type)
            await db.create_prompt(
                prompt_id=uuid4(),
                prompt_type=PromptType.SUMMARIZER,
                document_type=document_type,
                prompt_text=new_prompt_text,
                version=prompt['version'] + 1,
                performance_score=score_result['score']
            )
            logger.info(
                f"Updated {document_type} summarizer prompt: "
                f"v{prompt['version']+1}, score={score_result['score']:.2f}"
            )
        
        # Don't update status here - let the orchestrator proceed to series step
        # Document status stays as 'summarized' to trigger series summarization
        return score_result['score']
        
    except Exception as e:
        logger.error(f"Summary scoring failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='score_summary_task',
                     context={'document_type': doc.get('document_type')})
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def file_step(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> UUID:
    """Detect series, create file, add tags."""
    from mcp_server.tools.detect_series import detect_series_with_retry
    from uuid import uuid4

    event_logger = get_event_logger(db)

    logger.info(f"Filing document {doc_id}")

    try:
        doc = await db.get_document(doc_id)
        tags = await db.get_document_tags(doc_id)
        
        # Parse structured data
        structured_data = doc.get('structured_data', {})
        if isinstance(structured_data, str):
            structured_data = json.loads(structured_data)
        
        # Get series detector prompt from database
        series_prompt = await db.get_active_prompt(PromptType.SERIES_DETECTOR)
        if not series_prompt:
            raise ValueError("No active series_detector prompt found")
        
        # Get existing series for context injection (prevents duplicates)
        existing_series = await db.get_all_series_with_context(
            user_id=doc.get('user_id'),
            limit=100
        )
        
        logger.info(f"Filing with {len(existing_series)} existing series for context")
        
        # Detect series with context injection and timing
        start_time = time.time()
        series_data = detect_series_with_retry(
            summary=doc['summary'],
            document_type=doc['document_type'],
            structured_data=structured_data,
            tags=tags,
            bedrock_client=bedrock_client,
            series_prompt=series_prompt['prompt_text'],
            existing_series=existing_series
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # Log LLM series detection event
        await event_logger.log_llm_call(
            entity_type='document',
            entity_id=doc_id,
            event_type='llm_series_detect',
            model=bedrock_client.model_id,
            prompt=series_prompt['prompt_text'][:2000],
            response=json.dumps(series_data),
            latency_ms=latency_ms,
            task_name='file_step',
            details={
                'entity': series_data.get('entity'),
                'series_type': series_data.get('series_type')
            }
        )
        
        # Create series
        series = await db.find_or_create_series(
            series_id=uuid4(),
            entity=series_data['entity'],
            series_type=series_data['series_type'],
            title=series_data['title'],
            frequency=series_data.get('frequency'),
            description=series_data.get('description'),
            metadata=series_data.get('metadata')
        )
        
        # Add to series (with idempotency check)
        try:
            await db.add_document_to_series(series['id'], doc_id)
        except Exception as e:
            # Check if it's a duplicate key error (already added)
            if 'duplicate key' in str(e).lower() or 'already exists' in str(e).lower():
                logger.warning(f"Document {doc_id} already in series {series['id']}, skipping")
            else:
                raise
        
        # Create series tag
        entity_slug = series_data['entity'].lower().replace(' ', '-').replace('&', 'and')
        series_tag = f"series:{entity_slug}"
        
        logger.info(f"Adding series tag '{series_tag}' to document {doc_id}")
        await db.add_tag_to_document(doc_id, series_tag, created_by='llm')
        
        # Update document status to 'filed' BEFORE creating file
        # This ensures get_file_documents() can find it immediately
        await db.update_document(doc_id, status=DocumentStatus.FILED)
        logger.info(f"Document {doc_id} status updated to 'filed'")
        
        # Create file based on series tag (file query will now find this document)
        file = await db.find_or_create_file(uuid4(), tags=[series_tag])
        logger.info(f"File {file['id']} created/found for tag '{series_tag}'")
        
        # Log state transition (document)
        await event_logger.log_state_change(
            entity_type='document',
            entity_id=doc_id,
            old_status=DocumentStatus.SUMMARIZED,
            new_status=DocumentStatus.FILED,
            task_name='file_step',
            details={
                'series_id': str(series['id']),
                'file_id': str(file['id']),
                'series_tag': series_tag
            }
        )

        # Log event against series (document added)
        await event_logger.log_processing_event(
            entity_type='series',
            entity_id=series['id'],
            event_type='document_added',
            task_name='file_step',
            details={
                'document_id': str(doc_id),
                'document_type': doc['document_type'],
                'series_tag': series_tag
            }
        )

        logger.info(f"Filed {doc_id} into series {series['id']}, file {file['id']}, with tag '{series_tag}'")

        return file['id']

    except Exception as e:
        logger.error(f"Filing failed for {doc_id}: {e}", exc_info=True)

        # Log error event
        await event_logger.log_error_event(
            entity_type='document',
            entity_id=doc_id,
            error_message=str(e),
            task_name='file_step'
        )

        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='file_task')

        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def generate_file_summary_step(
    file_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """Generate summary for file collection."""
    async with _file_gen_semaphore:
        return await _generate_file_summary_task_impl(file_id, db, bedrock_client)


async def _generate_file_summary_task_impl(
    file_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """Implementation of file summary generation task (extracted for semaphore wrapping)."""
    from mcp_server.tools.summarize_file import summarize_file
    from datetime import datetime, timezone

    event_logger = get_event_logger(db)

    logger.info(f"Generating file summary for {file_id}")
    
    try:
        # Mark as generating with timestamp
        from shared.database import utc_now
        await db.update_file(
            file_id,
            status='generating',
            processing_started_at=utc_now()
        )
        
        # Get file and documents
        logger.info(f"Fetching file {file_id}...")
        file = await db.get_file(file_id)
        
        if not file:
            logger.error(f"File {file_id} not found")
            await db.update_file(file_id, status='failed')
            raise ValueError(f"File {file_id} not found")
        
        logger.info(f"File fetched: tags={file.get('tags')}, status={file.get('status')}")
        
        documents = await db.get_file_documents(file_id, order_by="created_at DESC")
        logger.info(f"File {file_id}: Generating summary for {len(documents)} documents")
        
        if not documents:
            logger.warning(f"No documents for file {file_id}, marking as generated with empty summary")
            await db.update_file(
                file_id,
                summary_text="",
                status='generated',
                last_generated_at=datetime.now(timezone.utc)
            )
            return ""
        
        # Build aggregated content
        content_parts = []
        for doc in documents:
            structured_data = doc.get('structured_data', {})
            if isinstance(structured_data, str):
                structured_data = json.loads(structured_data) if structured_data else {}
            
            content_parts.append({
                'filename': doc['filename'],
                'date': doc['created_at'].isoformat(),
                'summary': doc.get('summary', ''),
                'structured_data': structured_data
            })
        
        # Generate file summary with timing
        logger.info(f"Calling summarize_file with {len(content_parts)} documents, tags={file['tags']}")
        loop = asyncio.get_event_loop()
        start_time = time.time()

        try:
            summary = await loop.run_in_executor(
                None,
                summarize_file,
                content_parts,  # documents
                None,  # file_type (deprecated)
                file.get('tags', []),  # tags (ensure it's a list)
                "",  # prompt (empty string for default)
                bedrock_client,
                None  # flattened_table (will be auto-generated)
            )
            latency_ms = int((time.time() - start_time) * 1000)
            logger.info(f"File summary generated successfully: {len(summary.get('summary', ''))} chars")

            # Log LLM file summary event
            await event_logger.log_llm_call(
                entity_type='file',
                entity_id=file_id,
                event_type='llm_file_summarize',
                model=bedrock_client.model_id,
                prompt=f"Summarize file with {len(content_parts)} documents",
                response=summary.get('summary', '')[:5000],
                latency_ms=latency_ms,
                task_name='generate_file_summary_step',
                details={
                    'document_count': len(content_parts),
                    'tags': file.get('tags', [])
                }
            )
        except Exception as e:
            logger.error(f"Error in summarize_file: {e}", exc_info=True)
            raise

        # Save
        await db.update_file(
            file_id,
            summary_text=summary['summary'],
            summary_metadata=summary.get('metadata', {}),
            status='generated',
            last_generated_at=datetime.now(timezone.utc)
        )

        # Log state transition
        await event_logger.log_state_change(
            entity_type='file',
            entity_id=file_id,
            old_status='generating',
            new_status='generated',
            task_name='generate_file_summary_step',
            details={'summary_length': len(summary.get('summary', ''))}
        )

        logger.info(f"File {file_id}: Summary generated ({len(summary.get('summary', ''))} chars)")
        return summary['summary']
        
    except Exception as e:
        logger.error(f"File summary generation failed for {file_id}: {e}", exc_info=True)

        # Log error event
        await event_logger.log_error_event(
            entity_type='file',
            entity_id=file_id,
            error_message=str(e),
            task_name='generate_file_summary_step'
        )

        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='file', entity_id=file_id,
                     task_name='generate_file_summary_task')

        # Mark file as failed so it doesn't keep retrying
        await db.update_file(
            file_id,
            status='failed'
        )
        raise


async def series_summarize_step(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """
    Summarize document with series-specific prompt.
    This runs AFTER file_step() assigns the document to a series.
    """
    async with _bedrock_semaphore:
        return await _series_summarize_task_impl(doc_id, db, bedrock_client)


async def _series_summarize_task_impl(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """Implementation of series summarize task."""
    from mcp_server.tools.summarize_series import (
        create_series_prompt_from_generic,
        summarize_with_series_prompt
    )
    from uuid import uuid4
    from shared.database import utc_now

    event_logger = get_event_logger(db)

    logger.info(f"Series summarizing document {doc_id}")
    
    try:
        # Mark as in-progress
        await db.update_document(
            doc_id,
            status='series_summarizing',
            processing_started_at=utc_now()
        )
        
        doc = await db.get_document(doc_id)
        
        # Get series from document_series junction table
        series_data = await db.get_document_series(doc_id)
        if not series_data:
            logger.warning(f"Document {doc_id} not in any series, skipping")
            await db.update_document(doc_id, status=DocumentStatus.COMPLETED)
            return {}
        
        # get_document_series returns the series dict directly (not a list)
        series_id = series_data['id']
        series = await db.get_series(series_id)
        
        # ALWAYS check series.active_prompt_id FIRST to reuse existing prompt
        series_prompt = None
        if series.get('active_prompt_id'):
            series_prompt = await db.get_prompt(series['active_prompt_id'])
            if series_prompt:
                logger.info(
                    f"Reusing existing series prompt {series_prompt['id']} "
                    f"v{series_prompt['version']} for series {series_id}"
                )
        
        # Only create if series has NO active prompt - use DATABASE lock for cross-task safety
        if not series_prompt:
            # Use PostgreSQL advisory lock to prevent concurrent prompt creation
            async with series_prompt_lock(db, series_id):
                # Double-check after acquiring lock (another task may have created it)
                series = await db.get_series(series_id)
                if series.get('active_prompt_id'):
                    series_prompt = await db.get_prompt(series['active_prompt_id'])
                    if series_prompt:
                        logger.info(
                            f"✅ Another task created series prompt {series_prompt['id']}, reusing it"
                        )

                # Still no prompt after lock? Create it now
                if not series_prompt:
                    logger.info(f"🔒 Creating FIRST series prompt for series {series_id} (DB lock held)")

                    # Get generic prompt for this document type
                    generic_prompt = await db.get_active_prompt(
                        PromptType.SUMMARIZER,
                        doc['document_type']
                    )

                    if not generic_prompt:
                        logger.warning(f"No generic prompt for {doc['document_type']}, skipping series extraction")
                        await db.update_document(doc_id, status=DocumentStatus.COMPLETED)
                        return {}

                    # Create series-specific prompt
                    loop = asyncio.get_event_loop()
                    prompt_data = await loop.run_in_executor(
                        None,
                        create_series_prompt_from_generic,
                        generic_prompt['prompt_text'],
                        series['entity'],
                        series['series_type'],
                        doc['extracted_text'],
                        bedrock_client
                    )

                    # Save as new prompt in prompts table
                    series_prompt_id = uuid4()
                    await db.create_prompt(
                        prompt_id=series_prompt_id,
                        prompt_type='series_summarizer',
                        document_type=str(series_id),  # Store series_id as document_type
                        prompt_text=prompt_data['prompt_text'],
                        version=1,
                        performance_metrics={
                            'schema_definition': prompt_data['schema_definition'],
                            'documents_processed': 0
                        }
                    )

                    # Fetch the created prompt
                    series_prompt = await db.get_prompt(series_prompt_id)

                    # Link to series
                    await db.update_series(
                        series_id,
                        active_prompt_id=series_prompt_id
                    )

                    logger.info(f"✅ Created FIRST series prompt {series_prompt_id} for series {series_id}")

                    # Log series prompt creation event against series
                    await event_logger.log_processing_event(
                        entity_type='series',
                        entity_id=series_id,
                        event_type='prompt_created',
                        task_name='series_summarize_step',
                        details={
                            'prompt_id': str(series_prompt_id),
                            'document_type': doc['document_type'],
                            'schema_fields': list(prompt_data['schema_definition'].keys()) if prompt_data.get('schema_definition') else []
                        }
                    )
        
        # Extract schema from performance_metrics
        perf_metrics = series_prompt.get('performance_metrics', {})
        if isinstance(perf_metrics, str):
            perf_metrics = json.loads(perf_metrics)
        schema_def = perf_metrics.get('schema_definition', {})
        
        # Summarize with series prompt with timing
        loop = asyncio.get_event_loop()
        start_time = time.time()
        series_extraction = await loop.run_in_executor(
            None,
            summarize_with_series_prompt,
            doc['extracted_text'],
            series_prompt['prompt_text'],
            schema_def,
            bedrock_client
        )
        latency_ms = int((time.time() - start_time) * 1000)

        # Log LLM series summarization event
        await event_logger.log_llm_call(
            entity_type='document',
            entity_id=doc_id,
            event_type='llm_series_summarize',
            model=bedrock_client.model_id,
            prompt=series_prompt['prompt_text'][:2000],
            response=json.dumps(series_extraction)[:5000],
            latency_ms=latency_ms,
            task_name='series_summarize_step',
            details={
                'series_id': str(series_id),
                'schema_fields': list(schema_def.keys()) if schema_def else []
            }
        )

        # Save series-specific extraction to structured_data (primary field)
        await db.update_document(
            doc_id,
            structured_data=json.dumps(series_extraction),  # Series goes to primary structured_data field
            series_prompt_id=series_prompt['id'],
            extraction_method='series',  # Mark as series extraction
            status='series_summarized'
        )

        # Log state transition
        await event_logger.log_state_change(
            entity_type='document',
            entity_id=doc_id,
            old_status='series_summarizing',
            new_status='series_summarized',
            task_name='series_summarize_step',
            details={'series_id': str(series_id)}
        )

        logger.info(f"Series summarization complete for {doc_id}")
        return series_extraction
        
    except Exception as e:
        logger.error(f"Series summarization failed for {doc_id}: {e}", exc_info=True)

        # Log error event
        await event_logger.log_error_event(
            entity_type='document',
            entity_id=doc_id,
            error_message=str(e),
            task_name='series_summarize_step'
        )

        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='series_summarize_step')

        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


async def score_series_extraction_step(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score series extraction quality and evolve series prompt if improved."""
    async with _bedrock_semaphore:
        return await _score_series_extraction_task_impl(doc_id, db, bedrock_client)


async def _score_series_extraction_task_impl(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Implementation of score series extraction task."""
    from mcp_server.tools.score_performance import score_summarization, evolve_prompt
    from uuid import uuid4
    from shared.config import Settings
    from shared.database import utc_now
    
    settings = Settings()
    event_logger = get_event_logger(db)

    logger.info(f"Scoring series extraction for {doc_id}")
    
    try:
        doc = await db.get_document(doc_id)
        
        # Get series
        series_data = await db.get_document_series(doc_id)
        if not series_data:
            logger.warning(f"Document {doc_id} not in series, skipping scoring")
            return 0.0
        
        series_id = series_data['id']
        
        # Get series prompt
        series_prompt = await db.get_series_prompt(series_id)
        if not series_prompt:
            logger.warning(f"No series prompt for series {series_id}, skipping scoring")
            return 0.0
        
        # Parse series extraction from structured_data (now the primary field)
        structured_data = doc.get('structured_data', {})
        if isinstance(structured_data, str):
            structured_data = json.loads(structured_data)
        
        # Build document_info dict for scoring
        document_info = {
            'extracted_text': doc['extracted_text'],
            'filename': doc['filename'],
            'document_type': doc['document_type'],
            'structured_data': structured_data  # Score the series extraction
        }
        
        # Score using existing summarization scorer
        loop = asyncio.get_event_loop()
        score_result = await loop.run_in_executor(
            None,
            score_summarization,
            document_info,
            series_prompt['prompt_text'],
            bedrock_client
        )
        
        # Check if prompt can evolve
        can_evolve = series_prompt.get('can_evolve', True)
        
        if not can_evolve:
            logger.info(f"Series prompt is STATIC (can_evolve=false), skipping evolution")
            return series_prompt.get('performance_score') or 0.0
        
        # Check score ceiling (0.95 for series summarizer)
        score_ceiling = series_prompt.get('score_ceiling', 0.95)
        current_score = series_prompt.get('performance_score') or 0
        
        if current_score >= score_ceiling:
            logger.info(
                f"Series prompt at ceiling ({current_score:.2f} >= {score_ceiling}), "
                f"skipping evolution"
            )
            return score_result['score']
        
        # Update series prompt if significantly improved
        # This will trigger regeneration of ALL documents in the series
        logger.info(
            f"Evolution check: new_score={score_result['score']:.2f}, "
            f"current_score={current_score:.2f}, threshold={settings.prompt_update_threshold}, "
            f"required={current_score + settings.prompt_update_threshold:.2f}"
        )
        if score_result['score'] > (current_score + settings.prompt_update_threshold):
            logger.info(
                f"Series prompt score improved from {current_score:.2f} to {score_result['score']:.2f}"
            )
            
            # Evolve the series prompt
            new_prompt_text = await loop.run_in_executor(
                None,
                evolve_prompt,
                series_prompt['prompt_text'],
                'series_summarizer',
                series_data['entity'],  # Use entity name as doc type
                score_result.get('feedback', ''),
                score_result.get('suggested_improvements', ''),
                None,  # max_words (None for series summarizer)
                bedrock_client
            )
            
            # Deactivate ALL old prompts for this series before creating new one
            async with db.pool.acquire() as conn:
                await conn.execute("""
                    UPDATE prompts
                    SET is_active = FALSE, updated_at = $2
                    WHERE prompt_type = 'series_summarizer'
                      AND document_type = $1
                      AND is_active = TRUE
                """, str(series_id), utc_now())
            
            logger.info(f"Deactivated old series prompts for series {series_id}")
            
            # Create new version of series prompt (will be active by default)
            new_prompt_id = uuid4()
            await db.create_series_prompt(
                prompt_id=new_prompt_id,
                series_id=series_id,
                prompt_text=new_prompt_text,
                version=series_prompt['version'] + 1,
                performance_score=score_result['score'],
                performance_metrics=series_prompt.get('performance_metrics', {})
            )
            
            # Mark series for regeneration (regenerates_on_update=true)
            await db.update_series(
                series_id,
                active_prompt_id=new_prompt_id,
                regeneration_pending=True
            )
            
            logger.info(
                f"✅ Updated series {series_id} prompt: "
                f"v{series_prompt['version']+1} (ID: {new_prompt_id}), "
                f"score={score_result['score']:.2f}, "
                f"old prompts deactivated, regeneration_pending=True"
            )

            # Log series prompt evolution event
            await event_logger.log_processing_event(
                entity_type='series',
                entity_id=series_id,
                event_type='prompt_evolved',
                task_name='score_series_extraction_step',
                details={
                    'old_prompt_id': str(series_prompt['id']),
                    'new_prompt_id': str(new_prompt_id),
                    'old_version': series_prompt['version'],
                    'new_version': series_prompt['version'] + 1,
                    'old_score': current_score,
                    'new_score': score_result['score'],
                    'regeneration_pending': True
                }
            )
        
        # Don't update status - scoring is background-only
        # Document stays in 'series_summarized' status
        return score_result['score']
        
    except Exception as e:
        logger.error(f"Series extraction scoring failed for {doc_id}: {e}", exc_info=True)
        
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='score_series_extraction_step')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise