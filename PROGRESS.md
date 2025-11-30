# ALFRD - Development Progress

**Last Updated:** 2025-11-30 (PostgreSQL Migration Complete)

## Current Phase: Phase 1C Complete + PostgreSQL Migration ✅

### Pipeline Testing & Validation - COMPLETED

**Test Results from `./samples/test-pipeline.sh`:**
- ✅ OCR Worker: 98.47% confidence with AWS Textract
- ✅ Classification: 95% confidence as "bill" document type
- ✅ Prompt Evolution: Classifier v1→v2 (score: 0.85), Bill Summarizer v1→v2 (score: 0.85)
- ✅ Complete pipeline: pending → ocr_completed → classified → scored_classification → summarized → completed

**Issues Found and Fixed:**
1. **Minimum scoring threshold** - Changed `min_documents_for_scoring` from 5 to 1 in [`shared/config.py`](shared/config.py:62)
2. **SummarizerScorerWorker direct LLM calls** - Refactored to use MCP tools exclusively (architecture violation fixed)

**New Tools Created:**
- [`scripts/view-prompts`](scripts/view-prompts) - View prompt evolution history
- [`document-processor/src/document_processor/cli/view-prompts.py`](document-processor/src/document_processor/cli/view-prompts.py) - CLI implementation

### Self-Improving Prompt Architecture - COMPLETED

**Commits:**
- `f66f19d` - Folder-based processing with AWS Textract OCR ✅
- `e38ed47` - Worker pool base class with tests (6/6 passing) ✅
- `b2caf0f` - OCRWorker implementation with tests ✅
- `[TBD]` - ClassifierWorker with MCP integration ✅
- `[TBD]` - WorkflowWorker with type-specific handlers ✅
- `[TBD]` - Main.py orchestrator with all three workers ✅

**Status:**
- ✅ **BaseWorker** - Abstract base class for DB-driven polling workers
- ✅ **WorkerPool** - Manages multiple workers concurrently
- ✅ **OCRWorker** - Processes `pending` → `ocr_completed` with AWS Textract
- ✅ **ClassifierWorker** - MCP integration for document classification
- ✅ **WorkflowWorker** - Type-specific handlers (bill/finance/junk)
- ✅ **Main orchestrator** - Runs all workers concurrently

**Architecture:** State-machine-driven parallel workers
- Workers poll database for documents in specific status
- Process in parallel with configurable concurrency
- State transitions tracked in DB for observability/recovery
- See [`DOCUMENT_PROCESSING_DESIGN.md`](DOCUMENT_PROCESSING_DESIGN.md) for complete design

---

## Recent Major Update (November 2024)

### Document Processor Overhaul - COMPLETED ✅

**Key Changes:**
- ✅ **Folder-based input structure** - Documents organized in folders with `meta.json`
- ✅ **AWS Textract OCR** - Replaced Claude Vision for production-quality OCR
- ✅ **LLM-optimized output** - Preserves block-level data (PAGE, LINE, WORD) + full text
- ✅ **Standalone execution** - Built-in PYTHONPATH setup, no wrapper scripts needed
- ✅ **Comprehensive logging** - Timestamps, levels, detailed error messages
- ✅ **Test suite** - Pytest tests for storage module with temp database fixtures
- ✅ **Helper scripts** - `add-document.py` for easy document ingestion

### Files Updated/Created

**New/Modified Core Files:**
1. `document-processor/src/document_processor/main.py` - Complete rewrite for folder processing
2. `document-processor/src/document_processor/storage.py` - `store_document_folder()` method
3. `document-processor/src/document_processor/detector.py` - `validate_document_folder()` method
4. `document-processor/src/document_processor/extractors/aws_textract.py` - Block-level data extraction
5. `document-processor/tests/test_storage.py` - Comprehensive test suite

**New Helper Scripts:**
6. `scripts/add-document.py` - CLI tool to add documents to inbox
7. `scripts/process-documents.sh` - Wrapper for document processor
8. `samples/test_ocr.py` - Updated to display Textract blocks

**Updated Documentation:**
9. `START_HERE.md` - Complete rewrite with new workflow
10. `PROGRESS.md` - This file
11. `README.md` - Updated (pending)
12. `IMPLEMENTATION_PLAN.md` - Updated (pending)

## Current Architecture

### Folder-Based Document Structure

