# ALFRD - Current Status & Roadmap

**Last Updated:** 2025-12-10 (Asyncio Orchestrator Implementation)

**Current Phase:** Phase 2A Complete ✅ + Asyncio Orchestration ✅

---

## What's Working ✅

### Phase 1C: Self-Improving Pipeline (Complete - Asyncio Orchestrator)

1. **Asyncio Orchestration**
   - OCR Step → Classify Step → Summarize Step → File Step → Complete
   - Background scoring steps (fire-and-forget for prompt evolution)
   - Semaphore-based concurrency control (3 Textract, 5 Bedrock, 2 file-gen)
   - Automatic retry mechanism (max 3 attempts per item)
   - Periodic stale work recovery (every 5 minutes)
   - 30-minute timeout for stuck work
   - Series-based automatic filing
   - File collection summaries

2. **PostgreSQL Database**
   - asyncpg connection pooling (5-20 connections)
   - Full-text search with GIN indexes
   - JSONB for structured data
   - Unix socket connections for local dev

3. **AWS Textract OCR**
   - 95%+ accuracy on documents
   - Block-level preservation (PAGE, LINE, WORD)
   - Bounding boxes for spatial reasoning
   - ~2-3 seconds per page

4. **Self-Improving Prompts (Currently Disabled for Testing)**
   - Classifier prompt evolution implemented but disabled (threshold=999.0)
   - Summarizer prompt evolution implemented but disabled (threshold=999.0)
   - LLM can suggest NEW document types
   - Performance metrics tracked for each version
   - Min 1 document for testing (production should use 5+)
   - To enable: Set `prompt_update_threshold = 0.05` in config

5. **Dynamic Classification**
   - 6 default types: bill, finance, school, event, junk, generic
   - LLM suggestions for new types
   - Secondary tags for flexible organization

6. **Series-Based Filing System**
   - Automatic series detection via LLM
   - Hybrid approach: series entities + tags + files
   - File Task: Creates series, applies tags, generates files
   - File Generation Flow: Creates collection summaries
   - Database tables: series, document_series, files, file_documents, tags, document_tags

7. **API Server**
   - 30+ REST endpoints (documents, series, files, tags, prompts, etc.)
   - FastAPI with asyncio
   - OpenAPI documentation at `/docs`
   - File serving with security checks

7. **Ionic React PWA (90% Complete)**
   - ✅ **CapturePage** - Camera capture, photo preview, upload to API
   - ✅ **DocumentsPage** - API integration, document list, manual refresh
   - ✅ **DocumentDetailPage** - Full metadata, image preview, structured data
   - ✅ **Upload workflow** - Camera → Base64 → FormData → API
   - ⏳ **Auto-polling** - Missing automatic status updates (manual refresh works)

8. **Docker Deployment**
   - Single-container with supervisord
   - PostgreSQL via Unix socket
   - All services managed

9. **Test Suite**
   - 20/20 PostgreSQL tests passing
   - Database CRUD operations
   - Prompt management
   - Full-text search
   - JSON flattening tests (25+ test cases)

10. **Recovery & Retry Mechanisms**
    - Startup recovery scan for crashed work
    - Periodic recovery check every 5 minutes
    - Automatic retry on failure (max 3 attempts)
    - 30-minute timeout for stale work detection
    - Retry count tracking per document/file
    - Comprehensive error logging

---

## What's Pending ⏳

### Phase 2B: PWA Integration (90% Complete)

1. **Camera to API Upload Flow** ✅
   - ✅ Camera capture with Capacitor API
   - ✅ Upload to `/api/v1/upload-image` via FormData
   - ✅ Error handling with toast notifications
   - ✅ Photo preview before upload
   - ✅ Redirect to documents list after success

2. **Real-Time Status Updates** ⏳
   - ✅ Manual refresh (pull-to-refresh + button)
   - ✅ Status badges with color-coding
   - ⏳ Automatic polling for status updates (missing)
   - ⏳ WebSocket/SSE for real-time updates (optional)

3. **End-to-End Testing** ⏳
   - ✅ Photo capture working
   - ✅ Upload to API working
   - ✅ Document list display working
   - ✅ Document detail view working
   - ⏳ Full pipeline testing (upload → process → view)
   - ⏳ Error handling edge cases

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

**Lines of Code:** ~6,500+ lines
- Document Processor: ~800 lines (orchestrator + tasks)
- Asyncio Orchestration: ~435 lines (SimpleOrchestrator with recovery)
- MCP Tools: ~600 lines (library functions + Bedrock client)
- API Server: ~1,216 lines (30+ endpoints)
- Web UI: ~706 lines (3 fully functional pages)
- Database Layer: ~1,776 lines (shared/database.py with series/files/tags)
- Tests: ~850 lines (PostgreSQL + JSON flattening)
- Helper Scripts: ~750 lines
- Database Schema: ~693 lines (PostgreSQL with series, files, tags)

**Test Coverage:** 20/20 PostgreSQL tests + 25+ JSON flattening tests passing

**Test Results:**
- ✅ OCR: 98.47% confidence (AWS Textract)
- ✅ Classification: 95% confidence (Bedrock LLM)
- ✅ Prompt Evolution: Implemented but disabled for testing
- ✅ Full Pipeline: pending → ocr_completed → classified → summarized → filed → completed
- ✅ Series Detection: Automatic entity and series_type identification
- ✅ File Generation: Collection summaries with aggregated content
- ✅ Recovery: Automatic retry and stale work detection
- ✅ JSON Flattening: 4 array strategies with pandas integration

---

## Architecture Decision Record

### PostgreSQL with Recovery Mechanisms (2025-11-30) ✅

**Decision:** Use PostgreSQL 15+ with comprehensive recovery

