# ALFRD Document Processing Architecture Design

**Status:** ✅ Phase 1A Complete | 🚧 Phase 1B In Progress (Worker Architecture)

---

## Executive Summary

ALFRD uses a **state-machine-driven parallel worker architecture** where:
- Documents flow through multiple processing stages (OCR → Classification → Workflow)
- Each stage is handled by specialized workers polling the database
- Workers process documents in parallel with configurable concurrency
- All state is tracked in DuckDB for observability and crash recovery
- MCP server provides LLM abstraction for classification and extraction

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Document Processing Pipeline                 │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  User adds folder → Inbox Scanner → INSERT status='pending'      │
│                                                                   │
│  ┌──────────────┐         ┌──────────────┐        ┌───────────┐│
│  │  OCR Worker  │────────→│ Classifier   │───────→│ Workflow  ││
│  │              │         │ Worker       │        │ Worker    ││
│  │ Textract OCR │         │ MCP classify │        │Type-based ││
│  │              │         │              │        │handlers   ││
│  └──────────────┘         └──────────────┘        └───────────┘│
│       ↓                        ↓                       ↓         │
│  ocr_completed            classified              completed      │
│                                                                   │
│                    Database-Driven State Machine                 │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │ Status Flow:                                               │ │
│  │ pending → ocr_started → ocr_completed →                    │ │
│  │ classifying → classified → processing → completed          │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Core Design Principles

### 1. Database-Driven State Machine

**All state lives in DuckDB, not in-memory:**

```sql
-- Document status progression tracked in DB
status VARCHAR CHECK (status IN (
    'pending',           -- Document folder detected
    'ocr_started',       -- AWS Textract called
    'ocr_completed',     -- Text extracted
    'classifying',       -- MCP classification in progress
    'classified',        -- Type determined (junk/bill/finance)
    'processing',        -- Type-specific handler processing
    'completed',         -- All processing done
    'failed'            -- Error at any stage
))
```

**Benefits:**
- ✅ Workers can crash and resume from DB state
- ✅ No in-memory queues that lose data on restart
- ✅ Observable: `SELECT * FROM documents WHERE status='classifying'`
- ✅ Backpressure: Workers only fetch what they can process

### 2. Parallel Worker Pools

Each processing stage has a dedicated worker pool:

| Worker | Input Status | Output Status | Cloud API | Concurrency |
|--------|-------------|---------------|-----------|-------------|
| **OCRWorker** | `pending` | `ocr_completed` | AWS Textract | 3 workers |
| **ClassifierWorker** | `ocr_completed` | `classified` | AWS Bedrock | 5 workers |
| **WorkflowWorker** | `classified` | `completed` | (none) | 3 workers |

**Configuration:** `shared/config.py`
```python
# Worker concurrency (tune per cloud API limits)
ocr_workers: int = 3              # AWS Textract TPS
classifier_workers: int = 5        # Bedrock requests/minute
workflow_workers: int = 3          # CPU-bound processing

# Poll intervals
ocr_poll_interval: int = 5         # seconds
classifier_poll_interval: int = 2  # seconds
workflow_poll_interval: int = 5    # seconds
```

### 3. Worker Base Class Pattern

All workers extend `BaseWorker`:

```python
class BaseWorker(ABC):
    """Base class for all document processing workers."""
    
    async def run(self):
        """Main loop: poll DB, process batch, repeat."""
        while self.running:
            # Get documents in source_status
            docs = await self.get_documents(
                status=self.source_status,
                limit=self.concurrency * batch_multiplier
            )
            
            # Process in parallel
            tasks = [self.process_document(doc) for doc in docs[:concurrency]]
            await asyncio.gather(*tasks)
            
            await asyncio.sleep(self.poll_interval)
    
    @abstractmethod
    async def get_documents(self, status, limit) -> List[dict]:
        """Query DB for documents to process."""
        pass
    
    @abstractmethod
    async def process_document(self, document: dict) -> bool:
        """Process single document (worker-specific logic)."""
        pass
```

**Key Features:**
- Configurable concurrency per worker type
- Automatic batch sizing (concurrency × multiplier)
- Graceful shutdown
- Error handling with status updates

---

## Worker Implementations

### OCRWorker (✅ Implemented)

**Purpose:** Extract text from images/PDFs using AWS Textract

**Flow:**
1. Poll DB for `status='pending'` documents
2. Read `meta.json` from document folder
3. Process each file (image → Textract, text → direct)
4. Combine into LLM-optimized format (full text + blocks)
5. Save to filesystem and update DB
6. Set `status='ocr_completed'`

