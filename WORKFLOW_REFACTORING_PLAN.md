# ALFRD Workflow Refactoring: Prefect Migration Plan

**Goal:** Replace custom worker polling architecture with Prefect DAG-based workflows in a single migration.

**Timeline:** 3-4 days with clear commit and test points

**Key Requirements:**
- Multiple flow types (document processing vs. file generation)
- Concurrency limits (max 2-3 AWS Textract connections)
- Per-type serialization using PostgreSQL advisory locks (no Redis!)
- DB monitoring for continuous processing
- No data migration required

---

## Pre-Migration Checklist

- [ ] Create feature branch: `git checkout -b feature/prefect-migration`
- [ ] Ensure all tests passing on main branch
- [ ] Backup database: `pg_dump -U alfrd_user alfrd > backup_$(date +%Y%m%d).sql`
- [ ] Document current worker configuration in `shared/config.py`

---

## Day 1: Foundation & PostgreSQL Locks

### Milestone 1.1: Install Prefect & Setup (2 hours)

**Tasks:**
1. Install Prefect
   ```bash
   pip install prefect prefect-aws
   pip freeze > requirements.txt
   ```

2. Configure Prefect concurrency limits
   ```bash
   prefect concurrency-limit create aws-textract 3
   prefect concurrency-limit create aws-bedrock 5
   prefect concurrency-limit create file-generation 2
   ```

3. Create directory structure
   ```bash
   mkdir -p document-processor/src/document_processor/flows
   mkdir -p document-processor/src/document_processor/tasks
   mkdir -p document-processor/src/document_processor/utils
   ```

**🧪 Test:**
```bash
# Verify Prefect installed
prefect version

# Verify concurrency limits
prefect concurrency-limit ls
```

**✅ Commit Point:**
```bash
git add requirements.txt
git commit -m "feat: install Prefect and configure concurrency limits"
```

---

### Milestone 1.2: PostgreSQL Advisory Locks Utility (2 hours)

**Create:** `document-processor/src/document_processor/utils/locks.py`

```python
"""PostgreSQL advisory lock utilities (no Redis needed)."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
import logging

from shared.database import AlfrdDatabase

logger = logging.getLogger(__name__)


def _string_to_lock_id(s: str) -> int:
    """
    Convert string to PostgreSQL advisory lock ID.
    
    PostgreSQL advisory locks use bigint (64-bit integer).
    Hash the string and take lower 63 bits (avoid negative numbers).
    """
    hash_digest = hashlib.md5(s.encode()).digest()
    lock_id = int.from_bytes(hash_digest[:8], 'big') & 0x7FFFFFFFFFFFFFFF
    return lock_id


@asynccontextmanager
async def document_type_lock(
    db: AlfrdDatabase,
    document_type: str,
    timeout_seconds: int = 300
):
    """
    Acquire exclusive PostgreSQL advisory lock for document type.
    
    Ensures only ONE document of type 'bill' is processed at a time
    (critical for prompt evolution).
    
    Uses PostgreSQL pg_advisory_lock() - session-level lock that's
    automatically released on connection close.
    
    Args:
        db: Database instance
        document_type: Document type to lock (e.g., "bill")
        timeout_seconds: Max time to wait for lock
    
    Example:
        async with document_type_lock(db, "bill"):
            # Only one "bill" document processes here
            await summarize_document(...)
    """
    lock_id = _string_to_lock_id(f"doctype:{document_type}")
    
    logger.info(f"Acquiring PG advisory lock for '{document_type}' (id={lock_id})")
    
    acquired = False
    async with db.pool.acquire() as conn:
        try:
            # Try to acquire lock with timeout
            start = asyncio.get_event_loop().time()
            while True:
                result = await conn.fetchval(
                    "SELECT pg_try_advisory_lock($1)",
                    lock_id
                )
                
                if result:  # Lock acquired
                    acquired = True
                    logger.info(f"Lock acquired for '{document_type}'")
                    break
                
                # Check timeout
                if asyncio.get_event_loop().time() - start > timeout_seconds:
                    raise TimeoutError(
                        f"Failed to acquire lock for '{document_type}' "
                        f"after {timeout_seconds}s"
                    )
                
                await asyncio.sleep(1)
            
            # Lock held - yield to caller
            try:
                yield
            finally:
                # Release lock
                if acquired:
                    await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
                    logger.info(f"Lock released for '{document_type}'")
        
        except Exception as e:
            logger.error(f"Error with advisory lock: {e}")
            if acquired:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
            raise
```

**Create:** `document-processor/src/document_processor/utils/__init__.py`

```python
"""Utilities for document processing."""

from .locks import document_type_lock

__all__ = ['document_type_lock']
```

**🧪 Test:** Create `document-processor/tests/test_locks.py`

