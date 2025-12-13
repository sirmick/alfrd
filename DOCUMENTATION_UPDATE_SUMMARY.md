# Series-Specific Prompt Evolution - Documentation Update Summary

**Date:** 2025-12-10  
**Feature:** Series-Specific Prompt Evolution for Schema Consistency

---

## Executive Summary

Implemented a **series-specific prompt evolution system** to solve the **schema drift problem** in ALFRD. Previously, documents in the same series (e.g., 12 monthly PG&E bills) had inconsistent field names because the generic summarization prompts evolved over time. Now, each series gets its own specialized prompt that ensures ALL documents in that series have identical schemas.

### Key Benefit
**Schema consistency within series** - All PG&E bills will have identical field names (e.g., `usage_kwh`, `total_amount`), enabling clean data tables and aggregation, while still allowing prompt evolution across the entire series.

---

## Implementation Status

### ✅ Completed
1. **Database Schema** - Updated with series prompt support
2. **MCP Tools** - Created `summarize_series.py` with auto-generation and extraction
3. **Document Pipeline** - Added series summarization step
4. **Database Helpers** - Added series prompt management functions
5. **Type Definitions** - New statuses for series workflow
6. **Orchestrator Integration** - Series step integrated into pipeline
7. **Scoring & Evolution** - Automatic prompt improvement and regeneration marking

### ⏳ Pending
1. **Database Recreation** - Run `./scripts/create-alfrd-db` with new schema
2. **Regeneration Script** - Create script to regenerate series when prompts improve
3. **End-to-End Testing** - Test with multiple documents in same series

---

## Architecture Changes

### Database Schema Updates

**File:** `api-server/src/api_server/db/schema.sql`

#### Documents Table - Updated Fields

```sql
-- OLD:
structured_data JSONB,  -- Generic extraction only

-- NEW:
structured_data JSONB,          -- Series-specific extraction (PRIMARY)
structured_data_generic JSONB,  -- Generic extraction (FALLBACK)
```

**Rationale:** The rest of the stack automatically gets the better series-specific data from `structured_data` without requiring changes to existing code.

#### Documents Table - New Status Values

```sql
status VARCHAR NOT NULL CHECK (status IN (
    'pending',
    'ocr_completed',
    'classified',
    'scored_classification',
    'summarized',
    'scored_summary',
    'series_summarizing',     -- NEW: Series extraction in progress
    'series_summarized',       -- NEW: Series extraction complete
    'series_scoring',          -- NEW: Series scoring in progress
    'filed',
    'completed',
    'failed'
))
```

#### Series Table - New Columns

```sql
CREATE TABLE series (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    entity_name VARCHAR NOT NULL,
    series_type VARCHAR NOT NULL,
    frequency VARCHAR,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- NEW: Series prompt evolution support
    active_prompt_id UUID REFERENCES prompts(id),
    last_schema_update TIMESTAMP,
    regeneration_pending BOOLEAN DEFAULT FALSE,
    
    UNIQUE(entity_name, series_type)
);

-- NEW: Index for finding series needing regeneration
CREATE INDEX idx_series_regeneration ON series(regeneration_pending) 
WHERE regeneration_pending = TRUE;
```

#### Prompts Table - New Type

```sql
-- Existing types: 'classifier', 'summarizer', 'file_summarizer', 'series_detector'
-- NEW type:
prompt_type = 'series_summarizer'  -- One prompt per series
```

**Key Fields:**
- `prompt_type`: Always `'series_summarizer'`
- `document_type`: Series identifier (e.g., `'series:pge_monthly_utility'`)
- `prompt_text`: Auto-generated from generic template with schema enforcement
- `version`: Increments as prompt evolves
- `is_active`: Only one active prompt per series

#### Recovery Support

```sql
-- NEW: Index for stale work detection
CREATE INDEX idx_documents_series_summarizing_recovery 
ON documents(updated_at) 
WHERE status = 'series_summarizing';
```

---

## Pipeline Flow

### Updated Processing Pipeline

