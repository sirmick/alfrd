# Auto-File Creation Implementation

**Date:** 2025-12-04  
**Status:** Implementation Complete  
**Feature:** Automatic file creation based on document tags after summarization

---

## Overview

This feature automatically creates LLM-generated files that group documents with identical tag combinations. When a document completes summarization, a new worker (FilingWorker) checks if a file exists for that tag combination and creates one if needed.

---

## Design Decisions

### 1. File Source Types
- **`user`**: Manually created files, not auto-managed by the system
- **`llm`**: Auto-generated files based on document tags

### 2. Tag Signature Format
- Lowercase, sorted alphabetically, colon-separated
- Example: `"bill:pge:utility"`
- Includes document_type (auto-added as a tag by existing trigger)
- No document_type prefix needed (document_type is just another tag)

### 3. Pipeline Integration
- New status: `filed` (between `summarized` and `completed`)
- Linear pipeline flow ensures all data is finalized before filing
- FilingWorker operates after summarization completes

### 4. Existing Trigger Reuse
- `invalidate_files_on_tag_change()` trigger already handles marking files as 'outdated'
- No need for redundant logic in FilingWorker

---

## Updated Pipeline Flow

```
pending
  ↓ OCRWorker
ocr_completed
  ↓ ClassifierWorker
classified
  ↓ ClassifierScorerWorker
scored_classification
  ↓ SummarizerWorker
summarized
  ↓ FilingWorker (NEW - 6th worker)
filed
  ↓ SummarizerScorerWorker (UPDATED: now polls 'filed')
completed
```

---

## Implementation Changes

### 1. Database Schema Changes

**File:** `api-server/src/api_server/db/schema.sql`

#### A. Add `file_source` column to `files` table

```sql
-- Add file_source column to distinguish user vs LLM files
ALTER TABLE files 
ADD COLUMN file_source VARCHAR DEFAULT 'llm' 
    CHECK (file_source IN ('user', 'llm'));

-- Index for efficient queries
CREATE INDEX IF NOT EXISTS idx_files_source ON files(file_source);
```

#### B. Update `documents` status constraint

```sql
-- Add 'filed' status to document pipeline
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_status_check;
ALTER TABLE documents ADD CONSTRAINT documents_status_check
    CHECK (status IN (
        'pending',
        'ocr_started',
        'ocr_completed',
        'classifying',
        'classified',
        'scoring_classification',
        'scored_classification',
        'summarizing',
        'summarized',
        'filed',           -- NEW
        'completed',
        'failed'
    ));
```

---

### 2. New FilingWorker (6th Worker)

**File:** `document-processor/src/document_processor/filing_worker.py` (NEW)

**Purpose:** Auto-create LLM files based on document tags after summarization

**Logic:**

1. Poll for documents with `status='summarized'`
2. For each document:
   - Fetch all tags via `document_tags` + `tags` JOIN
   - Build `tag_signature`: lowercase, sorted, colon-separated
   - Check if LLM file exists with that exact signature
   - If NOT exists → CREATE new file
   - INSERT into `file_documents` junction table
   - Update document status to `'filed'`

**Implementation:** See `filing_worker.py` for complete code

---

### 3. Update SummarizerScorerWorker

**File:** `document-processor/src/document_processor/scorer_workers.py`

**Change:** Poll `'filed'` status instead of `'summarized'`

**Before:**
```python
class SummarizerScorerWorker(BaseWorker):
    def __init__(self, settings: Settings):
        super().__init__(
            name="SummarizerScorer",
            source_status="summarized",
            target_status="completed",
            ...
        )
```

**After:**
```python
class SummarizerScorerWorker(BaseWorker):
    def __init__(self, settings: Settings):
        super().__init__(
            name="SummarizerScorer",
            source_status="filed",  # CHANGED
            target_status="completed",
            ...
        )
```

---

### 4. Update Main Orchestrator

**File:** `document-processor/src/document_processor/main.py`

**Change:** Add FilingWorker to worker pool

**Before (5 workers):**
```python
workers = [
    OCRWorker(settings),
    ClassifierWorker(settings),
    ClassifierScorerWorker(settings),
    SummarizerWorker(settings),
    SummarizerScorerWorker(settings)
]
```