```python
"""Test PostgreSQL advisory locks."""

import pytest
import asyncio
from uuid import uuid4

from shared.database import AlfrdDatabase
from shared.config import Settings
from document_processor.utils.locks import document_type_lock, _string_to_lock_id


def test_string_to_lock_id():
    """Test consistent lock ID generation."""
    lock_id1 = _string_to_lock_id("bill")
    lock_id2 = _string_to_lock_id("bill")
    assert lock_id1 == lock_id2
    assert lock_id1 > 0  # Positive integer
    
    # Different strings get different IDs
    assert _string_to_lock_id("bill") != _string_to_lock_id("finance")


@pytest.mark.asyncio
async def test_document_type_lock_basic():
    """Test basic lock acquisition and release."""
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    try:
        async with document_type_lock(db, "test_type"):
            # Lock is held
            pass
        
        # Lock should be released
        async with document_type_lock(db, "test_type"):
            # Can acquire again
            pass
    
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_document_type_lock_serialization():
    """Test that locks serialize access."""
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    results = []
    
    async def worker(worker_id: int):
        async with document_type_lock(db, "bill", timeout_seconds=10):
            results.append(f"start-{worker_id}")
            await asyncio.sleep(0.5)  # Simulate work
            results.append(f"end-{worker_id}")
    
    try:
        # Run 3 workers concurrently
        await asyncio.gather(
            worker(1),
            worker(2),
            worker(3)
        )
        
        # Verify serialization: each worker completes before next starts
        assert results == [
            'start-1', 'end-1',
            'start-2', 'end-2',
            'start-3', 'end-3'
        ] or results == [
            'start-2', 'end-2',
            'start-1', 'end-1',
            'start-3', 'end-3'
        ]  # Order may vary, but pairs must be together
        
        # Verify no interleaving
        for i in range(0, len(results), 2):
            worker_id = results[i].split('-')[1]
            assert results[i+1] == f'end-{worker_id}'
    
    finally:
        await db.close()
```

**Run tests:**
```bash
pytest document-processor/tests/test_locks.py -v
```

**✅ Commit Point:**
```bash
git add document-processor/src/document_processor/utils/
git add document-processor/tests/test_locks.py
git commit -m "feat: add PostgreSQL advisory lock utilities

- Implement document_type_lock for per-type serialization
- No Redis dependency - uses native PostgreSQL locks
- Add comprehensive tests for lock behavior
"
```

---

### Milestone 1.3: Core Document Processing Tasks (4 hours)

**Create:** `document-processor/src/document_processor/tasks/document_tasks.py`