**Key Code:**
```python
class OCRWorker(BaseWorker):
    def __init__(self, settings):
        super().__init__(
            source_status=DocumentStatus.PENDING,
            target_status=DocumentStatus.OCR_COMPLETED,
            concurrency=settings.ocr_workers,
            poll_interval=settings.ocr_poll_interval,
        )
    
    async def process_document(self, doc):
        # AWS Textract OCR
        # Save extracted_text to DB
        # Update status to ocr_completed
```

**Output:**
- `{doc_id}.txt` - Full extracted text
- `{doc_id}_llm.json` - LLM-optimized format with blocks
- DB field: `extracted_text` (for classification)

### ClassifierWorker (⏳ To Implement)

**Purpose:** Classify documents as junk/bill/finance using MCP + Bedrock

**Flow:**
1. Poll DB for `status='ocr_completed'` documents
2. Read `extracted_text` from DB
3. Call MCP server: `classify_document(text, filename)`
4. MCP invokes Bedrock with classification prompt
5. Update DB with `document_type`, `confidence`, `reasoning`
6. Set `status='classified'`

**MCP Integration:**
```python
from mcp_server.tools.classify_document import classify_document
from mcp_server.llm.bedrock import BedrockClient

bedrock = BedrockClient()
result = classify_document(extracted_text, filename, bedrock)

# Update DB
UPDATE documents SET
    document_type = result.document_type,      # junk/bill/finance
    classification_confidence = result.confidence,
    classification_reasoning = result.reasoning,
    status = 'classified'
WHERE id = doc_id
```

**Why MCP?**
- Abstraction: Swap LLM providers (Bedrock → Claude → local)
- Reusable: Same tools work in Claude Desktop
- Testable: Mock MCP server for tests
- Flexible: Easy to change prompts/models

### WorkflowWorker (⏳ To Implement)

**Purpose:** Route classified documents to type-specific handlers

**Flow:**
1. Poll DB for `status='classified'` documents
2. Route by `document_type`:
   - **junk** → Mark `status='completed'` (no processing)
   - **bill** → `BillHandler` (extract vendor, amount, due date)
   - **finance** → `FinanceHandler` (extract account, amounts, dates)
3. Update summaries/reports
4. Set `status='completed'`

**Type-Specific Handlers:**
```python
class WorkflowWorker(BaseWorker):
    async def process_document(self, doc):
        if doc['document_type'] == 'bill':
            await self.handle_bill(doc)
        elif doc['document_type'] == 'finance':
            await self.handle_finance(doc)
        else:  # junk
            await self.mark_completed(doc)

class BillHandler:
    async def process(self, doc):
        # Call MCP: extract_bill_data(text)
        # Get: vendor, amount, due_date, account_number
        # Append to monthly bill summary
        # Update DB structured_data
```

---

## Orchestration

### Main Entry Point

`document-processor/src/document_processor/main.py` (to be updated):

```python
async def main():
    """Run all worker pools concurrently."""
    settings = Settings()
    
    # Initialize workers
    ocr_worker = OCRWorker(settings)
    classifier_worker = ClassifierWorker(settings)
    workflow_worker = WorkflowWorker(settings)
    
    # Create pool
    pool = WorkerPool()
    pool.add_worker(ocr_worker)
    pool.add_worker(classifier_worker)
    pool.add_worker(workflow_worker)
    
    # Run until Ctrl+C
    await pool.start()
```

**Deployment:**
- Development: `python main.py` (runs all workers)
- Production: Supervisord manages worker processes
- Scaling: Increase worker concurrency per cloud limits

---

## Data Flow Example

**User uploads 2-page PG&E bill:**

```
1. User runs: python scripts/add-document.py page1.jpg page2.jpg --tags bill
   → Creates: data/inbox/bill_20241125_120000/
      ├── meta.json
      ├── page1.jpg
      └── page2.jpg
   → Inserts DB: status='pending'

2. OCRWorker (3 workers polling every 5s)
   → Fetches: SELECT * FROM documents WHERE status='pending' LIMIT 6
   → Processes page1.jpg + page2.jpg with AWS Textract
   → Combines: "PG&E Energy Statement\n[full text from both pages]"
   → Saves: {doc_id}.txt, {doc_id}_llm.json
   → Updates DB: status='ocr_completed', extracted_text='...'

3. ClassifierWorker (5 workers polling every 2s)
   → Fetches: SELECT * FROM documents WHERE status='ocr_completed' LIMIT 10
   → Calls MCP: classify_document(text="PG&E Energy Statement...", filename="bill...")
   → MCP → Bedrock: "This is a utility bill..."
   → Updates DB: document_type='bill', status='classified'

4. WorkflowWorker (3 workers polling every 5s)
   → Fetches: SELECT * FROM documents WHERE status='classified' LIMIT 6
   → Routes to BillHandler (document_type='bill')
   → Calls MCP: extract_bill_data(text)
   → Gets: {vendor: "PG&E", amount: 125.43, due_date: "2024-12-15"}
   → Appends to: data/summaries/monthly/2024-11-bills.md
   → Updates DB: structured_data={...}, status='completed'

5. Done! Document fully processed and searchable.
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

# Conservative (low cloud limits or cost-sensitive)
ocr_workers: int = 2
classifier_workers: int = 3
worker_batch_multiplier: int = 1
```