```
User uploads folder → pending
         ↓
    OCR Step (AWS Textract) → ocr_completed
         ↓
    Classify Step (Bedrock) → classified
         ↓
    Background: Score Classification → scored_classification
         ↓
    Summarize Step (Generic) → summarized
         ↓                         │
         │                         ├─> structured_data_generic
         │
    Background: Score Summary → scored_summary
         ↓
    NEW: Series Summarize Step → series_summarizing → series_summarized
         ↓                                                │
         │                                                ├─> structured_data
         │
    Background: Score Series Extraction → series_scoring
         ↓
    File Step (Series detection & tagging) → filed
         ↓
    Complete Task → completed
```

### Series Summarization Logic

**First Document in Series:**
1. Check if series has active prompt → NO
2. Call `create_series_prompt_from_generic()`
   - Uses generic extraction as example
   - Infers schema from actual data
   - Creates specialized prompt with strict output requirements
3. Save new prompt with `prompt_type='series_summarizer'`
4. Link prompt to series: `active_prompt_id`
5. Extract using new prompt → `structured_data`

**Subsequent Documents in Series:**
1. Check if series has active prompt → YES
2. Get active prompt from database
3. Extract using series prompt with schema enforcement → `structured_data`
4. **Result: Identical field names across all documents in series**

### Prompt Evolution Flow

**Scoring Step:**
1. LLM evaluates series extraction quality
2. Suggests improvements if needed
3. If improvement score ≥ 0.05:
   - Create new prompt version
   - Mark as active
   - Set `series.regeneration_pending = TRUE`
   - Archive old version (`is_active = FALSE`)

**Regeneration (Manual for now):**
```bash
# Future script: ./scripts/regenerate-series
# 1. Find all series with regeneration_pending=TRUE
# 2. For each series:
#    - Get all documents in series
#    - Re-run series_summarize_step with new prompt
#    - Update structured_data with new schema
# 3. Set regeneration_pending=FALSE
```

---

## Code Changes

### New MCP Tool: `summarize_series.py`

**File:** `mcp-server/src/mcp_server/tools/summarize_series.py`

**Functions:**

#### 1. `create_series_prompt_from_generic()`

Auto-generates a series-specific prompt from a generic extraction.

```python
async def create_series_prompt_from_generic(
    document_id: str,
    series_id: str,
    generic_extraction: Dict[str, Any],
    extracted_text: str,
    document_type: str
) -> Dict[str, Any]:
    """
    Auto-generate a series-specific prompt from generic extraction.
    
    Returns:
        {
            "prompt_text": str,  # The specialized prompt
            "output_schema": dict,  # Inferred schema
            "prompt_type": "series_summarizer",
            "document_type": "series:{series_id}"
        }
    """
```

**LLM Prompt:**
- Takes generic extraction as reference
- Identifies key fields and their types
- Creates strict schema requirements
- Emphasizes consistent naming across series

#### 2. `summarize_with_series_prompt()`

Extracts structured data using series-specific prompt.

```python
async def summarize_with_series_prompt(
    document_id: str,
    series_id: str,
    series_prompt: str,
    extracted_text: str,
    output_schema: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Extract structured data using series-specific prompt.
    
    The prompt includes the output schema to ensure consistent field names.
    """
```

### Updated: `document_tasks.py`

**File:** `document-processor/src/document_processor/tasks/document_tasks.py`

#### New Task: `series_summarize_step()`

```python
async def series_summarize_step(document_id: str):
    """
    Series-specific summarization step.
    
    Workflow:
    1. Get document's series
    2. Check if series has active prompt
    3. If NO prompt:
       - Auto-generate from generic extraction
       - Save to prompts table
       - Link to series
    4. If HAS prompt:
       - Get active prompt
    5. Extract using series prompt
    6. Save to structured_data (PRIMARY field)
    7. Update status to 'series_summarized'
    """
```

**Key Changes:**
- Line 400-406: Generic summarization saves to `structured_data_generic`
- Line 964-971: Series summarization saves to `structured_data`

#### Updated Task: `score_series_extraction_step()`

