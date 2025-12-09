"""Document processing tasks with Prefect concurrency control."""

from prefect import task
from prefect.concurrency.asyncio import rate_limit
from uuid import UUID
import logging
import asyncio
from typing import Dict, Any
import json
from pathlib import Path

from shared.database import AlfrdDatabase
from shared.types import DocumentStatus, PromptType
from shared.config import Settings
from mcp_server.llm.bedrock import BedrockClient
from document_processor.utils.locks import document_type_lock

logger = logging.getLogger(__name__)

# Load settings for configurable worker limits
_settings = Settings()

# Asyncio semaphores for concurrency enforcement (works without Prefect Server)
# These ensure limits are respected even in standalone/dev mode
# Configured via environment variables
_textract_semaphore = asyncio.Semaphore(_settings.prefect_textract_workers)
_bedrock_semaphore = asyncio.Semaphore(_settings.prefect_bedrock_workers)
_file_gen_semaphore = asyncio.Semaphore(_settings.prefect_file_generation_workers)


@task(
    name="OCR Document",
    retries=2,
    retry_delay_seconds=30,
    tags=["ocr", "aws"],
    cache_policy=None  # Disable caching - db can't be serialized
)
async def ocr_task(doc_id: UUID, db: AlfrdDatabase) -> str:
    """
    Extract text using AWS Textract.
    
    Limited to 3 concurrent executions via asyncio semaphore + Prefect rate limiting.
    """
    # Dual concurrency control:
    # 1. Prefect rate limiting (enforced only with Prefect Server)
    await rate_limit("aws-textract")
    # 2. Asyncio semaphore (enforced in all modes including dev)
    async with _textract_semaphore:
        return await _ocr_task_impl(doc_id, db)