---

## Observability & Debugging

### Query Pipeline Status

```sql
-- See documents stuck in each stage
SELECT status, COUNT(*) 
FROM documents 
GROUP BY status;

-- Find failed documents
SELECT id, filename, error_message
FROM documents
WHERE status = 'failed'
ORDER BY updated_at DESC;

-- Processing time analysis
SELECT 
    AVG(EXTRACT(EPOCH FROM (processed_at - created_at))) as avg_seconds
FROM documents
WHERE status = 'completed';
```

### Logs

Each worker logs:
- Documents fetched
- Processing start/end
- Errors with stack traces
- Status transitions

```
2024-11-24 18:54:48 - INFO - OCR Worker found 2 documents, processing 2 in parallel
2024-11-24 18:54:51 - INFO - Extracted 1154 characters from pg&e-bill.jpg with 99.63% confidence
2024-11-24 18:54:51 - INFO - Updated document 73ef... status to ocr_completed
```

---

## Testing Strategy

### Unit Tests (6/6 passing)

`document-processor/tests/test_workers.py`:
- `test_base_worker_initialization`
- `test_worker_processes_documents` (parallel processing)
- `test_worker_handles_empty_queue`
- `test_worker_pool_manages_multiple_workers`
- `test_worker_respects_batch_multiplier`
- `test_worker_stops_gracefully`

### Integration Tests (⏳ To Add)

`document-processor/tests/test_pipeline_integration.py`:
1. Insert document with `status='pending'`
2. Run OCRWorker.process_document()
3. Verify `status='ocr_completed'` and text extracted
4. Run ClassifierWorker.process_document()
5. Verify `status='classified'` and `document_type` set
6. Run WorkflowWorker.process_document()
7. Verify `status='completed'` and summary updated

---

## Future Enhancements

### Phase 2: Advanced Features

1. **Retry Logic** - Exponential backoff for transient failures
2. **Priority Queue** - Process urgent documents first
3. **Batch OCR** - Send multiple images to Textract in single API call
4. **Worker Health Monitoring** - Detect stuck workers
5. **Metrics/Dashboard** - Grafana visualization of pipeline
6. **Multi-Tenancy** - Isolate users with `WHERE user_id = ?`

### Phase 3: Scaling

1. **Horizontal Scaling** - Run workers on multiple machines
2. **Distributed Queue** - Redis for cross-machine coordination
3. **Worker Specialization** - OCR-only nodes, classifier-only nodes
4. **Auto-scaling** - Scale workers based on queue depth

---

## File Structure

```
document-processor/
├── src/document_processor/
│   ├── workers.py              # BaseWorker, WorkerPool (216 lines)
│   ├── ocr_worker.py           # OCRWorker implementation (202 lines)
│   ├── classifier_worker.py    # ⏳ To implement
│   ├── workflow_worker.py      # ⏳ To implement
│   ├── main.py                 # Entry point (to update)
│   ├── storage.py              # DB operations
│   ├── detector.py             # File type detection
│   └── extractors/
│       ├── aws_textract.py     # AWS Textract integration
│       └── text.py             # Plain text extraction
├── tests/
│   ├── test_workers.py         # Worker tests (6/6 passing)
│   ├── test_storage.py         # Storage tests (5/5 passing)
│   └── test_pipeline_integration.py  # ⏳ To add
```

---

## Summary

**Current Architecture:** State-machine-driven parallel worker pools

**Key Benefits:**
- ✅ DB-driven (crash-resistant)
- ✅ Parallel processing (configurable concurrency)
- ✅ Observable (query DB for status)
- ✅ Modular (workers are independent)
- ✅ Testable (6/6 tests passing)

**Next Steps:**
1. Add OCRWorker tests
2. Implement ClassifierWorker with MCP
3. Implement WorkflowWorker with handlers
4. Update main.py to run worker pools
5. Add integration tests

This design scales from a single laptop to distributed cloud deployment while maintaining simplicity and observability.

---

**Last Updated:** 2024-11-25  
**Status:** Phase 1B In Progress (Worker Architecture)