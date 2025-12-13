# Series-Specific Prompt Evolution - Implementation Plan

**Date:** 2025-12-10
**Based on:** Current document_tasks.py analysis
**Goal:** Add series-specific extraction while maintaining generic extraction

---

## ⚠️ IMPORTANT: Hard Schema Cut

**This implementation requires a fresh database creation. No migrations needed.**

**Steps:**
1. Drop and recreate the database: `./scripts/create-alfrd-db`
2. Schema changes are in `api-server/src/api_server/db/schema.sql`
3. All existing data will be lost (test environment)

**Why hard cut:** This is a development/testing phase. Cleaner to start fresh than manage complex migrations.

---

## Current Pipeline (from document_tasks.py)

```
1. ocr_step() → status: OCR_COMPLETED
2. classify_step() → status: CLASSIFIED
3. score_classification_step() → status: SCORED_CLASSIFICATION → status: SUMMARIZING
4. summarize_step() → status: SUMMARIZED
5. score_summary_step() → status: FILED
6. file_step() → creates series, adds tags → status: FILED
7. generate_file_summary_step() → creates file summary
```

---

## Proposed New Pipeline

```
1. ocr_step() → status: OCR_COMPLETED
2. classify_step() → status: CLASSIFIED
3. score_classification_step() → status: SCORED_CLASSIFICATION → status: SUMMARIZING
4. summarize_step() → status: SUMMARIZED (generic extraction)
5. score_summary_step() → status: FILED
6. file_step() → creates series, adds tags → status: FILED
7. ✨ NEW: series_summarize_step() → status: SERIES_SUMMARIZED (series-specific extraction)
8. ✨ NEW: score_series_step() → evolves series prompt, triggers regeneration if needed
9. generate_file_summary_step() → creates file summary
```

---

## Implementation Phases

### Phase 1: Database Schema (Week 1, Day 1-2)

#### Checkpoint 1.1: Update schema.sql (NO MIGRATIONS!)

**File:** `api-server/src/api_server/db/schema.sql`

Add to existing schema (find the relevant sections and add):

```sql
-- 1. Update prompts table constraint (find existing constraint)
ALTER TABLE prompts DROP CONSTRAINT IF EXISTS prompts_prompt_type_check;
ALTER TABLE prompts ADD CONSTRAINT prompts_prompt_type_check
    CHECK (prompt_type IN (
        'classifier',
        'summarizer',
        'file_summarizer',
        'series_detector',
        'series_summarizer'  -- NEW!
    ));

-- 2. Add to documents table (add after existing columns)
ALTER TABLE documents
ADD COLUMN structured_data_series JSONB,
ADD COLUMN series_prompt_id UUID REFERENCES prompts(id),
ADD COLUMN extraction_method VARCHAR DEFAULT 'generic' CHECK (
    extraction_method IN ('generic', 'series', 'both')
);

-- 3. Add to series table (add after existing columns)
ALTER TABLE series
ADD COLUMN active_prompt_id UUID REFERENCES prompts(id),
ADD COLUMN last_schema_update TIMESTAMP WITH TIME ZONE,
ADD COLUMN regeneration_pending BOOLEAN DEFAULT FALSE;

-- 4. Add indexes (add to index section at bottom)
CREATE INDEX idx_documents_series_data ON documents USING GIN(structured_data_series);
CREATE INDEX idx_documents_extraction_method ON documents(extraction_method);
CREATE INDEX idx_series_active_prompt ON series(active_prompt_id) WHERE active_prompt_id IS NOT NULL;
```

**Then recreate database:**
```bash
# Drop and recreate
./scripts/create-alfrd-db

# Verify changes
psql -U alfrd_user -d alfrd -c "\d documents" | grep series
psql -U alfrd_user -d alfrd -c "\d series" | grep prompt
```

✅ **Checkpoint:** Fresh database with new schema

---

#### Checkpoint 1.2: Update DocumentStatus

**File:** `shared/types.py`