async def _ocr_task_impl(doc_id: UUID, db: AlfrdDatabase) -> str:
    """Implementation of OCR task (extracted for semaphore wrapping)."""
    from document_processor.extractors.aws_textract import TextractExtractor
    from document_processor.extractors.text import TextExtractor
    from shared.constants import META_JSON_FILENAME
    from shared.database import utc_now
    
    doc = await db.get_document(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    
    await db.update_document(doc_id, status=DocumentStatus.OCR_IN_PROGRESS)
    
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
        
        logger.info(
            f"OCR complete for {doc_id}: {len(full_text)} chars, "
            f"{avg_confidence:.2%} confidence"
        )
        
        return full_text
        
    except Exception as e:
        logger.error(f"OCR failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='ocr_task')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


@task(
    name="Classify Document",
    retries=2,
    tags=["classify", "llm"],
    cache_policy=None  # Disable caching
)
async def classify_task(
    doc_id: UUID,
    extracted_text: str,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """Classify document using Bedrock LLM."""
    await rate_limit("aws-bedrock")
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
    
    logger.info(f"Classifying document {doc_id}")
    
    try:
        # Get active prompt and known types
        prompt = await db.get_active_prompt(PromptType.CLASSIFIER)
        if not prompt:
            raise ValueError("No active classifier prompt found")
        
        known_types = [t['type_name'] for t in await db.get_document_types()]
        existing_tags = await db.get_popular_tags(limit=50)
        
        doc = await db.get_document(doc_id)
        
        # Run in executor (MCP tools are synchronous)
        loop = asyncio.get_event_loop()
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
        
        logger.info(
            f"Classified {doc_id}: {classification['document_type']} "
            f"(confidence: {classification['confidence']:.2%})"
        )
        return classification
        
    except Exception as e:
        logger.error(f"Classification failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='classify_task')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


@task(
    name="Summarize Document",
    retries=2,
    tags=["summarize", "llm"],
    cache_policy=None  # Disable caching
)
async def summarize_task(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """
    Summarize document with PostgreSQL advisory lock serialization.
    
    CRITICAL: Only ONE document of each type can be summarized at a time
    to prevent prompt evolution conflicts.
    """
    await rate_limit("aws-bedrock")
    async with _bedrock_semaphore:
        return await _summarize_task_impl(doc_id, db, bedrock_client)


async def _summarize_task_impl(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """Implementation of summarize task (extracted for semaphore wrapping)."""
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
                    f"No summarizer prompt for {document_type}, using generic"
                )
                prompt = await db.get_active_prompt(
                    PromptType.SUMMARIZER,
                    'generic'
                )
            
            if not prompt:
                raise ValueError(f"No summarizer prompt found for {document_type}")
            
            # Load LLM JSON if available
            llm_data = None
            text_path = doc.get("extracted_text_path")
            if text_path:
                llm_json_path = Path(text_path).parent / f"{Path(text_path).stem}_llm.json"
                if llm_json_path.exists():
                    with open(llm_json_path, 'r') as f:
                        llm_data = json.load(f)
            
            # Summarize
            from mcp_server.tools.summarize_dynamic import summarize_document_dynamic
            loop = asyncio.get_event_loop()
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
            
            # Save
            await db.update_document(
                doc_id,
                summary=summary_result.get('summary', ''),
                structured_data=json.dumps(summary_result),
                status=DocumentStatus.SUMMARIZED
            )
            
            logger.info(f"Summarized {doc_id} (lock releasing)")
            return summary_result.get('summary', '')
            
    except Exception as e:
        logger.error(f"Summarization failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='summarize_task',
                     context={'document_type': doc.get('document_type')})
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


@task(
    name="Score Classification",
    tags=["scoring", "llm"],
    cache_policy=None  # Disable caching
)
async def score_classification_task(
    doc_id: UUID,
    classification: Dict[str, Any],
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score classification quality and update prompt if improved."""
    await rate_limit("aws-bedrock")
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
        
        # Update prompt if significantly improved
        current_score = prompt.get('performance_score') or 0
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
        
        await db.update_document(
            doc_id,
            status=DocumentStatus.SUMMARIZING
        )
        return score_result['score']
        
    except Exception as e:
        logger.error(f"Classification scoring failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='score_classification_task')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


@task(
    name="Score Summary",
    tags=["scoring", "llm"],
    cache_policy=None  # Disable caching
)
async def score_summary_task(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score summary quality and update prompt if improved."""
    await rate_limit("aws-bedrock")
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
            await db.update_document(doc_id, status=DocumentStatus.FILED)
            return 0.0
        
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
        
        # Update prompt if improved
        current_score = prompt.get('performance_score') or 0
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
        
        await db.update_document(doc_id, status=DocumentStatus.FILED)
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


@task(
    name="File Document (Series)",
    tags=["filing", "llm"],
    cache_policy=None  # Disable caching
)
async def file_task(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> UUID:
    """Detect series, create file, add tags."""
    from mcp_server.tools.detect_series import detect_series_with_retry
    from uuid import uuid4
    
    logger.info(f"Filing document {doc_id}")
    
    try:
        doc = await db.get_document(doc_id)
        tags = await db.get_document_tags(doc_id)
        
        # Parse structured data
        structured_data = doc.get('structured_data', {})
        if isinstance(structured_data, str):
            structured_data = json.loads(structured_data)
        
        # Detect series
        series_data = detect_series_with_retry(
            summary=doc['summary'],
            document_type=doc['document_type'],
            structured_data=structured_data,
            tags=tags,
            bedrock_client=bedrock_client
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
        await db.add_tag_to_document(doc_id, series_tag, created_by='llm')
        
        # Create file
        file = await db.find_or_create_file(uuid4(), tags=[series_tag])
        
        await db.update_document(doc_id, status=DocumentStatus.FILED)
        logger.info(f"Filed {doc_id} into series {series['id']}, file {file['id']}")
        
        return file['id']
        
    except Exception as e:
        logger.error(f"Filing failed for {doc_id}: {e}", exc_info=True)
        
        # Structured exception logging
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='file_task')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise


@task(
    name="Generate File Summary",
    tags=["file-generation", "llm"],
    cache_policy=None  # Disable caching
)
async def generate_file_summary_task(
    file_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """Generate summary for file collection."""
    await rate_limit("file-generation")
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
    
    logger.info(f"Generating file summary for {file_id}")
    
    try:
        # Get file and documents
        logger.info(f"Fetching file {file_id}...")
        file = await db.get_file(file_id)
        logger.info(f"File fetched: {file.get('tags')}")
        
        logger.info(f"Fetching documents for file {file_id}...")
        documents = await db.get_file_documents(file_id, order_by="created_at DESC")
        logger.info(f"Documents fetched: {len(documents)} documents")
        
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
        
        # Generate file summary
        loop = asyncio.get_event_loop()
        summary = await loop.run_in_executor(
            None,
            summarize_file,
            content_parts,  # documents
            None,  # file_type (deprecated)
            file['tags'],  # tags
            "",  # prompt (empty string for default)
            bedrock_client,
            None  # flattened_table (will be auto-generated)
        )
        
        # Save
        await db.update_file(
            file_id,
            summary_text=summary['summary'],
            summary_metadata=summary.get('metadata', {}),
            status='generated',
            last_generated_at=datetime.now(timezone.utc)
        )
        
        logger.info(f"Generated summary for file {file_id}")
        return summary['summary']
        
    except Exception as e:
        logger.error(f"File summary generation failed for {file_id}: {e}", exc_info=True)
        
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