**Rationale:**
- Production-ready scalability
- Better multi-user support
- asyncpg connection pooling
- Full-text search with GIN indexes
- JSONB for flexible structured data
- Unix socket connections for performance
- Database-driven state machine enables crash recovery

**Recovery Features:**
- Periodic stale work detection (every 5 minutes)
- Automatic retry with max attempts tracking
- 30-minute timeout for stuck work
- Startup recovery scan
- Comprehensive error logging

**Impact:**
- New dependency: PostgreSQL 15+
- Updated scripts: `create-alfrd-db`
- Migration: All queries converted to PostgreSQL syntax
- Tests: 20 comprehensive PostgreSQL tests

### Folder-Based Document Input (2024-11) ✅

**Structure:**
```
inbox/doc-folder/
├── meta.json          # Document metadata
├── image.jpg          # Document files
└── page2.jpg          # Multi-page support
```

**Benefits:**
- Multi-page documents as single entity
- Extensible metadata
- Clear processing order

### AWS Textract OCR (2024-11) ✅

**Decision:** Use AWS Textract instead of Claude Vision

**Rationale:**
- 95%+ accuracy on financial documents
- Block-level data preservation
- Bounding boxes for spatial reasoning
- Cost-effective: $1.50/1000 pages
- Table/form extraction support

**Trade-offs:**
- AWS dependency (but already using Bedrock)
- Requires AWS credentials

### Asyncio Orchestration with Recovery (2025-12) ✅

**Decision:** Use simple asyncio orchestrator with comprehensive recovery

**Rationale:**
- No external dependencies (simpler deployment)
- Semaphore-based concurrency control
- Database-driven state machine (crash-resistant)
- Automatic retry and recovery mechanisms
- Easy to understand and debug
- Sufficient for single-instance deployment

**Recovery Implementation:**
- `recover_stale_work()` - Detects and resets stuck items
- `_periodic_recovery()` - Background task runs every 5 minutes
- Retry counting with max attempts (3 per document/file)
- 30-minute timeout for in-progress states
- Startup recovery scan

**Configuration:** `shared/config.py`
- Rate limits: 3 Textract, 5 Bedrock, 2 file-gen (via semaphores)
- Recovery interval: 5 minutes
- Stale timeout: 30 minutes
- Max retries: 3 per document/file

### MCP Architecture Rule (2024-11) ✅

**Rule:** Document processors MUST call MCP tools only, never LLM clients directly

**Examples:**
- ✅ `score_classification()` (MCP tool)
- ❌ `bedrock_client.invoke_model()` (direct LLM call)

**Rationale:**
- Consistent prompt management
- Future MCP server transition seamless
- All LLM interactions logged/trackable

---

## Known Issues & Notes

1. **PostgreSQL Required** - Must install and run PostgreSQL 15+
2. **Database Initialization** - Run `./scripts/create-alfrd-db` before first use
3. **Unix Socket Connection** - Development uses Unix sockets, Docker uses TCP
4. **Prompt Evolution Disabled** - `prompt_update_threshold = 999.0` for testing
5. **Minimum Scoring Threshold** - Set to 1 for testing; production should use 5+
6. **MCP as Library** - Functions imported directly, not separate server process
7. **Recovery Configuration** - 5-minute interval, 30-minute timeout, 3 max retries

---

## Next Steps (Priority Order)

### Immediate (Week 1-2)
1. ✅ Complete PWA camera to API upload flow - DONE (90%)
2. Add automatic polling for document status updates (last 10%)
3. Test end-to-end mobile workflow (photo → process → view)
4. UI polish and improvements
5. Document search in PWA

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

## Open Questions

1. **Summary Triggers:** When should summaries auto-generate?
   - End of each period (cron job)?
   - On-demand only?
   - After N documents processed?

2. **Mobile Features Priority:**
   - Camera integration? ✅
   - Push notifications for bill reminders?
   - Biometric authentication?
   - Offline support?

3. **Production Deployment:**
   - Single-container sufficient?
   - Need Kubernetes for multi-user?
   - Backup strategy (DB snapshots to S3)?

4. **LLM Provider Strategy:**
   - Stay with Bedrock only?
   - Add Claude API as fallback?
   - Support local models (Ollama)?

---

## File Structure Overview

```
esec/
├── api-server/              # FastAPI REST API
├── document-processor/      # 7-worker pipeline
├── mcp-server/              # LLM tools (library)
├── web-ui/                  # Ionic React PWA
├── shared/                  # Database + config
├── docker/                  # Deployment
├── scripts/                 # CLI utilities
├── data/                    # Runtime (not in git)
│   ├── inbox/              # Input folders
│   ├── documents/          # Processed output
│   └── postgres/           # PostgreSQL data
└── docs/
    ├── ARCHITECTURE.md     # System design (consolidated)
    ├── STATUS.md           # This file
    ├── START_HERE.md       # User guide
    └── README.md           # Project overview
```

---

## Recent Changes (2025-12-10)

### Asyncio Orchestrator Implementation
- Implemented SimpleOrchestrator with semaphore-based concurrency
- Added comprehensive retry and recovery mechanisms
- Periodic stale work detection (every 5 minutes)
- Automatic retry on failure (max 3 attempts)
- 30-minute timeout for stuck work
- Startup recovery scan for crashed work
- Background scoring steps (fire-and-forget)
- MCP tools as library functions (no separate server)
- Prompt evolution implemented but disabled for testing (threshold=999.0)
- Updated all documentation to reflect actual implementation

---

**Status:** Phase 2A complete! Asyncio orchestrator with automatic retry/recovery, semaphore concurrency control, and comprehensive error handling. Next: Complete PWA integration and comprehensive testing.