```python
# Add new statuses
class DocumentStatus:
    # ... existing statuses ...
    SERIES_SUMMARIZED = "series_summarized"  # NEW!
    SERIES_SCORING = "series_scoring"  # NEW!
```

**Test:**
```python
from shared.types import DocumentStatus
assert hasattr(DocumentStatus, 'SERIES_SUMMARIZED')
assert hasattr(DocumentStatus, 'SERIES_SCORING')
```

✅ **Checkpoint:** New statuses accessible in code

---

### Phase 2: Series Prompt Creation Tool (Week 1, Day 3-4)

#### Checkpoint 2.1: Create Series Summarizer Tool

**File:** `mcp-server/src/mcp_server/tools/summarize_series.py`

```python
"""Series-specific document summarization with schema enforcement."""

import json
from typing import Dict, Any, Optional
from mcp_server.llm.bedrock import BedrockClient


def create_series_prompt_from_generic(
    generic_prompt: str,
    series_entity: str,
    series_type: str,
    sample_document: str,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """
    Create first series-specific prompt by analyzing a sample document.
    
    Args:
        generic_prompt: Base generic summarizer prompt
        series_entity: Entity name (e.g., "Pacific Gas & Electric")
        series_type: Series type (e.g., "monthly_utility_bill")
        sample_document: Sample document text for analysis
        bedrock_client: Bedrock client
        
    Returns:
        Dict with 'prompt_text' and 'schema_definition'
    """
    # Ask LLM to analyze document and suggest schema
    analysis_prompt = f"""You are analyzing a document to create a specialized extraction schema.

Entity: {series_entity}
Series Type: {series_type}

Generic Prompt:
{generic_prompt}

Sample Document:
{sample_document[:3000]}

Based on this document, create:
1. A strict JSON schema for extracting data from ALL documents in this series
2. An improved extraction prompt specifically tailored to {series_entity}'s format

Requirements:
- Use EXACT field names (lowercase_with_underscores)
- Specify data types clearly (string, number, boolean, date)
- Include validation rules (formats, required fields)
- Note vendor-specific quirks or patterns

Return as JSON:
{{
  "prompt_text": "Improved extraction prompt...",
  "schema_definition": {{
    "required_fields": [...],
    "optional_fields": [...],
    "field_definitions": {{...}},
    "vendor_notes": "..."
  }}
}}
"""
    
    response = bedrock_client.invoke_model(
        prompt=analysis_prompt,
        max_tokens=2000,
        temperature=0.3
    )
    
    result = json.loads(response)
    return result


def summarize_with_series_prompt(
    document_text: str,
    series_prompt_text: str,
    schema_definition: Dict[str, Any],
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """
    Summarize document using series-specific prompt.
    
    Args:
        document_text: Full document text
        series_prompt_text: Series-specific extraction prompt
        schema_definition: Expected schema for validation
        bedrock_client: Bedrock client
        
    Returns:
        Structured data extracted according to series schema
    """
    # Build prompt with schema enforcement
    full_prompt = f"""{series_prompt_text}

Expected Schema:
{json.dumps(schema_definition, indent=2)}

CRITICAL: Return JSON matching this EXACT schema.

Document:
{document_text}
"""
    
    response = bedrock_client.invoke_model(
        prompt=full_prompt,
        max_tokens=2000,
        temperature=0.1  # Low temp for consistency
    )
    
    # Parse and validate
    try:
        result = json.loads(response)
        # TODO: Add schema validation here
        return result
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON response from LLM: {e}")
```

**Test:**
```python
# Test with PG&E bill
from mcp_server.tools.summarize_series import create_series_prompt_from_generic
from mcp_server.llm.bedrock import BedrockClient

bedrock = BedrockClient()
generic_prompt = "Extract key information from utility bills..."
sample_text = open("samples/pg&e-bill.jpg").read()

result = create_series_prompt_from_generic(
    generic_prompt=generic_prompt,
    series_entity="Pacific Gas & Electric",
    series_type="monthly_utility_bill",
    sample_document=sample_text,
    bedrock_client=bedrock
)

assert 'prompt_text' in result
assert 'schema_definition' in result
print(f"Created schema with {len(result['schema_definition'])} fields")
```

