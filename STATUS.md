# ALFRD - Current Status & Roadmap

**Last Updated:** 2025-12-12 (Series Schema Stability)

**Current Phase:** Phase 1C Complete + Series Schema Stability

---

## What's Working

### Phase 1C: Self-Improving Pipeline with Series Schema Stability

1. **Asyncio Orchestration**
   - OCR Step → Classify Step → Summarize Step → File Step → Series Summarize → Complete
   - Background scoring steps (fire-and-forget for prompt evolution)
   - Semaphore-based concurrency control (3 Textract, 5 Bedrock, 2 file-gen)
   - Automatic retry mechanism (max 3 attempts per item)
   - Periodic stale work recovery (every 5 minutes)
   - 30-minute timeout for stuck work
   - Series-based automatic filing
   - Series regeneration after prompt evolution

2. **Series-Specific Extraction (Schema Consistency)**
   - Each document series gets its own extraction prompt
   - First document creates series prompt from generic extraction
   - All subsequent documents use SAME prompt for identical field names
   - Eliminates schema drift (e.g., `total_amount` vs `amount_due`)
   - Enables clean data tables and aggregation
   - PostgreSQL advisory locks prevent concurrent prompt creation
   - Automatic regeneration when series prompt improves

3. **PostgreSQL Advisory Locks**
   - `series_prompt_lock` - Prevents race conditions in prompt creation
   - `document_type_lock` - Prevents concurrent processing of same type
   - Event logging for lock operations (requested, acquired, released, timeout)
   - Proper connection handling (held for duration of lock)

4. **Event Logging System**
   - Comprehensive event table for debugging
   - Categories: state_transition, llm_request, processing, error, user_action
   - LLM tracking: prompt, response, tokens, latency, cost
   - Lock events: requested, acquired, released, timeout
   - CLI viewer: `./scripts/view-events <uuid>`

5. **PostgreSQL Database**
   - asyncpg connection pooling (5-20 connections)
   - Full-text search with GIN indexes
   - JSONB for structured data
   - Unix socket connections for local dev
   - Advisory locks for distributed coordination

6. **AWS Textract OCR**
   - 95%+ accuracy on documents
   - Block-level preservation (PAGE, LINE, WORD)
   - Bounding boxes for spatial reasoning
   - ~2-3 seconds per page

7. **Self-Improving Prompts**
   - Classifier prompt evolution based on accuracy
   - Summarizer prompt evolution based on extraction quality
   - Series prompt evolution with automatic regeneration
   - LLM can suggest NEW document types
   - Performance metrics tracked for each version
   - Configure threshold via `PROMPT_UPDATE_THRESHOLD` (default: 0.05)

8. **Dynamic Classification**
   - 6 default types: bill, finance, school, event, junk, generic
   - LLM suggestions for new types
   - Secondary tags for flexible organization

9. **Series-Based Filing System**
   - Automatic series detection via LLM
   - Hybrid approach: series entities + tags + files
   - File Task: Creates series, applies tags, generates files
   - Series Summarize: Entity-specific extraction with schema enforcement
   - Database tables: series, document_series, files, file_documents, tags, document_tags

10. **API Server**
    - 30+ REST endpoints (documents, series, files, tags, prompts, events)
    - FastAPI with asyncio
    - OpenAPI documentation at `/docs`
    - File serving with security checks

11. **Ionic React PWA (90% Complete)**
    - **CapturePage** - Camera capture, photo preview, upload to API
    - **DocumentsPage** - API integration, document list, manual refresh
    - **DocumentDetailPage** - Full metadata, image preview, structured data
    - **Upload workflow** - Camera → Base64 → FormData → API
    - Missing: Automatic status polling (manual refresh works)

12. **Docker Deployment**
    - Single-container with supervisord
    - PostgreSQL via Unix socket
    - All services managed

13. **Test Suite**
    - 20/20 PostgreSQL tests passing
    - Database CRUD operations
    - Prompt management
    - Full-text search
    - JSON flattening tests (25+ test cases)

