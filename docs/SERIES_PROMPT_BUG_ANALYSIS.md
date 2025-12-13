# Series Prompt Bug Analysis & Fixes

**Date:** 2025-12-11  
**System:** ALFRD Series Schema Stability Implementation  
**Status:** Critical bugs identified, fixes planned

---

## Problem Summary

The series-specific prompt system was implemented but has **3 critical bugs** that prevent it from working correctly. Instead of maintaining schema consistency across series documents, the system creates a **new prompt for every document**, resulting in 35 prompts for a 12-document series.

---

## Evidence from Production

### Test Case: Bay Area Properties LLC Rent Receipts
- **Series ID:** `37cda28b-dbd0-4da9-8900-67eedd962597`
- **Expected:** 12 documents using 1 shared series prompt
- **Actual:** 12 documents using 12 different prompts (35 total prompts created)

### Database State

```sql
-- Series configuration
Series: "Bay Area Properties LLC - Monthly Rent Receipt"
- active_prompt_id: f76afb46-f6a9-48a9-ba35-ddc2d9f65e48 (v2, score 0.85)
- regeneration_pending: TRUE
- document_count: 12

-- Document prompt assignments (first 5 documents)
ff4bece3: series_prompt_id = 72ffca76... (v1) ❌ WRONG
166ecef2: series_prompt_id = 969beab3... (v1) ❌ WRONG  
54709f8c: series_prompt_id = f4742b86... (v1) ❌ WRONG
feb07729: series_prompt_id = 858c2490... (v1) ❌ WRONG
c7d37603: series_prompt_id = 487d818f... (v1) ❌ WRONG

Expected: ALL should use f76afb46 (series.active_prompt_id)

-- Prompt proliferation
35 series prompts created for this ONE series:
- 20 version 1 prompts (one per document as they were processed)
- 15 version 2 prompts (created during scoring/evolution)
```

### Impact

All 12 documents have **different schemas** with inconsistent field names:
- `receipt_no` vs `receipt_number`
- `landlord_name` (string) vs `landlord_contact_info` (object)
- Different required/optional field lists
- Different data structures for same information

This completely defeats the purpose of series-specific prompts.

---

## Root Causes

### Bug #1: Prompt Creation Logic ❌