```python
"""Document processing tasks with Prefect concurrency control."""

from prefect import task
from prefect.concurrency.asyncio import rate_limit
from uuid import UUID
import logging
import asyncio
from typing import Dict, Any

from shared.database import AlfrdDatabase
from shared.types import DocumentStatus, PromptType
from mcp_server.llm.bedrock import BedrockClient
from document_processor.utils.locks import document_type_lock

logger = logging.getLogger(__name__)


@task(
    name="OCR Document",
    retries=2,
    retry_delay_seconds=30,
    tags=["ocr", "aws"]
)
async def ocr_task(doc_id: UUID, db: AlfrdDatabase) -> str:
    """
    Extract text using AWS Textract.
    
    Limited to 3 concurrent executions via Prefect concurrency.
    """
    # Prefect rate limiting (max 3 concurrent across all workers)
    await rate_limit("aws-textract")
    
    from document_processor.extractors.aws_textract import extract_text_from_folder
    
    doc = await db.get_document(doc_id)
    if not doc:
        raise ValueError(f"Document {doc_id} not found")
    
    await db.update_document(doc_id, status=DocumentStatus.OCR_IN_PROGRESS)
    
    # Extract text
    result = extract_text_from_folder(doc['folder_path'])
    
    # Save to database
    await db.update_document(
        doc_id,
        extracted_text=result['full_text'],
        status=DocumentStatus.OCR_COMPLETED
    )
    
    logger.info(f"OCR completed: {doc_id} ({len(result['full_text'])} chars)")
    return result['full_text']


@task(
    name="Classify Document",
    retries=2,
    tags=["classify", "llm"]
)
async def classify_task(
    doc_id: UUID,
    extracted_text: str,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """Classify document using Bedrock LLM."""
    await rate_limit("aws-bedrock")
    
    from mcp_server.tools.classify_dynamic import classify_document_dynamic
    
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
        status=DocumentStatus.CLASSIFIED
    )
    
    # Add tags
    await db.add_tag_to_document(
        doc_id,
        classification['document_type'],
        created_by='system'
    )
    
    for tag in classification.get('tags', []):
        await db.add_tag_to_document(doc_id, tag, created_by='llm')
    
    logger.info(
        f"Classified {doc_id}: {classification['document_type']} "
        f"(confidence: {classification['confidence']:.2%})"
    )
    return classification


@task(
    name="Summarize Document",
    retries=2,
    tags=["summarize", "llm"]
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
    
    doc = await db.get_document(doc_id)
    document_type = doc['document_type']
    
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
        
        # Summarize
        from mcp_server.tools.summarize_dynamic import summarize_document_dynamic
        loop = asyncio.get_event_loop()
        summary_result = await loop.run_in_executor(
            None,
            summarize_document_dynamic,
            doc['extracted_text'],
            document_type,
            prompt['prompt_text'],
            bedrock_client
        )
        
        # Save
        await db.update_document(
            doc_id,
            summary=summary_result['summary'],
            structured_data=summary_result.get('structured_data', {}),
            status=DocumentStatus.SUMMARIZED
        )
        
        logger.info(f"Summarized {doc_id} (lock releasing)")
        return summary_result['summary']


@task(name="Score Classification", tags=["scoring", "llm"])
async def score_classification_task(
    doc_id: UUID,
    classification: Dict[str, Any],
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score classification quality and update prompt if improved."""
    await rate_limit("aws-bedrock")
    
    from mcp_server.tools.score_performance import score_classification
    from uuid import uuid4
    
    # Get documents count for this type
    docs = await db.list_documents(
        document_type=classification['document_type'],
        limit=1000
    )
    
    # Skip if too few documents
    if len(docs) < 5:
        logger.info(f"Skipping scoring - only {len(docs)} documents")
        await db.update_document(
            doc_id,
            status=DocumentStatus.SCORED_CLASSIFICATION
        )
        return 0.0
    
    # Score
    doc = await db.get_document(doc_id)
    prompt = await db.get_active_prompt(PromptType.CLASSIFIER)
    
    loop = asyncio.get_event_loop()
    score_result = await loop.run_in_executor(
        None,
        score_classification,
        doc['extracted_text'],
        classification,
        prompt['prompt_text'],
        bedrock_client
    )
    
    # Update prompt if significantly improved
    if score_result['score'] > (prompt.get('performance_score', 0) + 0.05):
        await db.deactivate_old_prompts(PromptType.CLASSIFIER)
        await db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.CLASSIFIER,
            prompt_text=score_result['suggested_prompt'],
            version=prompt['version'] + 1,
            performance_score=score_result['score']
        )
        logger.info(
            f"Updated classifier prompt: "
            f"v{prompt['version']+1}, score={score_result['score']}"
        )
    
    await db.update_document(
        doc_id,
        status=DocumentStatus.SCORED_CLASSIFICATION
    )
    return score_result['score']


@task(name="Score Summary", tags=["scoring", "llm"])
async def score_summary_task(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score summary quality and update prompt if improved."""
    await rate_limit("aws-bedrock")
    
    from mcp_server.tools.score_performance import score_summary
    from uuid import uuid4
    
    doc = await db.get_document(doc_id)
    document_type = doc['document_type']
    
    prompt = await db.get_active_prompt(PromptType.SUMMARIZER, document_type)
    if not prompt:
        await db.update_document(doc_id, status=DocumentStatus.SCORED_SUMMARY)
        return 0.0
    
    # Score
    loop = asyncio.get_event_loop()
    score_result = await loop.run_in_executor(
        None,
        score_summary,
        doc['extracted_text'],
        doc['summary'],
        doc.get('structured_data', {}),
        prompt['prompt_text'],
        document_type,
        bedrock_client
    )
    
    # Update prompt if improved
    if score_result['score'] > (prompt.get('performance_score', 0) + 0.05):
        await db.deactivate_old_prompts(PromptType.SUMMARIZER, document_type)
        await db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.SUMMARIZER,
            document_type=document_type,
            prompt_text=score_result['suggested_prompt'],
            version=prompt['version'] + 1,
            performance_score=score_result['score']
        )
        logger.info(
            f"Updated {document_type} summarizer prompt: "
            f"v{prompt['version']+1}, score={score_result['score']}"
        )
    
    await db.update_document(doc_id, status=DocumentStatus.SCORED_SUMMARY)
    return score_result['score']


@task(name="File Document (Series)", tags=["filing", "llm"])
async def file_task(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> UUID:
    """Detect series, create file, add tags."""
    from mcp_server.tools.detect_series import detect_series_with_retry
    from uuid import uuid4
    
    doc = await db.get_document(doc_id)
    tags = await db.get_document_tags(doc_id)
    
    # Detect series
    series_data = detect_series_with_retry(
        summary=doc['summary'],
        document_type=doc['document_type'],
        structured_data=doc.get('structured_data', {}),
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
    
    # Add to series
    await db.add_document_to_series(series['id'], doc_id)
    
    # Create series tag
    entity_slug = series_data['entity'].lower().replace(' ', '-').replace('&', 'and')
    series_tag = f"series:{entity_slug}"
    await db.add_tag_to_document(doc_id, series_tag, created_by='llm')
    
    # Create file
    file = await db.find_or_create_file(uuid4(), tags=[series_tag])
    
    await db.update_document(doc_id, status=DocumentStatus.FILED)
    logger.info(f"Filed {doc_id} into series {series['id']}, file {file['id']}")
    
    return file['id']


@task(name="Generate File Summary", tags=["file-generation", "llm"])
async def generate_file_summary_task(
    file_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> str:
    """Generate summary for file collection."""
    from mcp_server.tools.summarize_file import summarize_file_with_retry
    from datetime import datetime, timezone
    
    await rate_limit("file-generation")
    
    # Get file and documents
    file = await db.get_file(file_id)
    documents = await db.get_file_documents(file_id, order_by="created_at DESC")
    
    if not documents:
        logger.warning(f"No documents for file {file_id}")
        return ""
    
    # Build aggregated content
    content_parts = []
    for doc in documents:
        content_parts.append({
            'filename': doc['filename'],
            'date': doc['created_at'].isoformat(),
            'summary': doc.get('summary', ''),
            'structured_data': doc.get('structured_data', {})
        })
    
    # Generate file summary
    summary = summarize_file_with_retry(
        file_tags=file['tags'],
        documents=content_parts,
        bedrock_client=bedrock_client
    )
    
    # Save
    await db.update_file(
        file_id,
        summary_text=summary['summary_text'],
        summary_metadata=summary.get('metadata', {}),
        status='generated',
        last_generated_at=datetime.now(timezone.utc)
    )
    
    logger.info(f"Generated summary for file {file_id}")
    return summary['summary_text']
```