14. **Recovery & Retry Mechanisms**
    - Startup recovery scan for crashed work
    - Periodic recovery check every 5 minutes
    - Automatic retry on failure (max 3 attempts)
    - 30-minute timeout for stale work detection
    - Retry count tracking per document/file
    - Comprehensive error logging

---

## What's Pending

### Phase 2B: PWA Integration (90% Complete)

1. **Real-Time Status Updates**
   - Manual refresh works
   - Missing: Automatic polling for status updates
   - Optional: WebSocket/SSE for real-time updates

2. **End-to-End Testing**
   - Full pipeline testing (upload → process → view)
   - Error handling edge cases

### Phase 3: Enhanced Features (Planned)

1. **Hierarchical Summaries**
   - Weekly summary generation
   - Monthly rollup (aggregate weeks)
   - Yearly rollup (aggregate months)
   - Markdown + CSV exports

2. **Financial Tracking**
   - Running totals by category
   - Month-over-month trends
   - CSV exports for Excel
   - Budget tracking

3. **Analytics Dashboard**
   - Spending charts
   - Category breakdown
   - Prompt performance metrics
   - Document type distribution

4. **Advanced Search**
   - Complex filters (date range, amount, vendor)
   - Full-text search in UI
   - Saved searches

---

## Statistics

**Lines of Code:** ~8,000+ lines
- Document Processor: ~1,000 lines (orchestrator + tasks + regeneration)
- Advisory Locks: ~250 lines (document-processor/src/document_processor/utils/locks.py)
- Event Logger: ~280 lines (shared/event_logger.py)
- MCP Tools: ~700 lines (library functions + Bedrock client + series summarize)
- API Server: ~1,216 lines (30+ endpoints)
- Web UI: ~706 lines (3 fully functional pages)
- Database Layer: ~1,900 lines (shared/database.py with series/files/tags/events)
- Tests: ~850 lines (PostgreSQL + JSON flattening)
- Helper Scripts: ~800 lines
- Database Schema: ~750 lines (PostgreSQL with series, files, tags, events)

**Test Coverage:** 20/20 PostgreSQL tests + 25+ JSON flattening tests passing

**Test Results:**
- OCR: 98.47% confidence (AWS Textract)
- Classification: 95% confidence (Bedrock LLM)
- Prompt Evolution: Enabled with threshold=0.05
- Series Schema Consistency: 100% (all docs in series match)
- Full Pipeline: pending → ocr_completed → classified → summarized → filed → series_summarized → completed
- Series Detection: Automatic entity and series_type identification
- File Generation: Collection summaries with aggregated content
- Recovery: Automatic retry and stale work detection
- JSON Flattening: 4 array strategies with pandas integration
- Event Logging: Full audit trail for debugging

---

## Architecture Decision Record

### Series Schema Stability (2025-12-12)

**Decision:** Implement series-specific prompts with PostgreSQL advisory locks

**Problem:** Schema drift - documents in same series had inconsistent field names
- 12 State Farm bills → 12 different schemas
- `total_amount` vs `amount_due` vs `premium_amount`

**Solution:**
- Each series gets ONE prompt that extracts with consistent field names
- PostgreSQL advisory locks prevent concurrent prompt creation
- Regeneration updates all documents when prompt improves
- Dedicated regeneration function bypasses scoring (prevents infinite loop)

**Components:**
- `series_prompt_lock` in `locks.py`
- `series_regeneration.py` for regeneration worker
- `summarize_series.py` MCP tool
- Event logging for debugging

**Impact:**
- All documents in a series now have identical field names
- Clean data tables and aggregation
- Full audit trail via event logging

### PostgreSQL with Recovery Mechanisms (2025-11-30)

**Decision:** Use PostgreSQL 15+ with comprehensive recovery

**Rationale:**
- Production-ready scalability
- Better multi-user support
- asyncpg connection pooling
- Full-text search with GIN indexes
- JSONB for flexible structured data
- Unix socket connections for performance
- Advisory locks for distributed coordination
- Database-driven state machine enables crash recovery

**Recovery Features:**
- Periodic stale work detection (every 5 minutes)
- Automatic retry with max attempts tracking
- 30-minute timeout for stuck work
- Startup recovery scan
- Comprehensive error logging