**Location:** [`document-processor/src/document_processor/tasks/document_tasks.py:896`](../document-processor/src/document_processor/tasks/document_tasks.py#L896)

**Current Code:**
```python
# Get series from document_series junction table
series_data = await db.get_document_series(doc_id)
series_id = series_data['id']
series = await db.get_series(series_id)

# Check if series has active prompt
series_prompt = None
if series.get('active_prompt_id'):
    series_prompt = await db.get_prompt(series['active_prompt_id'])

# If no series prompt, create one
if not series_prompt:
    logger.info(f"Creating first series prompt for series {series_id}")
    # ... creates new prompt ...
```

**Problem:**
1. The check `if not series_prompt:` happens AFTER querying
2. But when multiple documents process concurrently, they all see `active_prompt_id = NULL`
3. Each document creates its own prompt
4. Each prompt gets stored with a different UUID
5. No deduplication or reuse logic

**Why This Happens:**
- Document processing is async and concurrent
- Multiple documents hit line 896 simultaneously
- All see `active_prompt_id = NULL` because prompt creation happens later
- Race condition: whoever finishes first sets `active_prompt_id`, but others already started creating their own

### Bug #2: No Regeneration Trigger ❌

**Location:** [`document-processor/src/document_processor/tasks/document_tasks.py:1082-1087`](../document-processor/src/document_processor/tasks/document_tasks.py#L1082-L1087)

**Current Code:**
```python
# Mark series for regeneration
await db.update_series(
    series_id,
    active_prompt_id=new_prompt_id,
    regeneration_pending=True
)

logger.info(
    f"Updated series {series_id} prompt: "
    f"v{series_prompt['version']+1}, score={score_result['score']:.2f}, "
    f"regeneration_pending=True"
)

# TODO: Trigger regeneration (Phase 7)
```

**Problem:**
- Sets `regeneration_pending = TRUE` in database
- Logs intention to regenerate
- **BUT NEVER ACTUALLY REGENERATES**
- No worker, no trigger, no orchestrator step checks this flag
- Documents stay with old prompt IDs forever

**Why This Happens:**
- Code comment says "Phase 7" but it was never implemented
- [`orchestrator.py`](../document-processor/src/document_processor/orchestrator.py) doesn't check for `regeneration_pending` series
- No periodic worker to process regeneration queue

### Bug #3: Prompt Deactivation Missing ❌

**Location:** [`document-processor/src/document_processor/tasks/document_tasks.py:1072-1080`](../document-processor/src/document_processor/tasks/document_tasks.py#L1072-L1080)

**Current Code:**
```python
# Create new version of series prompt
new_prompt_id = uuid4()
await db.create_series_prompt(
    prompt_id=new_prompt_id,
    series_id=series_id,
    prompt_text=new_prompt_text,
    version=series_prompt['version'] + 1,
    performance_score=score_result['score'],
    performance_metrics=series_prompt.get('performance_metrics', {})
)

# Mark series for regeneration
await db.update_series(
    series_id,
    active_prompt_id=new_prompt_id,
    regeneration_pending=True
)
```

**Problem:**
- Creates new prompt version with `is_active = TRUE` (default)
- Updates series to point to new prompt
- **But doesn't deactivate old prompts**
- Result: 35 active prompts for same series

**Why This Happens:**
- Missing call to `db.deactivate_old_prompts()` or equivalent
- For generic prompts, this step exists (line 612 in summarize step)
- But series prompts never clean up old versions

---

## Schema Analysis

### Database Schema (Correct)

```sql
-- Series table
active_prompt_id UUID REFERENCES prompts(id)  -- ✅ Correct
regeneration_pending BOOLEAN DEFAULT FALSE     -- ✅ Correct

-- Documents table  
structured_data JSONB                          -- ✅ Series extraction
structured_data_generic JSONB                  -- ✅ Generic extraction
series_prompt_id UUID REFERENCES prompts(id)  -- ✅ Correct
extraction_method VARCHAR                      -- ✅ Correct
```

### Code Implementation (Correct for writes, wrong for logic)

```python
# Generic extraction (line 404)
await db.update_document(
    doc_id,
    summary=summary_result.get('summary', ''),
    structured_data_generic=json.dumps(summary_result),  # ✅ Writes to generic field
    status=DocumentStatus.SUMMARIZED
)

# Series extraction (line 967)
await db.update_document(
    doc_id,
    structured_data=json.dumps(series_extraction),      # ✅ Writes to series field
    series_prompt_id=series_prompt['id'],               # ✅ Links to prompt
    extraction_method='series',                         # ✅ Marks method
    status='series_summarized'
)
```

**Status:** Field naming is correct, but prompt reuse logic is broken.

---

## Fixes Required

### Fix #1: Add Prompt Reuse Check

**File:** [`document-processor/src/document_processor/tasks/document_tasks.py`](../document-processor/src/document_processor/tasks/document_tasks.py#L890)

**Before (line 890-946):**
```python
# Check if series has active prompt
series_prompt = None
if series.get('active_prompt_id'):
    series_prompt = await db.get_prompt(series['active_prompt_id'])

# If no series prompt, create one
if not series_prompt:
    logger.info(f"Creating first series prompt for series {series_id}")
    # ... creates new prompt ...
```

**After:**
```python
# ALWAYS check series.active_prompt_id FIRST
series_prompt = None
if series.get('active_prompt_id'):
    series_prompt = await db.get_prompt(series['active_prompt_id'])
    if series_prompt:
        logger.info(f"Reusing existing series prompt {series_prompt['id']} (v{series_prompt['version']})")

# Only create if series has NO active prompt
if not series_prompt:
    # Use database lock to prevent race conditions
    async with document_type_lock(db, f"series_{series_id}"):
        # Double-check after acquiring lock
        series = await db.get_series(series_id)
        if series.get('active_prompt_id'):
            series_prompt = await db.get_prompt(series['active_prompt_id'])
            if series_prompt:
                logger.info(f"Another worker created prompt, reusing {series_prompt['id']}")
        
        if not series_prompt:
            logger.info(f"Creating FIRST series prompt for series {series_id}")
            # ... create new prompt ...
```

### Fix #2: Implement Regeneration Worker

**File:** New file [`document-processor/src/document_processor/tasks/series_regeneration.py`](../document-processor/src/document_processor/tasks/series_regeneration.py)

```python
async def regenerate_series_documents(
    series_id: UUID,
    db: AlfrdDatabase,
    bedrock_client: BedrockClient
) -> int:
    """Regenerate all documents in series with latest prompt.
    
    Returns:
        Number of documents regenerated
    """
    series = await db.get_series(series_id)
    if not series.get('active_prompt_id'):
        logger.warning(f"Series {series_id} has no active prompt, skipping regeneration")
        return 0
    
    series_prompt = await db.get_prompt(series['active_prompt_id'])
    documents = await db.get_series_documents(series_id)
    
    logger.info(f"Regenerating {len(documents)} documents in series {series_id} with prompt v{series_prompt['version']}")
    
    regenerated = 0
    for doc_id_dict in documents:
        doc_id = doc_id_dict['id']
        
        # Skip if already using latest prompt
        doc = await db.get_document(doc_id)
        if doc.get('series_prompt_id') == series_prompt['id']:
            logger.debug(f"Document {doc_id} already using latest prompt, skipping")
            continue
        
        try:
            # Re-extract with latest series prompt
            await series_summarize_step(doc_id, db, bedrock_client)
            regenerated += 1
            logger.info(f"Regenerated document {doc_id} ({regenerated}/{len(documents)})")
        except Exception as e:
            logger.error(f"Failed to regenerate {doc_id}: {e}")
    
    # Mark regeneration complete
    await db.update_series(series_id, regeneration_pending=False)
    logger.info(f"Series {series_id} regeneration complete: {regenerated} documents updated")
    
    return regenerated
```

**Add to orchestrator:** [`document-processor/src/document_processor/orchestrator.py`](../document-processor/src/document_processor/orchestrator.py#L82)

```python
async def _process_documents(self):
    # ... existing code ...
    
    # NEW: Check for series needing regeneration
    await self._process_series_regenerations()

async def _process_series_regenerations(self):
    """Process series marked for regeneration."""
    from document_processor.tasks.series_regeneration import regenerate_series_documents
    
    # Find series with regeneration_pending = TRUE
    series_list = await self.db.list_series(limit=10)
    pending_series = [s for s in series_list if s.get('regeneration_pending')]
    
    if not pending_series:
        return
    
    logger.info(f"Found {len(pending_series)} series needing regeneration")
    
    for series in pending_series:
        try:
            regenerated = await regenerate_series_documents(
                series['id'], 
                self.db, 
                self.bedrock
            )
            logger.info(f"✅ Regenerated {regenerated} documents in series {series['title']}")
        except Exception as e:
            logger.error(f"❌ Failed to regenerate series {series['id']}: {e}")
```

### Fix #3: Deactivate Old Prompts

**File:** [`document-processor/src/document_processor/tasks/document_tasks.py`](../document-processor/src/document_processor/tasks/document_tasks.py#L1072)

**Before:**
```python
# Create new version of series prompt
new_prompt_id = uuid4()
await db.create_series_prompt(
    prompt_id=new_prompt_id,
    series_id=series_id,
    prompt_text=new_prompt_text,
    version=series_prompt['version'] + 1,
    performance_score=score_result['score'],
    performance_metrics=series_prompt.get('performance_metrics', {})
)
```

**After:**
```python
# Deactivate ALL old prompts for this series
await db.execute("""
    UPDATE prompts 
    SET is_active = FALSE 
    WHERE prompt_type = 'series_summarizer' 
      AND document_type = $1
      AND is_active = TRUE
""", str(series_id))

# Create new version of series prompt
new_prompt_id = uuid4()
await db.create_series_prompt(
    prompt_id=new_prompt_id,
    series_id=series_id,
    prompt_text=new_prompt_text,
    version=series_prompt['version'] + 1,
    performance_score=score_result['score'],
    performance_metrics=series_prompt.get('performance_metrics', {})
)

logger.info(f"Deactivated old prompts and created new prompt {new_prompt_id} v{series_prompt['version'] + 1}")
```

---

## Testing Plan

### 1. Clean Slate Test
```bash
# Drop existing series prompts
psql ... -c "DELETE FROM prompts WHERE prompt_type = 'series_summarizer' AND document_type = '37cda28b-dbd0-4da9-8900-67eedd962597'"

# Reset documents
psql ... -c "UPDATE documents SET series_prompt_id = NULL, extraction_method = 'generic' WHERE id IN (SELECT document_id FROM document_series WHERE series_id = '37cda28b-dbd0-4da9-8900-67eedd962597')"

# Reset series
psql ... -c "UPDATE series SET active_prompt_id = NULL, regeneration_pending = FALSE WHERE id = '37cda28b-dbd0-4da9-8900-67eedd962597'"

# Reprocess one document
./scripts/add-document test-dataset-generator/output/property/rent_2024_01.jpg

# Expected:
# - ONE series prompt created
# - Document uses that prompt
```

### 2. Prompt Reuse Test
```bash
# Process second document
./scripts/add-document test-dataset-generator/output/property/rent_2024_02.jpg

# Expected:
# - NO new prompt created
# - Document reuses existing series prompt
# - Both documents have SAME series_prompt_id
```

### 3. Regeneration Test
```bash
# Manually trigger prompt evolution
psql ... -c "UPDATE series SET regeneration_pending = TRUE WHERE id = '37cda28b-dbd0-4da9-8900-67eedd962597'"

# Run orchestrator once
./scripts/start-processor --once

# Expected:
# - Regeneration worker runs
# - All 12 documents updated with latest prompt
# - regeneration_pending = FALSE
# - All documents have SAME series_prompt_id
```

### 4. Schema Consistency Validation
```bash
# Query field names across all documents
psql ... -c "
SELECT 
    d.id,
    d.filename,
    jsonb_object_keys(d.structured_data) as field_name
FROM documents d
INNER JOIN document_series ds ON d.id = ds.document_id
WHERE ds.series_id = '37cda28b-dbd0-4da9-8900-67eedd962597'
ORDER BY d.filename, field_name
"

# Expected:
# - ALL documents have IDENTICAL field names
# - receipt_number (not receipt_no)
# - landlord_name (consistent structure)
# - base_rent, total_amount_paid (consistent types)
```

---

## Success Criteria

✅ **Prompt Creation:** Only 1 series prompt exists per series  
✅ **Prompt Reuse:** All documents in series use same `series_prompt_id`  
✅ **Regeneration:** When prompt evolves, all documents updated automatically  
✅ **Schema Consistency:** All documents have identical field names and structure  
✅ **Deactivation:** Old prompt versions marked `is_active = FALSE`  

---

## Next Steps

1. ✅ Document findings (this file)
2. Implement Fix #1 (prompt reuse with locking)
3. Implement Fix #2 (regeneration worker)
4. Implement Fix #3 (deactivate old prompts)
5. Run clean slate test
6. Run prompt reuse test
7. Run regeneration test
8. Validate schema consistency
9. Deploy fixes to production