**Create:** `document-processor/src/document_processor/tasks/__init__.py`

```python
"""Prefect tasks for document processing."""

from .document_tasks import (
    ocr_task,
    classify_task,
    summarize_task,
    score_classification_task,
    score_summary_task,
    file_task,
    generate_file_summary_task
)

__all__ = [
    'ocr_task',
    'classify_task',
    'summarize_task',
    'score_classification_task',
    'score_summary_task',
    'file_task',
    'generate_file_summary_task'
]
```

**🧪 Test:** Create `document-processor/tests/test_tasks.py`

```python
"""Test Prefect tasks."""

import pytest
from prefect.testing.utilities import prefect_test_harness
from uuid import uuid4

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient
from document_processor.tasks import ocr_task, classify_task


@pytest.fixture(autouse=True, scope="session")
def prefect_test_fixture():
    """Enable Prefect test mode."""
    with prefect_test_harness():
        yield


@pytest.mark.asyncio
async def test_ocr_task_basic():
    """Test OCR task updates document status correctly."""
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    # Create test document (you'll need actual test folder)
    # This is a skeleton - adjust for your test setup
    doc_id = uuid4()
    
    # Mock or use real document
    # result = await ocr_task(doc_id, db)
    # assert result  # Has extracted text
    
    await db.close()


# Add more task tests as needed
```

**Run tests:**
```bash
pytest document-processor/tests/test_tasks.py -v
```

**✅ Commit Point:**
```bash
git add document-processor/src/document_processor/tasks/
git add document-processor/tests/test_tasks.py
git commit -m "feat: implement Prefect tasks for document processing

- Add OCR, classify, summarize tasks with rate limiting
- Implement scoring tasks for prompt evolution
- Add filing and file generation tasks
- Use PostgreSQL advisory locks for per-type serialization
- All tasks respect Prefect concurrency limits
"
```

---

## Day 2: Flows & Orchestration

### Milestone 2.1: Document Processing Flow (3 hours)

**Create:** `document-processor/src/document_processor/flows/document_flow.py`

```python
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
    logger.info(f"Processing document {doc_id}")
    
    # Step 1: OCR
    extracted_text = await ocr_task(doc_id, db)
    
    # Step 2: Classification
    classification = await classify_task(doc_id, extracted_text, db, bedrock_client)
    
    # Step 3: Parallel - score classification while starting summarization
    score_future = score_classification_task.submit(
        doc_id, classification, db, bedrock_client
    )
    
    # Step 4: Summarization (serialized per-type internally)
    summary = await summarize_task(doc_id, db, bedrock_client)
    
    # Wait for classification scoring
    await score_future.wait()
    
    # Step 5: Score summary
    await score_summary_task(doc_id, db, bedrock_client)
    
    # Step 6: File into series
    file_id = await file_task(doc_id, db, bedrock_client)
    
    logger.info(f"Document {doc_id} processing complete (filed into {file_id})")
    return "completed"
```