✅ **Checkpoint:** Series prompt creation works, generates valid schema

---

### Phase 3: Add Series Summarize Step (Week 1, Day 5-6)

#### Checkpoint 3.1: New Task Function

**File:** `document-processor/src/document_processor/tasks/document_tasks.py`

Add after `file_step()`:

```python
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
    
    logger.info(f"Series summarizing document {doc_id}")
    
    try:
        doc = await db.get_document(doc_id)
        
        # Get series from document_series junction table
        series_list = await db.get_document_series(doc_id)
        if not series_list:
            logger.warning(f"Document {doc_id} not in any series, skipping")
            await db.update_document(doc_id, status=DocumentStatus.COMPLETED)
            return {}
        
        # Use first series (most documents are in one series)
        series_id = series_list[0]['series_id']
        series = await db.get_series(series_id)
        
        # Check if series has active prompt
        series_prompt = None
        if series.get('active_prompt_id'):
            series_prompt = await db.get_prompt(series['active_prompt_id'])
        
        # If no series prompt, create one
        if not series_prompt:
            logger.info(f"Creating first series prompt for series {series_id}")
            
            # Get generic prompt for this document type
            generic_prompt = await db.get_active_prompt(
                PromptType.SUMMARIZER,
                doc['document_type']
            )
            
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
            series_prompt = await db.create_prompt(
                prompt_id=uuid4(),
                prompt_type='series_summarizer',
                document_type=str(series_id),  # Store series_id as document_type
                prompt_text=prompt_data['prompt_text'],
                version=1,
                performance_metrics={
                    'schema_definition': prompt_data['schema_definition'],
                    'documents_processed': 0
                }
            )
            
            # Link to series
            await db.update_series(
                series_id,
                active_prompt_id=series_prompt['id']
            )
            
            logger.info(f"Created series prompt {series_prompt['id']} for series {series_id}")
        
        # Extract schema from performance_metrics
        perf_metrics = series_prompt.get('performance_metrics', {})
        if isinstance(perf_metrics, str):
            perf_metrics = json.loads(perf_metrics)
        schema_def = perf_metrics.get('schema_definition', {})
        
        # Summarize with series prompt
        loop = asyncio.get_event_loop()
        series_extraction = await loop.run_in_executor(
            None,
            summarize_with_series_prompt,
            doc['extracted_text'],
            series_prompt['prompt_text'],
            schema_def,
            bedrock_client
        )
        
        # Save series-specific extraction
        await db.update_document(
            doc_id,
            structured_data_series=json.dumps(series_extraction),
            series_prompt_id=series_prompt['id'],
            extraction_method='both',  # Has both generic and series
            status=DocumentStatus.SERIES_SUMMARIZED
        )
        
        logger.info(f"Series summarization complete for {doc_id}")
        return series_extraction
        
    except Exception as e:
        logger.error(f"Series summarization failed for {doc_id}: {e}", exc_info=True)
        
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='series_summarize_step')
        
        await db.update_document(doc_id, status=DocumentStatus.FAILED, error_message=str(e))
        raise
```

✅ **Checkpoint:** New step compiles and can be called

---

#### Checkpoint 3.2: Database Helper Functions

**File:** `shared/database.py`

Add these methods to `AlfrdDatabase` class:

```python
async def get_document_series(self, document_id: UUID) -> List[Dict[str, Any]]:
    """Get all series this document belongs to."""
    async with self.pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT s.*, ds.added_at
            FROM series s
            JOIN document_series ds ON s.id = ds.series_id
            WHERE ds.document_id = $1
        """, document_id)
        return [dict(r) for r in rows]


async def get_series(self, series_id: UUID) -> Dict[str, Any]:
    """Get series by ID."""
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM series WHERE id = $1
        """, series_id)
        return dict(row) if row else None


async def get_prompt(self, prompt_id: UUID) -> Dict[str, Any]:
    """Get prompt by ID."""
    async with self.pool.acquire() as conn:
        row = await conn.fetchrow("""
            SELECT * FROM prompts WHERE id = $1
        """, prompt_id)
        return dict(row) if row else None
```