```
data/inbox/
└── my-bill_20241125_120000/
    ├── meta.json              # Required metadata
    ├── bill.jpg               # Document files
    └── page2.jpg              # Multi-page support
```

### Self-Improving Processing Pipeline

```
1. User adds document → scripts/add-document.py
   ↓
2. Document folder created in data/inbox/ (PENDING)
   ↓
3. OCRWorker → AWS Textract OCR (OCR_COMPLETED)
   ↓
4. ClassifierWorker → DB prompt + suggest types (CLASSIFIED)
   ↓
5. ClassifierScorerWorker → Score & evolve prompt (SCORED_CLASSIFICATION)
   ↓
6. SummarizerWorker → Type-specific DB prompt (SUMMARIZED)
   ↓
7. SummarizerScorerWorker → Score & evolve prompt (COMPLETED)
```

**Self-Improving Features:**
- Prompts stored in DB and versioned
- Classifier prompt evolves based on accuracy (max 300 words)
- Summarizer prompts (per type) evolve based on extraction quality
- LLM can suggest new document types
- Secondary tags for flexible organization
- Performance metrics tracked for each prompt version

### Output Structure

```
data/documents/2024/11/
├── raw/{doc-id}/              # Original folder copy
├── text/
│   ├── {doc-id}.txt          # Full text for search
│   └── {doc-id}_llm.json     # LLM-formatted with blocks
└── meta/{doc-id}.json         # Detailed metadata
```

## Working Features

### ✅ Fully Functional

1. **Document ingestion** - `add-document.py` creates proper folder structure
2. **AWS Textract OCR** - Extracts text with confidence scores and bounding boxes
3. **Block-level data** - Preserves PAGE, LINE, WORD blocks for LLM consumption
4. **Multi-document folders** - Processes multiple images/text files as single document
5. **Database storage** - Stores in PostgreSQL with full metadata
6. **Filesystem organization** - Year/month directory structure
7. **LLM-optimized format** - Combined text + blocks by document
8. **Logging** - Comprehensive logging with timestamps
9. **Error handling** - Graceful failures with detailed messages
10. **Test suite** - Pytest tests for storage module
11. **Standalone execution** - All scripts work without PYTHONPATH setup

### ✅ Phase 2A Partially Implemented

1. **API Server** - ✅ Implemented with 5 endpoints (health, status, documents list/detail/file, upload-image)
2. **Web UI** - ✅ Basic Ionic React PWA with 3 pages (CapturePage, DocumentsPage, DocumentDetailPage)
3. **Image upload** - ⏳ API endpoint exists, needs integration testing
4. **Camera capture** - ⏳ UI structure ready, needs backend wiring

### ✅ Phase 1B Complete

1. **Worker Pool Architecture** - BaseWorker + WorkerPool + OCRWorker ✅
2. **ClassifierWorker** - MCP integration for document classification ✅
3. **WorkflowWorker** - Type-specific handlers (bill/finance/junk) ✅
4. **MCP Tools** - classify_document + summarize_bill ✅
5. **Main Orchestrator** - All three workers running in parallel ✅

### ✅ Phase 1C Complete - Self-Improving Prompts

1. **Database Schema** - Added prompts, classification_suggestions, document_types tables ✅
2. **Dynamic Classification** - LLM can suggest new document types beyond defaults ✅
3. **Secondary Tags** - Flexible classification tags (tax, university, utility, etc.) ✅
4. **ClassifierWorker** - Now uses DB-stored prompts, accepts type suggestions ✅
5. **ClassifierScorerWorker** - Scores classification and evolves prompt (300 word max) ✅
6. **SummarizerWorker** - Generic DB-driven summarizer (replaces hardcoded handlers) ✅
7. **SummarizerScorerWorker** - Scores summaries and evolves type-specific prompts ✅
8. **Prompt Evolution** - Automatic prompt improvement based on performance ✅
9. **5-Worker Pipeline** - OCR → Classify → Score → Summarize → Score → Complete ✅
10. **Default Prompts** - Initialized for classifier + 6 summarizer types ✅

### ❌ Not Yet Implemented

1. **Real-time file watching** - watcher.py exists but not used (use batch mode --once instead)
2. **Hierarchical summaries** - Not started (weekly → monthly → yearly)
3. **Analytics dashboard** - Not started
4. **Financial CSV exports** - Not started
5. **Full PWA integration** - Camera to upload to API to processing workflow
6. **Event emission** - events.py exists but not currently used