**Create:** `document-processor/src/document_processor/flows/file_flow.py`

```python
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
```

**Create:** `document-processor/src/document_processor/flows/__init__.py`

```python
"""Prefect flows for document processing."""

from .document_flow import process_document_flow
from .file_flow import generate_file_summary_flow

__all__ = [
    'process_document_flow',
    'generate_file_summary_flow'
]
```

**🧪 Test:** Create `document-processor/tests/test_flows.py`

```python
"""Test Prefect flows."""

import pytest
from prefect.testing.utilities import prefect_test_harness
from uuid import uuid4

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient
from document_processor.flows import process_document_flow


@pytest.fixture(autouse=True, scope="session")
def prefect_test_fixture():
    with prefect_test_harness():
        yield


@pytest.mark.asyncio
async def test_process_document_flow_structure():
    """Test that flow can be constructed (not full execution)."""
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    bedrock_client = BedrockClient(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_region=settings.aws_region
    )
    
    # Test flow structure (mock actual execution for now)
    # Full integration test will come later
    
    await db.close()
```

**Run tests:**
```bash
pytest document-processor/tests/test_flows.py -v
```

**✅ Commit Point:**
```bash
git add document-processor/src/document_processor/flows/
git add document-processor/tests/test_flows.py
git commit -m "feat: implement Prefect flows for document and file processing

- Add process_document_flow for complete pipeline
- Add generate_file_summary_flow (separate flow)
- Flows orchestrate tasks with proper dependencies
"
```

---

### Milestone 2.2: Orchestrator (3 hours)

**Create:** `document-processor/src/document_processor/flows/orchestrator.py`

```python
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
            
            # === Monitor Documents ===
            pending_docs = await db.get_documents_by_status(
                DocumentStatus.PENDING,
                limit=50
            )
            
            if pending_docs:
                logger.info(f"Found {len(pending_docs)} pending documents")
                
                # Launch document processing flows
                for doc in pending_docs:
                    process_document_flow.submit(
                        doc_id=doc['id'],
                        db=db,
                        bedrock_client=bedrock_client
                    )
                
                logger.info(f"Launched {len(pending_docs)} document flows")
            
            # === Monitor Files ===
            pending_files = await db.get_files_by_status(
                ['pending', 'outdated'],
                limit=20
            )
            
            if pending_files:
                logger.info(f"Found {len(pending_files)} files needing generation")
                
                # Launch file generation flows
                for file in pending_files:
                    generate_file_summary_flow.submit(
                        file_id=file['id'],
                        db=db,
                        bedrock_client=bedrock_client
                    )
                
                logger.info(f"Launched {len(pending_files)} file generation flows")
            
            # Exit if run-once mode
            if run_once:
                logger.info("Run-once mode: waiting for flows to complete")
                # Wait a bit for flows to start processing
                await asyncio.sleep(5)
                break
            
            # Poll interval
            await asyncio.sleep(10)
    
    finally:
        await db.close()
        logger.info("Orchestrator shutdown complete")
```

**🧪 Test:** Create `document-processor/tests/test_orchestrator.py`

```python
"""Test orchestrator flow."""

import pytest
from prefect.testing.utilities import prefect_test_harness

from shared.config import Settings
from document_processor.flows.orchestrator import main_orchestrator_flow


@pytest.fixture(autouse=True, scope="session")
def prefect_test_fixture():
    with prefect_test_harness():
        yield


@pytest.mark.asyncio
async def test_orchestrator_run_once():
    """Test orchestrator in run-once mode."""
    settings = Settings()
    
    # Run orchestrator once
    await main_orchestrator_flow(settings, run_once=True)
    
    # Should complete without errors
```

**Run tests:**
```bash
pytest document-processor/tests/test_orchestrator.py -v
```

**✅ Commit Point:**
```bash
git add document-processor/src/document_processor/flows/orchestrator.py
git add document-processor/tests/test_orchestrator.py
git commit -m "feat: implement orchestrator for DB monitoring and flow launching

- Monitor documents and files tables
- Launch appropriate flows based on status
- Support run-once and continuous modes
- Replace worker polling architecture
"
```

---

### Milestone 2.3: New Entry Point (2 hours)

**Create:** `document-processor/src/document_processor/main_prefect.py`