```python
async def score_series_extraction_step(document_id: str):
    """
    Score series extraction quality and evolve prompt if needed.
    
    Workflow:
    1. Get document and series info
    2. Score extraction quality
    3. If score improves by ≥0.05:
       - Create new prompt version
       - Mark series for regeneration
    4. Background task (fire-and-forget)
    """
```

**Key Change:**
- Line 1035-1047: Now reads from `structured_data` (not `structured_data_series`)

### Updated: `shared/database.py`

**New Functions:**

```python
async def get_document_series(document_id: str) -> Optional[Dict]:
    """Get the series for a document."""

async def get_series_prompt(series_id: str) -> Optional[Dict]:
    """Get the active series prompt."""

async def create_series_prompt(prompt_data: Dict) -> str:
    """Create a new series-specific prompt."""
```

**Updated Function:**

```python
async def recover_stale_work():
    """
    Find and reset stuck work.
    
    NEW: Includes 'series_summarizing' status
    """
```

### Updated: `shared/types.py`

**New Status Constants:**

```python
class DocumentStatus:
    # ... existing statuses ...
    SERIES_SUMMARIZING = "series_summarizing"
    SERIES_SUMMARIZED = "series_summarized"
    SERIES_SCORING = "series_scoring"
```

### Updated: `orchestrator.py`

**File:** `document-processor/src/document_processor/orchestrator.py`

**Integration:**

```python
# After summarize step completes:
if status == 'scored_summary':
    # NEW: Series summarization
    asyncio.create_task(series_summarize_step(doc_id))
    
    # After series summarization completes:
    if status == 'series_summarized':
        # Background scoring (fire-and-forget)
        asyncio.create_task(score_series_extraction_step(doc_id))
```

---

## Data Flow Example

### Example: Processing 12 PG&E Bills

#### Document 1 (January Bill)

```
1. OCR → extracted_text
2. Classify → document_type: "utility_bill"
3. Generic Summarize → structured_data_generic: {
     "vendor": "PG&E",
     "amount": 125.43,
     "usage": 450,  # ← Field name from generic prompt
     "period": "2024-01"
   }
4. Series Summarize:
   - Series "PG&E Monthly Bills" has NO prompt yet
   - Auto-generate prompt from generic extraction
   - NEW PROMPT enforces: {
       "vendor": string,
       "total_amount": number,
       "usage_kwh": number,  # ← CONSISTENT name
       "billing_period": string
     }
   - Extract with new prompt → structured_data: {
       "vendor": "PG&E",
       "total_amount": 125.43,
       "usage_kwh": 450,  # ← Now uses series schema
       "billing_period": "2024-01"
     }
```

#### Document 2-12 (February-December Bills)

```
1-3. Same as Document 1
4. Series Summarize:
   - Series "PG&E Monthly Bills" HAS active prompt
   - Extract using SAME prompt → structured_data: {
       "vendor": "PG&E",
       "total_amount": 132.18,
       "usage_kwh": 475,  # ← IDENTICAL field names!
       "billing_period": "2024-02"
     }
```

#### Result: Clean Data Table

| Document | vendor | total_amount | usage_kwh | billing_period |
|----------|--------|--------------|-----------|----------------|
| Jan Bill | PG&E   | 125.43       | 450       | 2024-01        |
| Feb Bill | PG&E   | 132.18       | 475       | 2024-02        |
| Mar Bill | PG&E   | 118.92       | 420       | 2024-03        |
| ...      | ...    | ...          | ...       | ...            |

**No schema drift!** All documents have identical field names.

---

## Documentation Updates Needed

### 1. README.md

**Section to Add:** Under "Key Features"

```markdown
### ✅ Series-Specific Prompt Evolution

- **Schema Consistency** - Documents in the same series use identical field names
- **Auto-Generation** - First document creates series prompt from generic template
- **Schema Enforcement** - All subsequent documents use the same schema
- **Automatic Evolution** - Prompts improve based on scoring, marking series for regeneration
- **Dual Storage** - `structured_data` (series) + `structured_data_generic` (fallback)
```

