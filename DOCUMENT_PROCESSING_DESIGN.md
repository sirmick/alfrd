# ALFRD Document Processing Architecture

**Status:** ✅ Phase 1C Complete + PostgreSQL Migration (2025-11-30)

---

## Executive Summary

ALFRD uses a **state-machine-driven parallel worker architecture** where:
- Documents flow through 5 processing stages with status transitions
- Each stage handled by specialized workers polling PostgreSQL
- Workers process documents in parallel with configurable concurrency
- All state tracked in database for observability and crash recovery
- MCP tools provide LLM abstraction for classification and summarization

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Document Processing Pipeline                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  User adds folder → Inbox Scanner → INSERT status='pending'      │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │  OCR Worker  │──→│ Classifier   │──→│ ClassifierScorer   │  │
│  │ (Textract)   │   │ (Bedrock)    │   │ (Prompt Evolution) │  │
│  └──────────────┘   └──────────────┘   └────────────────────┘  │
│                                                                   │
│  ┌──────────────┐   ┌──────────────┐                            │
│  │ Summarizer   │──→│SummarizerScorer                          │
│  │(Type-Specific│   │(Prompt Evolution)                         │
│  └──────────────┘   └──────────────┘                            │
│                                                                   │
│                    Database-Driven State Machine                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Status Flow:                                               │ │
│  │ pending → ocr_completed → classified →                     │ │
│  │ scored_classification → summarized → completed             │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles

### 1. Database-Driven State Machine

**All state lives in PostgreSQL, not in-memory:**

```sql
status VARCHAR NOT NULL CHECK (status IN (
    'pending',              -- Document folder detected
    'ocr_completed',        -- Text extracted
    'classified',           -- Type determined
    'scored_classification',-- Classifier scored
    'summarized',           -- Type-specific summary
    'completed',            -- All processing done
    'failed'                -- Error at any stage
))
```

**Benefits:**
- ✅ Workers can crash and resume from PostgreSQL state
- ✅ No in-memory queues that lose data on restart
- ✅ Observable: `SELECT status, COUNT(*) FROM documents GROUP BY status`
- ✅ Horizontal scaling: Run multiple worker instances
- ✅ Connection pooling: asyncpg manages 5-20 connections efficiently

### 2. Parallel Worker Pools

Each processing stage has a dedicated worker pool:

| Worker | Input Status | Output Status | Cloud API | Concurrency |
|--------|-------------|---------------|-----------|-------------|
| **OCRWorker** | `pending` | `ocr_completed` | AWS Textract | 3 workers |
| **ClassifierWorker** | `ocr_completed` | `classified` | AWS Bedrock | 5 workers |
| **ClassifierScorerWorker** | `classified` | `scored_classification` | AWS Bedrock | 2 workers |
| **SummarizerWorker** | `scored_classification` | `summarized` | AWS Bedrock | 5 workers |
| **SummarizerScorerWorker** | `summarized` | `completed` | AWS Bedrock | 2 workers |

**Configuration:** [`shared/config.py`](shared/config.py)
```python
# Worker concurrency (tune per cloud API limits)
ocr_workers: int = 3              # AWS Textract TPS
classifier_workers: int = 5        # Bedrock requests/minute
scorer_workers: int = 2            # Lower for scoring tasks

# Poll intervals
ocr_poll_interval: int = 5         # seconds
classifier_poll_interval: int = 2  # seconds
scorer_poll_interval: int = 10     # seconds
```

### 3. Worker Base Class Pattern

All workers extend [`BaseWorker`](document-processor/src/document_processor/workers.py):

```python
class BaseWorker(ABC):
    """Base class for all document processing workers."""
    
    async def run(self):
        """Main loop: poll DB, process batch, repeat."""
        while self.running:
            docs = await self.get_documents(
                status=self.source_status,
                limit=self.concurrency * batch_multiplier
            )
            
            tasks = [self.process_document(doc) for doc in docs[:concurrency]]
            await asyncio.gather(*tasks)
            
            await asyncio.sleep(self.poll_interval)
```

**Key Features:**
- Configurable concurrency per worker type
- Automatic batch sizing
- Graceful shutdown
- Error handling with status updates

---

## Worker Implementations

### OCRWorker ✅

**Purpose:** Extract text from images/PDFs using AWS Textract

**Flow:**
1. Poll DB for `status='pending'` documents
2. Read `meta.json` from document folder
3. Process each file (image → Textract, text → direct)
4. Combine into LLM-optimized format (full text + blocks)
5. Save to filesystem and update DB
6. Set `status='ocr_completed'`

**Output:**
- `{doc_id}.txt` - Full extracted text
- `{doc_id}_llm.json` - LLM-optimized format with blocks
- DB field: `extracted_text` (for classification)

See: [`document-processor/src/document_processor/ocr_worker.py`](document-processor/src/document_processor/ocr_worker.py)

### ClassifierWorker ✅

**Purpose:** Classify documents using DB-stored prompts + AWS Bedrock

**Flow:**
1. Poll DB for `status='ocr_completed'` documents
2. Fetch active classifier prompt from `prompts` table
3. Call MCP tool: `classify_dynamic(text, filename, prompt)`
4. Accept LLM suggestions for NEW document types
5. Update DB with `document_type`, `confidence`, `reasoning`
6. Record suggestions in `classification_suggestions` table
7. Set `status='classified'`

**MCP Integration:**
```python
from mcp_server.tools.classify_dynamic import classify_dynamic
result = classify_dynamic(extracted_text, filename, prompt_text, bedrock)
```

**Why MCP?** Abstraction layer for LLM provider, reusable tools, testable

See: [`document-processor/src/document_processor/classifier_worker.py`](document-processor/src/document_processor/classifier_worker.py)

### ClassifierScorerWorker ✅

**Purpose:** Evaluate classification performance and evolve prompt

**Flow:**
1. Poll DB for `status='classified'` documents
2. Wait for min 5 documents since last score
3. Call MCP tool: `score_classification(doc, prompt_version)`
4. Analyze accuracy, confidence, reasoning quality
5. If score > current + 0.05 → create new prompt version
6. Mark prompt as active, archive old version
7. Set `status='scored_classification'`

**Prompt Evolution:**
- Max 300 words for classifier prompt
- Tracks performance score (0-1)
- Creates new version only if significant improvement

See: [`document-processor/src/document_processor/scorer_workers.py`](document-processor/src/document_processor/scorer_workers.py)

### SummarizerWorker ✅

**Purpose:** Generate type-specific summaries using DB prompts

**Flow:**
1. Poll DB for `status='scored_classification'` documents
2. Fetch active summarizer prompt for document type
3. Call MCP tool: `summarize_dynamic(text, type, prompt)`
4. Extract structured data (vendor, amount, dates, etc.)
5. Update DB `structured_data` field
6. Set `status='summarized'`

**Generic Architecture:**
- No hardcoded handlers
- All prompt-driven from database
- Works for any document type

See: [`document-processor/src/document_processor/summarizer_worker.py`](document-processor/src/document_processor/summarizer_worker.py)

### SummarizerScorerWorker ✅

**Purpose:** Evaluate summarization quality and evolve prompts

**Flow:**
1. Poll DB for `status='summarized'` documents
2. Wait for min 5 documents per type since last score
3. Call MCP tool: `score_summarization(doc, summary, prompt_version)`
4. Analyze extraction completeness, accuracy, usefulness
5. If score > current + 0.05 → create new prompt version
6. Set `status='completed'`

**Per-Type Evolution:**
- Each document type has its own summarizer prompt
- Prompts evolve independently based on type-specific performance

See: [`document-processor/src/document_processor/scorer_workers.py`](document-processor/src/document_processor/scorer_workers.py)

---

## Orchestration

### Main Entry Point

[`document-processor/src/document_processor/main.py`](document-processor/src/document_processor/main.py):

```python
async def main():
    """Run all worker pools concurrently."""
    settings = Settings()
    
    # Initialize 5 workers
    workers = [
        OCRWorker(settings),
        ClassifierWorker(settings),
        ClassifierScorerWorker(settings),
        SummarizerWorker(settings),
        SummarizerScorerWorker(settings)
    ]
    
    # Create pool
    pool = WorkerPool()
    for worker in workers:
        pool.add_worker(worker)
    
    # Run until Ctrl+C
    await pool.start()
```

**Deployment:**
- Development: `./scripts/start-processor` (runs all workers)
- Production: Supervisord manages worker process
- Scaling: Increase worker concurrency in config

---

## Data Flow Example

**User uploads 2-page PG&E bill:**

```
1. Add document: ./scripts/add-document page1.jpg page2.jpg --tags bill
   → Creates: data/inbox/bill_20241130_140000/
   → Inserts DB: status='pending'

2. OCRWorker (3 workers, poll every 5s)
   → Processes with AWS Textract
   → Saves: {doc_id}.txt, {doc_id}_llm.json
   → Updates: status='ocr_completed'

3. ClassifierWorker (5 workers, poll every 2s)
   → Uses DB prompt: "Classify this document..."
   → Calls Bedrock: "This is a utility bill..."
   → Updates: document_type='bill', status='classified'

4. ClassifierScorerWorker (2 workers, poll every 10s)
   → Evaluates classification accuracy
   → If improved: Creates prompt v2
   → Updates: status='scored_classification'

5. SummarizerWorker (5 workers, poll every 2s)
   → Uses bill-specific prompt
   → Extracts: vendor, amount, due_date
   → Updates: structured_data={...}, status='summarized'

6. SummarizerScorerWorker (2 workers, poll every 10s)
   → Evaluates extraction quality
   → If improved: Creates bill prompt v2
   → Updates: status='completed'

Done! Document fully processed and searchable.
```

---

## Configuration & Tuning

### Cloud API Limits

**AWS Textract:**
- Free tier: 1,000 pages/month
- Paid: $1.50/1,000 pages
- TPS limit: ~5 requests/second
- **Config:** `ocr_workers: int = 3` (safe for TPS)

**AWS Bedrock (Nova Lite):**
- Cost: $0.0006/1K input tokens
- Concurrency: Varies by region (typically 10-50)
- **Config:** `classifier_workers: int = 5`

### Performance Tuning

```python
# Aggressive (high cloud limits)
ocr_workers: int = 10
classifier_workers: int = 20
worker_batch_multiplier: int = 3  # Fetch 3× concurrency

# Conservative (low limits or cost-sensitive)
ocr_workers: int = 2
classifier_workers: int = 3
worker_batch_multiplier: int = 1
```

---

## Observability

### Query Pipeline Status

```sql
-- See documents in each stage
SELECT status, COUNT(*) 
FROM documents 
GROUP BY status;

-- Find failed documents
SELECT id, filename, error_message
FROM documents
WHERE status = 'failed'
ORDER BY updated_at DESC;
```

### Logs

Each worker logs:
- Documents fetched
- Processing start/end
- Errors with stack traces
- Status transitions

```
2024-11-30 08:54:48 - INFO - OCR Worker found 2 documents, processing 2 in parallel
2024-11-30 08:54:51 - INFO - Extracted 1154 chars with 98.47% confidence
```

---

## File Structure

```
document-processor/
├── src/document_processor/
│   ├── main.py                 # 5-worker orchestrator
│   ├── workers.py              # BaseWorker, WorkerPool
│   ├── ocr_worker.py           # AWS Textract
│   ├── classifier_worker.py    # DB-driven classification
│   ├── summarizer_worker.py    # Generic summarization
│   ├── scorer_workers.py       # Prompt evolution
│   └── extractors/
│       ├── aws_textract.py     # Textract integration
│       └── text.py             # Plain text extraction
```

**PostgreSQL Layer:** [`shared/database.py`](shared/database.py) (674 lines)
- asyncpg connection pooling
- All CRUD operations
- Prompt management
- Full-text search

---

## Testing

**Database Tests:** [`shared/tests/test_database.py`](shared/tests/test_database.py)
- 20/20 tests passing
- PostgreSQL CRUD operations
- Prompt management
- Full-text search

**Pipeline Test:** [`samples/test-pipeline.sh`](samples/test-pipeline.sh)
- End-to-end test with PG&E bill sample
- Verifies all 5 workers
- Checks prompt evolution
- Results: ✅ 98.47% OCR confidence, ✅ 95% classification confidence

---

## Summary

**Current Status:** 5-worker self-improving pipeline complete ✅

**Key Benefits:**
- ✅ DB-driven (crash-resistant)
- ✅ Parallel processing (configurable concurrency)
- ✅ Observable (query DB for status)
- ✅ Modular (workers are independent)
- ✅ Self-improving (prompts evolve automatically)

**Next Steps:**
1. Complete PWA camera to API integration
2. Add real-time status updates in UI
3. Test end-to-end mobile workflow

This design scales from a single laptop to distributed cloud deployment while maintaining simplicity and observability.

---

**Last Updated:** 2025-11-30