```python
"""Prefect-based document processor entry point."""

import asyncio
import argparse
from pathlib import Path
import sys
from uuid import UUID

# Path setup
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

from shared.config import Settings
from shared.database import AlfrdDatabase
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient
from document_processor.flows.orchestrator import main_orchestrator_flow
from document_processor.flows import process_document_flow


async def scan_inbox_and_create_pending(settings: Settings):
    """
    Scan inbox for new folders and create pending database entries.
    
    (Existing logic from old main.py - unchanged)
    """
    from document_processor.detector import FileDetector
    from shared.constants import META_JSON_FILENAME
    from datetime import datetime, timezone
    import json
    import shutil
    
    detector = FileDetector()
    inbox = settings.inbox_path
    
    if not inbox.exists():
        inbox.mkdir(parents=True, exist_ok=True)
        return
    
    folders = [f for f in inbox.iterdir() if f.is_dir()]
    if not folders:
        return
    
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
        
        if new_count > 0:
            print(f"✅ Registered {new_count} new document(s)")
    
    finally:
        await db.close()


async def main(run_once: bool = False, doc_id: str = None):
    """Main entry point."""
    settings = Settings()
    
    print("\n" + "=" * 80)
    print("🚀 ALFRD Document Processor - Prefect Mode")
    if run_once:
        print("   Mode: Run once and exit")
    if doc_id:
        print(f"   Processing single document: {doc_id}")
    print("=" * 80)
    print()
    
    # Process single document
    if doc_id:
        print(f"Processing document {doc_id}...")
        
        db = AlfrdDatabase(settings.database_url)
        await db.initialize()
        
        bedrock_client = BedrockClient(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_region=settings.aws_region
        )
        
        try:
            await process_document_flow(UUID(doc_id), db, bedrock_client)
            print(f"✅ Document {doc_id} processed")
        finally:
            await db.close()
        
        return
    
    # Scan inbox first
    print("📂 Scanning inbox for new documents...")
    await scan_inbox_and_create_pending(settings)
    print()
    
    # Run orchestrator
    print("🔧 Starting Prefect orchestrator...")
    await main_orchestrator_flow(settings, run_once=run_once)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ALFRD Document Processor (Prefect)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process all pending documents and exit"
    )
    parser.add_argument(
        "--doc-id",
        help="Process single document by ID"
    )
    args = parser.parse_args()
    
    asyncio.run(main(run_once=args.once, doc_id=args.doc_id))
```

**🧪 Test:**
```bash
# Test run-once mode (should complete without error)
python document-processor/src/document_processor/main_prefect.py --once

# Test help
python document-processor/src/document_processor/main_prefect.py --help
```

**✅ Commit Point:**
```bash
git add document-processor/src/document_processor/main_prefect.py
git commit -m "feat: add new Prefect-based entry point

- Implement main_prefect.py with orchestrator integration
- Retain inbox scanning logic
- Support --once and --doc-id arguments
- Ready to replace old main.py
"
```

---

## Day 3: Cleanup & Integration

### Milestone 3.1: Switch to Prefect Entry Point (1 hour)

**Backup old main.py:**
```bash
mv document-processor/src/document_processor/main.py \
   document-processor/src/document_processor/main_old.py
```

**Rename new entry point:**
```bash
mv document-processor/src/document_processor/main_prefect.py \
   document-processor/src/document_processor/main.py
```

**Update scripts:**

Edit `scripts/start-processor`:
```bash
#!/bin/bash
# Start document processor with Prefect

python3 document-processor/src/document_processor/main.py
```

**🧪 Test:**
```bash
# Test new entry point
./scripts/start-processor --once

# Should work exactly like before but using Prefect
```

**✅ Commit Point:**
```bash
git add document-processor/src/document_processor/main.py
git add document-processor/src/document_processor/main_old.py
git add scripts/start-processor
git commit -m "feat: switch to Prefect-based entry point

- Rename main_prefect.py to main.py
- Backup old main.py as main_old.py
- Update start-processor script
"
```

---

### Milestone 3.2: Delete Old Worker Infrastructure (1 hour)

**Delete old worker files:**
```bash
git rm document-processor/src/document_processor/workers.py
git rm document-processor/src/document_processor/ocr_worker.py
git rm document-processor/src/document_processor/classifier_worker.py
git rm document-processor/src/document_processor/summarizer_worker.py
git rm document-processor/src/document_processor/scorer_workers.py
git rm document-processor/src/document_processor/filing_worker.py
git rm document-processor/src/document_processor/file_generator_worker.py
```

**Remove database triggers:**

Edit `api-server/src/api_server/db/schema.sql`:
- Remove `document_tags_invalidate_files` trigger
- Add comment explaining invalidation is now handled in Prefect flows

**🧪 Test:**
```bash
# Ensure system still works without old workers
./scripts/start-processor --once

# Check for import errors
python -m py_compile document-processor/src/document_processor/main.py
```

**✅ Commit Point:**
```bash
git add api-server/src/api_server/db/schema.sql
git commit -m "refactor: remove old worker infrastructure

- Delete workers.py and all worker classes (~1,500 lines)
- Remove database trigger (now handled in flows)
- Prefect tasks and flows fully replace workers
"
```

---