✅ **Checkpoint:** Database functions work, can query series and prompts

---

### Phase 4: Update Orchestrator (Week 1, Day 7)

#### Checkpoint 4.1: Add Step to Pipeline

**File:** `document-processor/src/document_processor/orchestrator.py`

Find the document processing loop and add:

```python
# After file_step completes:
elif doc['status'] == DocumentStatus.FILED:
    # NEW: Series summarization
    try:
        await series_summarize_step(doc_id, db, bedrock_client)
        logger.info(f"Document {doc_id}: Series summarization complete")
    except Exception as e:
        logger.error(f"Series summarization failed for {doc_id}: {e}")
        # Don't block pipeline - mark as completed anyway
        await db.update_document(doc_id, status=DocumentStatus.COMPLETED)

elif doc['status'] == DocumentStatus.SERIES_SUMMARIZED:
    # Mark as complete (scoring happens in background)
    await db.update_document(doc_id, status=DocumentStatus.COMPLETED)
    logger.info(f"Document {doc_id}: Processing complete")
```

✅ **Checkpoint:** Pipeline runs with new step, documents progress through

---

### Phase 5: API & Display (Week 2, Day 1-2)

#### Checkpoint 5.1: Prefer Series Data in API

**File:** `api-server/src/api_server/main.py`

Update `/api/v1/documents/{id}` endpoint:

```python
@app.get("/api/v1/documents/{document_id}")
async def get_document(document_id: str):
    """Get document details."""
    doc = await db.get_document(UUID(document_id))
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # PREFER series extraction for display
    structured_data = doc.get('structured_data_series') or doc.get('structured_data')
    
    # Parse if string
    if isinstance(structured_data, str):
        structured_data = json.loads(structured_data) if structured_data else {}
    
    return {
        **doc,
        'structured_data': structured_data,  # Series data (or fallback to generic)
        'has_series_extraction': bool(doc.get('structured_data_series')),
        'extraction_method': doc.get('extraction_method', 'generic')
    }
```

Update `/api/v1/files/{id}` endpoint:

```python
@app.get("/api/v1/files/{file_id}")
async def get_file(file_id: str):
    """Get file with documents."""
    file = await db.get_file(UUID(file_id))
    documents = await db.get_file_documents(UUID(file_id))
    
    # Use series extraction for all documents
    for doc in documents:
        doc['structured_data'] = (
            doc.get('structured_data_series') or 
            doc.get('structured_data')
        )
    
    return {
        'file': file,
        'documents': documents
    }
```

✅ **Checkpoint:** API returns series data when available

---

### Phase 6: Series Prompt Evolution (Week 2, Day 3-5)

#### Checkpoint 6.1: Scoring Step

**File:** `document-processor/src/document_processor/tasks/document_tasks.py`

Add background scoring (similar to existing score_summary_step):