**Section to Update:** "Processing Pipeline"

Add after "Summarize Step":

```markdown
Series Summarize Step → Series-specific structured data extraction (SERIES_SUMMARIZED)
                     ↓
                Background: Score Series Extraction (for prompt evolution)
```

### 2. ARCHITECTURE.md

**Section to Add:** "Series Prompt Evolution System"

```markdown
## Series Prompt Evolution System

### Problem Solved
Generic prompts evolve over time, causing schema drift. Documents in the same series 
(e.g., 12 monthly bills) end up with different field names, breaking data tables.

### Solution
Each series gets its own prompt:
1. **First document**: Auto-generates series prompt from generic extraction
2. **Subsequent documents**: Use the SAME prompt → identical schemas
3. **Prompt improvement**: When scoring detects improvements, mark series for regeneration
4. **Hard schema cut**: Regenerate all documents in series with new schema

### Database Fields
- `structured_data` - Series-specific extraction (PRIMARY - used by rest of stack)
- `structured_data_generic` - Generic extraction (FALLBACK - kept for comparison)

### Benefits
- ✅ Clean data tables with consistent columns
- ✅ Easy aggregation and analysis
- ✅ Still allows prompt evolution (via regeneration)
- ✅ Backward compatible (generic extraction preserved)
```

### 3. START_HERE.md

**Section to Update:** "Processing Pipeline"

```markdown
**Pipeline stages:**
1. **OCR Step** - AWS Textract OCR extraction
2. **Classify Step** - Document type classification
3. **Background: Score Classification** - Evaluate classifier performance
4. **Summarize Step** - Generic type-specific summary → `structured_data_generic`
5. **Background: Score Summary** - Evaluate summarizer performance
6. **Series Summarize Step** - Series-specific extraction → `structured_data`
7. **Background: Score Series** - Evaluate series extraction, evolve prompt
8. **File Step** - Series detection and filing
9. **Complete** - Final status update
```

### 4. STATUS.md

**Section to Update:** "What's Working"

Add under "Phase 1C: Self-Improving Pipeline":

```markdown
11. **Series-Specific Prompt Evolution**
    - Auto-generation of series prompts from first document
    - Schema consistency across all documents in a series
    - Dual storage: series extraction (primary) + generic extraction (fallback)
    - Automatic prompt evolution with regeneration marking
    - Eliminates schema drift within series
    - Enables clean data tables and aggregation
```

**Section to Update:** "Known Issues & Notes"

Add:

```markdown
8. **Series Regeneration** - Manual script needed for regenerating series when prompts improve
```

**Section to Update:** "Next Steps"

Add to "Immediate (Week 1-2)":

```markdown
6. Create series regeneration script for prompt evolution
7. Test series feature with 12 monthly bills
```

### 5. New Documentation File

**File:** `docs/SERIES_PROMPTS.md`

```markdown
# Series-Specific Prompt Evolution

## Overview
Each document series (e.g., monthly PG&E bills) gets its own specialized prompt 
to ensure schema consistency across all documents in that series.

## Why This Matters
Without series prompts, schema drift occurs as generic prompts evolve over time,
resulting in inconsistent field names that break data tables and aggregation.

## How It Works
[Include detailed technical explanation from this document]

## Usage Examples
[Include code examples]

## Regeneration Workflow
[Include regeneration script design]

## API Reference
[Document the new database functions]
```

---

## Testing Plan

### Unit Tests Needed

1. **Test Series Prompt Creation**
   ```bash
   pytest -k test_create_series_prompt
   ```

2. **Test Series Schema Consistency**
   ```bash
   pytest -k test_series_schema_consistency
   ```

3. **Test Prompt Evolution**
   ```bash
   pytest -k test_series_prompt_evolution
   ```

### Integration Tests Needed

1. **Test Full Pipeline with Series**
   - Upload 3 documents to same series
   - Verify first creates prompt
   - Verify subsequent use same prompt
   - Verify identical field names

2. **Test Regeneration**
   - Create series with documents
   - Improve prompt
   - Run regeneration
   - Verify all documents updated