## Test Results

```bash
# Storage tests - ALL PASSING ✅
pytest document-processor/tests/test_storage.py -v

test_storage.py::TestDocumentStorage::test_database_connection PASSED
test_storage.py::TestDocumentStorage::test_store_document_folder PASSED
test_storage.py::TestDocumentStorage::test_update_document_status PASSED
test_storage.py::TestDocumentStorage::test_update_document_status_with_error PASSED
test_storage.py::TestDocumentStorage::test_get_document PASSED
```

## Usage Examples

### Add and Process Documents

```bash
# 1. Initialize database (REQUIRED FIRST TIME!)
python3 scripts/init-db.py

# 2. Add a document
python scripts/add-document.py samples/pg\&e-bill.jpg --tags bill utilities

# 3. Process documents
python3 document-processor/src/document_processor/main.py

# 4. Check results
ls -la data/processed/
ls -la data/documents/2024/11/
```

### Test OCR

```bash
# See detailed block output from Textract
python samples/test_ocr.py samples/pg\&e-bill.jpg
```

## Statistics

**Lines of Code (PostgreSQL Migration Complete):**
- Document Processor Core: ~800 lines (main.py, storage.py, detector.py, extractors)
- Worker Infrastructure: ~418 lines (workers.py, ocr_worker.py)
- Classifier Worker: ~237 lines (classifier_worker.py - DB-driven)
- Scorer Workers: ~556 lines (scorer_workers.py - Using MCP tools)
- Summarizer Worker: ~263 lines (summarizer_worker.py)
- MCP Server: ~400 lines (bedrock.py, classify_dynamic.py, score_performance.py, summarize_dynamic.py)
- API Server: ~452 lines (main.py with 5 endpoints)
- Web UI: ~100+ lines (App.jsx + 3 pages)
- Database Layer: ~674 lines (shared/database.py - PostgreSQL with asyncpg)
- Tests: ~850 lines (test_database.py with 20 PostgreSQL tests)
- Helper Scripts: ~750 lines (add-document, create-alfrd-db, view-document, view-prompts)
- Database Schema: ~246 lines (PostgreSQL schema.sql)
- **Total: ~5,700+ lines**

**Test Coverage:**
- Database module: 100% (20/20 tests passing)
- PostgreSQL integration: Full CRUD + prompts + search
- **Total: 20/20 tests passing** ✅

## Next Steps

### Immediate (Phase 2B - Complete PWA Integration)
1. ✅ Basic PWA UI structure created - COMPLETED
2. ✅ API upload-image endpoint implemented - COMPLETED
3. ⏳ Test camera capture to upload workflow
4. ⏳ Wire up PWA to API server (fetch documents from API)
5. ⏳ Test end-to-end: photo → upload → process → classify → summarize → view in UI
6. ⏳ Add real-time document status updates in UI

### Short Term (Phase 2C - Enhanced Features)
1. Add document search in PWA
2. Add document filtering by type/status in UI
3. Improve UI/UX with better styling
4. Add error handling and loading states
5. Test offline functionality (if desired)
6. Add file upload progress indicator

### Medium Term (Phase 3 - Enhanced Features)
1. Add comprehensive integration tests for full pipeline
2. Implement hierarchical summaries (weekly → monthly → yearly)
3. Add financial tracking with CSV exports
4. Implement real-time file watching (watchdog)
5. Add analytics dashboard for prompt performance

### Medium Term (Phase 3)
1. Hierarchical summaries (weekly/monthly/yearly)
2. Financial tracking and CSV exports
3. Web UI implementation
4. Real-time file watching (watchdog)
5. Analytics dashboard

## Known Issues & Notes

1. **PostgreSQL Required** - PostgreSQL 15+ must be installed and running
2. **Database must be initialized** - Users must run `./scripts/create-alfrd-db` before first use
3. **Unix Socket Connection** - Development uses Unix sockets for performance (Docker uses TCP)
4. **Minimum scoring threshold** - Set to 1 for testing; production should use 5+
5. **MCP Architecture Rule** - Document processors must ONLY call MCP tools, never LLM directly

## Technical Decisions

### Why PostgreSQL?
- Production-ready with proven scalability
- Full-text search with GIN indexes
- JSONB for flexible structured data
- Connection pooling with asyncpg
- Better multi-user support
- Native triggers for auto-updating fields