```python
async def score_series_extraction_step(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score series extraction and evolve prompt if improved."""
    async with _bedrock_semaphore:
        return await _score_series_extraction_impl(doc_id, db, bedrock_client)


async def _score_series_extraction_impl(
    doc_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> float:
    """Score series extraction quality."""
    from mcp_server.tools.score_performance import score_summarization, evolve_prompt
    from uuid import uuid4
    from shared.config import Settings
    
    settings = Settings()
    
    logger.info(f"Scoring series extraction for {doc_id}")
    
    try:
        doc = await db.get_document(doc_id)
        
        if not doc.get('series_prompt_id'):
            return 0.0
        
        series_prompt = await db.get_prompt(doc['series_prompt_id'])
        
        # Parse series extraction
        series_data = doc.get('structured_data_series', {})
        if isinstance(series_data, str):
            series_data = json.loads(series_data) if series_data else {}
        
        # Build document info
        document_info = {
            'extracted_text': doc['extracted_text'],
            'filename': doc['filename'],
            'document_type': doc['document_type'],
            'structured_data': series_data
        }
        
        # Score (reuse existing scoring logic)
        loop = asyncio.get_event_loop()
        score_result = await loop.run_in_executor(
            None,
            score_summarization,
            document_info,
            series_prompt['prompt_text'],
            bedrock_client
        )
        
        # Update prompt performance metrics
        perf_metrics = series_prompt.get('performance_metrics', {})
        if isinstance(perf_metrics, str):
            perf_metrics = json.loads(perf_metrics)
        
        docs_processed = perf_metrics.get('documents_processed', 0) + 1
        perf_metrics['documents_processed'] = docs_processed
        
        await db.update_prompt_performance(
            series_prompt['id'],
            performance_score=score_result['score'],
            performance_metrics=perf_metrics
        )
        
        # Check if evolution needed (min 3 docs, improvement > 0.1)
        current_score = series_prompt.get('performance_score', 0)
        if docs_processed >= 3 and score_result['score'] > (current_score + 0.1):
            logger.info(f"Series prompt improved significantly, evolving...")
            
            # Evolve prompt
            new_prompt_text = await loop.run_in_executor(
                None,
                evolve_prompt,
                series_prompt['prompt_text'],
                'series_summarizer',
                series_prompt['document_type'],  # series_id
                score_result.get('feedback', ''),
                score_result.get('suggested_improvements', ''),
                None,
                bedrock_client
            )
            
            # Create new version
            new_version = await db.create_prompt(
                prompt_id=uuid4(),
                prompt_type='series_summarizer',
                document_type=series_prompt['document_type'],  # series_id
                prompt_text=new_prompt_text,
                version=series_prompt['version'] + 1,
                performance_metrics=perf_metrics,
                performance_score=score_result['score']
            )
            
            # Deactivate old, activate new
            await db.update_prompt(series_prompt['id'], is_active=False)
            await db.update_prompt(new_version['id'], is_active=True)
            
            # Update series
            series_id = UUID(series_prompt['document_type'])
            await db.update_series(
                series_id,
                active_prompt_id=new_version['id'],
                regeneration_pending=True
            )
            
            logger.info(
                f"Updated series prompt to v{new_version['version']}, "
                f"score={score_result['score']:.2f}, marking for regeneration"
            )
            
            # TODO: Trigger regeneration (Phase 7)
        
        return score_result['score']
        
    except Exception as e:
        logger.error(f"Series scoring failed for {doc_id}: {e}", exc_info=True)
        from shared.logging_config import log_exception
        log_exception(e, entity_type='document', entity_id=doc_id,
                     task_name='score_series_extraction_step')
        raise
```

✅ **Checkpoint:** Scoring runs, prompts evolve when quality improves

---

### Phase 7: Series Regeneration (Week 2, Day 6-7)

#### Checkpoint 7.1: Manual Regeneration Command

**File:** `scripts/regenerate-series`

```bash
#!/usr/bin/env python3
"""Regenerate all documents in a series with improved prompt."""

import asyncio
from uuid import UUID
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.database import AlfrdDatabase
from mcp_server.llm.bedrock import BedrockClient
from document_processor.tasks.document_tasks import series_summarize_step
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def regenerate_series(series_id: UUID):
    """Regenerate all documents in series."""
    db = AlfrdDatabase()
    bedrock_client = BedrockClient()
    
    try:
        await db.connect()
        
        # Get series and documents
        series = await db.get_series(series_id)
        if not series:
            print(f"Series {series_id} not found")
            return
        
        documents = await db.get_series_documents_list(series_id)
        print(f"Regenerating {len(documents)} documents in series: {series['title']}")
        
        for i, doc_id in enumerate(documents, 1):
            try:
                print(f"[{i}/{len(documents)}] Processing {doc_id}...")
                await series_summarize_step(doc_id, db, bedrock_client)
                print(f"  ✓ Complete")
            except Exception as e:
                print(f"  ✗ Failed: {e}")
        
        # Mark regeneration complete
        await db.update_series(series_id, regeneration_pending=False)
        print(f"\n✓ Series regeneration complete!")
        
    finally:
        await db.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ./scripts/regenerate-series <series-id>")
        sys.exit(1)
    
    series_id = UUID(sys.argv[1])
    asyncio.run(regenerate_series(series_id))
```