### Manual Testing Workflow

```bash
# 1. Recreate database with new schema
./scripts/create-alfrd-db

# 2. Add 12 PG&E bills (use test dataset generator)
cd test-dataset-generator
python generator.py
cd ../esec

for file in ../test-dataset-generator/output/bills/pge_*.jpg; do
    ./scripts/add-document "$file" --tags bill utilities
done

# 3. Start processor
./scripts/start-processor

# 4. Monitor processing
watch -n 2 './scripts/get-document --stats'

# 5. Verify schema consistency
./scripts/analyze-file-data --series "PG&E Monthly Bills"
# Should see identical column names across all 12 documents

# 6. Check prompt evolution
./scripts/view-prompts --type series_summarizer
```

---

## Migration Guide

### For Existing Databases

**⚠️ Breaking Change:** Requires database recreation

```bash
# 1. Backup existing data (if needed)
pg_dump -U alfrd_user alfrd > backup_$(date +%Y%m%d).sql

# 2. Recreate database with new schema
./scripts/create-alfrd-db

# 3. Verify schema
psql -U alfrd_user -d alfrd -c "\d documents"
# Should see: structured_data and structured_data_generic columns

psql -U alfrd_user -d alfrd -c "\d series"
# Should see: active_prompt_id, last_schema_update, regeneration_pending columns

psql -U alfrd_user -d alfrd -c "\d prompts"
# Should support prompt_type='series_summarizer'

# 4. Reprocess documents
# All existing documents will need to be reprocessed to get series extraction
```

### For New Installations

Just run:
```bash
./scripts/create-alfrd-db
```

The new schema is already included.

---

## Future Enhancements

### Short Term
1. **Regeneration Script** - `./scripts/regenerate-series`
   - Find series with `regeneration_pending=TRUE`
   - Re-extract all documents with new prompt
   - Update `structured_data` fields
   - Clear regeneration flag

2. **Schema Validation** - Validate extraction against expected schema

3. **Series Prompt Viewer** - `./scripts/view-series-prompts`
   - Show all series and their active prompts
   - Display prompt evolution history per series

### Medium Term
1. **Manual Series Prompt Creation** - Allow users to define custom schemas
2. **Schema Migration** - Tools to migrate from old schema to new schema
3. **Prompt Templates** - Pre-built templates for common series types
4. **Multi-Series Documents** - Handle documents that belong to multiple series

### Long Term
1. **Schema Learning** - ML to detect optimal schema from usage patterns
2. **Cross-Series Analysis** - Compare schemas across similar series
3. **Schema Versioning** - Track schema changes over time
4. **Schema Merging** - Combine schemas when series are merged

---

## Questions & Answers

**Q: What happens to existing `structured_data`?**  
A: It moves to `structured_data_generic`. The `structured_data` field now holds series-specific extraction.

**Q: Do I need to update my API queries?**  
A: No! The API still returns `structured_data`, which now contains the better series extraction.

**Q: What if a document isn't in a series?**  
A: It only gets generic extraction in `structured_data_generic`. The `structured_data` field will be null.

**Q: Can I disable series prompts?**  
A: Not currently, but you could skip the series_summarize_step in the orchestrator.

**Q: How do I force regeneration of a series?**  
A: Set `regeneration_pending=TRUE` in the series table, then run the regeneration script (when created).

**Q: What's the performance impact?**  
A: One additional LLM call per document (for series extraction). Same latency as generic summarization.

**Q: Can series prompts be manually edited?**  
A: Yes, update the prompt in the `prompts` table. The next document in the series will use the updated prompt.

---

## Summary

The series-specific prompt evolution feature ensures schema consistency within document series while maintaining the system's self-improving capabilities. This solves the schema drift problem and enables clean data tables and aggregation, which is essential for financial tracking and analysis.

**Next Steps:**
1. Recreate database: `./scripts/create-alfrd-db`
2. Test with 12 monthly bills
3. Create regeneration script
4. Update all documentation files
5. Add to changelog/release notes