### Why AWS Textract?
- Production-quality OCR (95%+ accuracy)
- Block-level data preservation
- Table/form extraction support
- Cost-effective ($1.50/1000 pages)

### Why Unix Socket Connections?
- Faster than TCP for local development
- Lower latency for database operations
- More secure (no network exposure)
- Docker shares socket via volume mount

## Architecture Notes

### PostgreSQL Migration (2025-11-30)
- **asyncpg Connection Pooling** - Efficient async database access
- **Full-Text Search** - GIN indexes on TSVECTOR for fast search
- **JSONB Storage** - Flexible structured data with indexing
- **Auto-Updating Triggers** - Timestamps and search vectors
- **Unix Socket Connections** - High performance for local dev
- **Test Database Isolation** - Separate `alfrd_test` database

### Worker Architecture
- **State-machine-driven** - All state in PostgreSQL, not memory
- **Parallel processing** - Configurable concurrency per worker
- **Crash-resistant** - Workers resume from database state
- **Observable** - Query database to see pipeline status

### MCP Integration
- **MCP tools as libraries** - Imported directly by workers
- **⚠️ Architecture Rule** - Workers ONLY call MCP tools, never BedrockClient directly
  - Ensures consistent prompt management and versioning
  - Makes future MCP server transition seamless
  - Example: Use `score_summarization()` not `bedrock_client.invoke_model()`

## Phase 1C Implementation Details

### Self-Improving Worker Pipeline

**Five-Worker Pipeline:**
1. **OCRWorker** - Polls for `pending`, runs AWS Textract OCR → `ocr_completed`
2. **ClassifierWorker** - Polls for `ocr_completed`, uses DB prompt, suggests types → `classified`
3. **ClassifierScorerWorker** - Polls for `classified`, scores & evolves prompt → `scored_classification`
4. **SummarizerWorker** - Polls for `scored_classification`, type-specific summarization → `summarized`
5. **SummarizerScorerWorker** - Polls for `summarized`, scores & evolves prompt → `completed`

**Prompt Evolution System:**
- **Classifier Prompt**: Single prompt (max 300 words), evolves based on classification accuracy
- **Summarizer Prompts**: One per document type (bill, finance, school, event, junk, generic)
- **Scoring**: LLM evaluates its own performance, suggests improvements
- **Versioning**: All prompts tracked with version numbers and performance scores
- **Thresholds**: Min 5 documents before scoring, 0.05 score improvement to update

**Dynamic Classification:**
- LLM can suggest NEW document types not in initial list
- Suggestions recorded in `classification_suggestions` table
- Secondary tags for flexible organization (tax, university, utility, etc.)
- Document types managed in `document_types` table

**MCP Integration:**
- MCP tools used as library functions (no separate server)
- BedrockClient handles AWS Bedrock API (Claude Sonnet 4 + Amazon Nova)
- Full Textract blocks sent to LLM for spatial reasoning

**Key Design Decisions:**
- NO hardcoded handlers - all prompt-driven
- Prompts improve automatically based on feedback
- System learns from mistakes and adapts
- Generic architecture works for any document type
- Workers poll at 3-5s intervals (configurable)

---

---

## PostgreSQL Migration Details (2025-11-30)

### Changes Made
1. **Database Engine** - PostgreSQL 15 with asyncpg
2. **Connection Method** - asyncpg connection pooling (5-20 connections)
3. **Schema Updates** - JSONB for JSON fields, TSVECTOR for full-text search
4. **Triggers** - Auto-update `updated_at` and `extracted_text_tsv`
5. **Test Database** - Separate `alfrd_test` database for tests

### Migration Benefits
- ✅ Production-ready scalability
- ✅ Better concurrent access
- ✅ Faster full-text search (GIN indexes)
- ✅ JSONB indexing for structured queries
- ✅ Connection pooling for efficiency

### Files Changed
- `shared/config.py` - Added PostgreSQL connection settings
- `shared/database.py` - Complete rewrite with asyncpg
- `api-server/src/api_server/db/schema.sql` - PostgreSQL syntax
- `shared/tests/test_database.py` - 20 comprehensive tests
- `scripts/create-alfrd-db` - PostgreSQL database creation
- Documentation updated across all markdown files

---

**Status:** Phase 1C complete + PostgreSQL migration complete! Self-improving prompt architecture with production-ready database. Next: Complete PWA integration for mobile photo capture.