### Milestone 3.3: Integration Testing (2 hours)

**Create:** `document-processor/tests/integration/test_full_pipeline.py`

```python
"""Integration test for full document processing pipeline."""

import pytest
import asyncio
from uuid import uuid4
from pathlib import Path

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient
from document_processor.flows import process_document_flow


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_document_pipeline():
    """
    Test complete document processing pipeline end-to-end.
    
    This requires:
    - Real AWS credentials
    - Test document in test-dataset-generator/output/
    """
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    bedrock_client = BedrockClient(
        aws_access_key_id=settings.aws_access_key_id,
        aws_secret_access_key=settings.aws_secret_access_key,
        aws_region=settings.aws_region
    )
    
    try:
        # Use a test document from dataset
        # (Adjust path to your test files)
        test_file = Path("test-dataset-generator/output/bills/pge_2024_01.jpg")
        
        if not test_file.exists():
            pytest.skip("Test dataset not available")
        
        # Create test document
        doc_id = uuid4()
        # ... (create document in DB with status=PENDING)
        
        # Run full pipeline
        result = await process_document_flow(doc_id, db, bedrock_client)
        
        # Verify
        doc = await db.get_document(doc_id)
        assert doc['status'] == DocumentStatus.FILED
        assert doc['extracted_text'] is not None
        assert doc['document_type'] is not None
        assert doc['summary'] is not None
        
        print(f"✅ Full pipeline test passed for {doc_id}")
    
    finally:
        await db.close()
```

**Run integration tests:**
```bash
pytest document-processor/tests/integration/ -v -m integration
```

**🧪 Manual Test:**
```bash
# Process a real document end-to-end
./scripts/add-document test-dataset-generator/output/bills/pge_2024_01.jpg --tags test
./scripts/start-processor --once

# Verify in database
./scripts/view-document
```

**✅ Commit Point:**
```bash
git add document-processor/tests/integration/
git commit -m "test: add integration tests for full pipeline

- Test complete document processing flow
- Verify all statuses transition correctly
- Manual testing with real documents passing
"
```

---

### Milestone 3.4: Update Documentation (1 hour)

**Update:** `README.md`

Add section on Prefect architecture:
```markdown
## Architecture (Prefect-Based)

ALFRD uses **Prefect** for workflow orchestration:

- **Tasks**: Pure functions with retry/rate limiting
- **Flows**: DAG-based pipelines (document processing, file generation)
- **Orchestrator**: Monitors DB and launches flows
- **Concurrency**: Global limits via Prefect (3 OCR, 5 LLM, 2 file gen)
- **Serialization**: PostgreSQL advisory locks (no Redis!)

See `WORKFLOW_REFACTORING_PLAN.md` for migration details.
```

**Create:** `docs/PREFECT_ARCHITECTURE.md`

```markdown
# Prefect Architecture

## Overview

ALFRD uses Prefect for workflow orchestration, replacing custom worker polling.

## Key Components

### Tasks
- **Pure functions** with `@task` decorator
- **Rate limiting** via `rate_limit("name")`
- **Retries** and timeouts built-in
- Located in: `document-processor/src/document_processor/tasks/`

### Flows
- **process_document_flow**: Main document pipeline
- **generate_file_summary_flow**: File generation (separate)
- Located in: `document-processor/src/document_processor/flows/`

### Orchestrator
- Monitors `documents` and `files` tables
- Launches flows based on status
- Runs continuously or in run-once mode

## Concurrency Control

### Prefect Limits
```bash
prefect concurrency-limit create aws-textract 3
prefect concurrency-limit create aws-bedrock 5
prefect concurrency-limit create file-generation 2
```

### PostgreSQL Advisory Locks
- Per-document-type serialization
- Prevents prompt evolution conflicts
- No Redis dependency

## Running

```bash
# Continuous mode
python document-processor/src/document_processor/main.py

# Run once
python document-processor/src/document_processor/main.py --once

# Single document
python document-processor/src/document_processor/main.py --doc-id <uuid>
```
```

**✅ Commit Point:**
```bash
git add README.md
git add docs/PREFECT_ARCHITECTURE.md
git commit -m "docs: update documentation for Prefect architecture

- Add Prefect section to README
- Create PREFECT_ARCHITECTURE.md guide
- Document concurrency control mechanisms
"
```

---

## Day 4: Final Testing & Deployment

### Milestone 4.1: Comprehensive Testing (2 hours)

**Run all tests:**
```bash
# Unit tests
pytest document-processor/tests/test_locks.py -v
pytest document-processor/tests/test_tasks.py -v
pytest document-processor/tests/test_flows.py -v

# Integration tests
pytest document-processor/tests/integration/ -v -m integration

# Database tests
pytest shared/tests/test_database.py -v
```