```bash
chmod +x scripts/regenerate-series
```

**Test:**
```bash
# Get a series ID
psql -U alfrd_user -d alfrd -c "SELECT id, title FROM series LIMIT 1;"

# Regenerate it
./scripts/regenerate-series <series-id>
```

✅ **Checkpoint:** Can manually regenerate series on demand

---

## Testing Checklist

### End-to-End Test

```bash
# 1. Add a test document
./scripts/add-document samples/pg&e-bill.jpg --tags test

# 2. Process it
./scripts/start-processor --once

# 3. Check both extractions exist
psql -U alfrd_user -d alfrd -c "
  SELECT 
    filename,
    document_type,
    extraction_method,
    structured_data IS NOT NULL as has_generic,
    structured_data_series IS NOT NULL as has_series
  FROM documents
  WHERE filename LIKE '%pge%'
  ORDER BY created_at DESC
  LIMIT 1;
"

# Expected output:
#  filename | document_type | extraction_method | has_generic | has_series
# ----------|---------------|-------------------|-------------|------------
#  pg&e-... | utility_bill  | both              | t           | t

# 4. View via API
curl -s http://localhost:8000/api/v1/documents/<doc-id> | jq '.structured_data'
# Should show series extraction (consistent schema)

# 5. Add second PG&E bill
./scripts/add-document samples/pge_2024_02.jpg --tags test

# 6. Process it
./scripts/start-processor --once

# 7. Verify schema consistency
psql -U alfrd_user -d alfrd -c "
  SELECT 
    filename,
    jsonb_object_keys(structured_data_series) as fields
  FROM documents
  WHERE document_type = 'utility_bill'
    AND structured_data_series IS NOT NULL
  ORDER BY created_at DESC
  LIMIT 10;
"

# All PG&E bills should have IDENTICAL field names! ✅
```

---

## Rollback Plan

If issues arise:

1. **Disable new steps:**
   ```python
   # In orchestrator.py, comment out:
   # await series_summarize_step(...)
   ```

2. **Revert schema (if needed):**
   ```sql
   ALTER TABLE documents DROP COLUMN structured_data_series;
   ALTER TABLE documents DROP COLUMN series_prompt_id;
   ALTER TABLE documents DROP COLUMN extraction_method;
   ALTER TABLE series DROP COLUMN active_prompt_id;
   ALTER TABLE series DROP COLUMN regeneration_pending;
   ```

3. **System continues working with generic extraction only**

---

## Success Criteria

✅ **Phase 1:** Schema changes applied, no errors  
✅ **Phase 2:** Can create series prompts with schemas  
✅ **Phase 3:** Series summarize step completes successfully  
✅ **Phase 4:** Pipeline includes new step, processes documents  
✅ **Phase 5:** API returns series data, UI displays correctly  
✅ **Phase 6:** Prompts evolve based on quality scores  
✅ **Phase 7:** Can manually regenerate series  

**Final validation:**
- All PG&E bills have identical field names ✓
- Data tables display clean, consistent columns ✓
- Prompt evolution happens automatically ✓
- Can trigger manual regeneration ✓

---

## Next Steps After Implementation

1. **Monitor in production** (1 week)
2. **Tune thresholds** (improvement > 0.1, min 3 docs)
3. **Add automatic regeneration** (background worker)
4. **Build series schema viewer in UI**
5. **Add cost tracking for regenerations**