**After (6 workers):**
```python
from document_processor.filing_worker import FilingWorker

workers = [
    OCRWorker(settings),
    ClassifierWorker(settings),
    ClassifierScorerWorker(settings),
    SummarizerWorker(settings),
    FilingWorker(settings),            # NEW
    SummarizerScorerWorker(settings)
]
```

---

## FilingWorker Implementation Details

### Configuration

**File:** `shared/config.py`

```python
# Filing worker settings
filing_workers: int = 3            # Concurrency
filing_poll_interval: int = 2      # Poll every 2 seconds
```

### Database Queries

**Get documents to file:**
```sql
SELECT id, filename 
FROM documents 
WHERE status = 'summarized' 
LIMIT ?
```

**Get document tags:**
```sql
SELECT t.tag_normalized 
FROM document_tags dt
JOIN tags t ON dt.tag_id = t.id
WHERE dt.document_id = ?
ORDER BY t.tag_normalized
```

**Check if file exists:**
```sql
SELECT id 
FROM files 
WHERE tag_signature = ? 
  AND file_source = 'llm' 
  AND user_id = ?
```

**Create file:**
```sql
INSERT INTO files (
    id, tags, tag_signature, file_source, 
    status, user_id, created_at, updated_at
) VALUES (?, ?, ?, 'llm', 'pending', ?, NOW(), NOW())
```

**Associate document with file:**
```sql
INSERT INTO file_documents (file_id, document_id, added_at)
VALUES (?, ?, NOW())
ON CONFLICT DO NOTHING
```

**Update document status:**
```sql
UPDATE documents 
SET status = 'filed', updated_at = NOW() 
WHERE id = ?
```

---

## Error Handling

### FilingWorker Error Cases

1. **No tags found:** Skip filing, log warning, mark as 'filed' anyway
2. **Database error:** Log error, mark document as 'failed', retry on next poll
3. **Duplicate file creation:** ON CONFLICT handled by UNIQUE constraint on `tag_signature`
4. **Missing user_id:** Use NULL or 'system' default

---

## Testing Strategy

### Unit Tests

1. **Tag signature generation:**
   - Test with various tag combinations
   - Verify lowercase + sorting
   - Handle empty tag lists

2. **File creation:**
   - Create file when doesn't exist
   - Skip creation when exists
   - Handle concurrent creation (race conditions)

3. **Document association:**
   - Insert into file_documents
   - Handle duplicates gracefully

### Integration Tests

1. **End-to-end pipeline:**
   - Process document → summarization → filing → completion
   - Verify file created with correct tag_signature
   - Verify document added to file_documents

2. **Multiple documents with same tags:**
   - Process 3 documents with tags `["bill", "pge"]`
   - Verify only ONE file created
   - Verify all 3 documents associated with that file

3. **File invalidation:**
   - Add new document with matching tags
   - Verify existing file marked as 'outdated'

---

## Migration Notes

**No migration needed** - user will delete and recreate database.

For production systems with existing data:
1. Add `file_source` column with default 'llm'
2. Backfill existing files (assume 'llm' unless marked otherwise)
3. Add 'filed' status to enum
4. Deploy FilingWorker

---

## Benefits

✅ **Automatic organization:** Documents grouped by tags without manual effort  
✅ **Consistent structure:** One file per unique tag combination  
✅ **Extensible:** Users can create manual files alongside LLM files  
✅ **Observable:** File creation tracked in database  
✅ **Crash-resistant:** State-machine ensures resume after failure  

---

## Future Enhancements

1. **Hierarchical files:** Parent files that aggregate child files
2. **Tag-based rules:** User-defined filing rules (e.g., "all bills → Finance file")
3. **File summarization worker:** Generate summaries of file contents
4. **File merging:** Combine similar files based on LLM suggestions
5. **File archiving:** Auto-archive files older than X days

---

## References

- Database schema: `api-server/src/api_server/db/schema.sql`
- Worker base class: `document-processor/src/document_processor/workers.py`
- Main orchestrator: `document-processor/src/document_processor/main.py`
- Scorer workers: `document-processor/src/document_processor/scorer_workers.py`

---

**Last Updated:** 2025-12-04