### Asyncio Orchestration with Recovery (2025-12)

**Decision:** Use simple asyncio orchestrator with comprehensive recovery

**Rationale:**
- No external dependencies (simpler deployment)
- Semaphore-based concurrency control
- Database-driven state machine (crash-resistant)
- Automatic retry and recovery mechanisms
- Easy to understand and debug
- Sufficient for single-instance deployment

**Configuration:** `shared/config.py`
- Rate limits: 3 Textract, 5 Bedrock, 2 file-gen (via semaphores)
- Recovery interval: 5 minutes
- Stale timeout: 30 minutes
- Max retries: 3 per document/file

### MCP Architecture Rule (2024-11)

**Rule:** Document processors MUST call MCP tools only, never LLM clients directly

**Examples:**
- `score_classification()` (MCP tool)
- `bedrock_client.invoke_model()` (direct LLM call)

**Rationale:**
- Consistent prompt management
- Future MCP server transition seamless
- All LLM interactions logged/trackable

---

## Known Issues & Notes

1. **PostgreSQL Required** - Must install and run PostgreSQL 15+
2. **Database Initialization** - Run `./scripts/create-alfrd-db` before first use
3. **Unix Socket Connection** - Development uses Unix sockets, Docker uses TCP
4. **Prompt Evolution Threshold** - Configure via `PROMPT_UPDATE_THRESHOLD` env var (default: 0.05)
5. **Minimum Scoring Threshold** - Set to 1 for testing; production should use 5+
6. **MCP as Library** - Functions imported directly, not separate server process
7. **Recovery Configuration** - 5-minute interval, 30-minute timeout, 3 max retries
8. **Event Logging** - View events with `./scripts/view-events <uuid>`

---

## Next Steps (Priority Order)

### Immediate (Week 1-2)
1. Add automatic polling for document status updates (PWA)
2. Test end-to-end mobile workflow (photo → process → view)
3. UI polish and improvements
4. Document search in PWA

### Short Term (Week 3-4)
1. Hierarchical summaries (weekly/monthly/yearly)
2. Financial tracking with running totals
3. CSV export functionality
4. Analytics dashboard (basic)
5. Advanced search and filtering

### Medium Term (Month 2-3)
1. Comprehensive integration tests
2. Performance optimization
3. Production deployment guide
4. Multi-user architecture (if needed)
5. Backup/restore functionality

---

## File Structure Overview

```
esec/
├── api-server/              # FastAPI REST API
├── document-processor/      # Asyncio pipeline
│   └── src/document_processor/
│       ├── tasks/
│       │   ├── document_tasks.py
│       │   └── series_regeneration.py
│       └── utils/
│           └── locks.py     # PostgreSQL advisory locks
├── mcp-server/              # LLM tools (library)
│   └── src/mcp_server/tools/
│       └── summarize_series.py
├── web-ui/                  # Ionic React PWA
├── shared/                  # Database + config + events
│   ├── database.py
│   └── event_logger.py
├── docker/                  # Deployment
├── scripts/
│   ├── view-events          # Event log viewer
│   └── ...
└── data/                    # Runtime (not in git)
    ├── inbox/              # Input folders
    ├── documents/          # Processed output
    └── postgres/           # PostgreSQL data
```

---

## Recent Changes (2025-12-12)

### Series Schema Stability Implementation
- Implemented series-specific prompt system for schema consistency
- Added PostgreSQL advisory locks (`series_prompt_lock`)
- Created series regeneration worker (`series_regeneration.py`)
- Added comprehensive event logging system
- Fixed `get_series()` and `list_series()` to return `active_prompt_id`, `regeneration_pending`
- Fixed regeneration timing (now runs after background tasks complete)
- Created dedicated regeneration function that bypasses scoring
- Added `./scripts/view-events` CLI for debugging
- All documents in series now have identical field names
- Full audit trail via event logging

---

**Status:** Phase 1C Complete + Series Schema Stability! All documents in a series now have consistent field names. PostgreSQL advisory locks prevent race conditions. Event logging provides full debugging capability. Next: Complete PWA integration and comprehensive testing.