**Load test:**
```bash
# Add multiple documents
for i in {1..10}; do
    ./scripts/add-document test-dataset-generator/output/bills/pge_2024_0$i.jpg \
        --tags test
done

# Process all at once
./scripts/start-processor --once

# Monitor progress
watch -n 1 'psql -U alfrd_user -d alfrd -c "SELECT status, COUNT(*) FROM documents GROUP BY status;"'
```

**✅ Test Checklist:**
- [ ] All unit tests passing
- [ ] Integration tests passing
- [ ] Can process 10+ documents concurrently
- [ ] Concurrency limits respected (check logs)
- [ ] PostgreSQL advisory locks working (no duplicate processing)
- [ ] File generation triggers correctly
- [ ] Prompt evolution still works

---

### Milestone 4.2: Production Deployment (2 hours)

**Update Docker configuration:**

Edit `docker/supervisord.conf`:
```ini
[program:document_processor]
command=/app/venv/bin/python document-processor/src/document_processor/main.py
directory=/app
autostart=true
autorestart=true
stdout_logfile=/dev/stdout
stdout_logfile_maxbytes=0
stderr_logfile=/dev/stderr
stderr_logfile_maxbytes=0
```

**Update `docker/Dockerfile` if needed:**
```dockerfile
# Add Prefect
RUN pip install prefect prefect-aws
```

**Test Docker:**
```bash
docker-compose -f docker/docker-compose.yml build
docker-compose -f docker/docker-compose.yml up -d
docker-compose -f docker/docker-compose.yml logs -f document_processor
```

**✅ Deployment Checklist:**
- [ ] Docker build successful
- [ ] All services start correctly
- [ ] Document processor running via supervisord
- [ ] Logs showing Prefect orchestrator iterations
- [ ] Can process documents through Docker

**✅ Final Commit:**
```bash
git add docker/
git commit -m "build: update Docker configuration for Prefect

- Update supervisord.conf for new entry point
- Add Prefect to Dockerfile
- Tested in Docker environment
"
```

---

## Post-Migration Cleanup

### After 1 Week of Stable Operation

**Remove old backup file:**
```bash
git rm document-processor/src/document_processor/main_old.py
git commit -m "cleanup: remove old main.py backup after successful migration"
```

**Archive this plan:**
```bash
mv WORKFLOW_REFACTORING_PLAN.md docs/archive/
git add docs/archive/WORKFLOW_REFACTORING_PLAN.md
git commit -m "docs: archive migration plan after completion"
```

---

## Rollback Plan

If critical issues arise:

```bash
# 1. Checkout previous commit
git log --oneline  # Find commit before "feat: switch to Prefect-based entry point"
git checkout <commit-hash>

# 2. Restart services
docker-compose -f docker/docker-compose.yml restart

# 3. Verify old system works
./scripts/start-processor --once
```

---

## Success Criteria

**Migration is complete when:**
- [x] All 7 workers replaced with Prefect tasks/flows
- [x] Concurrency limits enforced (AWS, file generation)
- [x] Per-type serialization working (PostgreSQL locks)
- [x] DB monitoring and flow launching operational
- [x] All tests passing
- [x] Docker deployment successful
- [x] No Redis dependency
- [x] Documentation updated

**Benefits Achieved:**
- ✅ Visual DAG in Prefect UI (if using Prefect server)
- ✅ Simpler codebase (~1,500 lines removed)
- ✅ Better observability (task-level metrics)
- ✅ Built-in retry/timeout logic
- ✅ Explicit dependencies (no implicit worker order)
- ✅ PostgreSQL-only infrastructure (no Redis!)

---

## Summary Timeline

| Day | Milestone | Hours | Test Points | Commit Points |
|-----|-----------|-------|-------------|---------------|
| 1 | Setup & PG Locks | 2 | Prefect installed, locks tested | 1 |
| 1 | PG Lock Utility | 2 | Lock serialization verified | 1 |
| 1 | Core Tasks | 4 | Task tests passing | 1 |
| 2 | Document Flow | 3 | Flow tests passing | 1 |
| 2 | Orchestrator | 3 | Orchestrator tested | 1 |
| 2 | New Entry Point | 2 | Entry point working | 1 |
| 3 | Switch Entry Point | 1 | Old system backed up | 1 |
| 3 | Delete Old Workers | 1 | No import errors | 1 |
| 3 | Integration Tests | 2 | Full pipeline tested | 1 |
| 3 | Documentation | 1 | Docs updated | 1 |
| 4 | Final Testing | 2 | Load tests passing | 0 |
| 4 | Deployment | 2 | Docker working | 1 |
| **Total** | | **25 hours** | **12 test points** | **11 commits** |

---

**Ready to begin? Start with Day 1, Milestone 1.1!** 🚀