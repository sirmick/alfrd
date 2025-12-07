# ALFRD - Current Status & Roadmap

**Last Updated:** 2025-12-07 (Prefect 3.x Migration Complete)

**Current Phase:** Phase 2A Complete ✅ + Prefect Migration ✅

---

## What's Working ✅

### Phase 1C: Self-Improving Pipeline (Complete - Migrated to Prefect 3.x)

1. **Prefect 3.x DAG-Based Pipeline**
   - OCR Task → Classify Task → Score Classification Task → Summarize Task → Score Summary Task → File Task → Complete Task
   - DAG-based workflow with explicit dependencies
   - Rate limiting for AWS APIs (3 Textract, 5 Bedrock, 2 file-gen)
   - PostgreSQL advisory locks for prompt evolution
   - Series-based automatic filing
   - File collection summaries
   - Prefect UI at http://0.0.0.0:4200 for monitoring

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

4. **Self-Improving Prompts**
   - Classifier prompt evolves based on accuracy (max 300 words)
   - Summarizer prompts (per type) evolve based on quality
   - LLM can suggest NEW document types
   - Performance metrics tracked for each version
   - Min 5 documents before scoring, 0.05 improvement threshold

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

**Lines of Code:** ~7,500+ lines (after removing ~1,500 lines of old worker infrastructure)
- Document Processor: ~900 lines (Prefect flows + tasks)
- Prefect Infrastructure: ~600 lines (3 flows, 7 tasks, locks utility)
- MCP Server: ~600 lines (tools + Bedrock client + series detection)
- API Server: ~1,216 lines (30+ endpoints)
- Web UI: ~706 lines (3 fully functional pages)
- Database Layer: ~1,776 lines (shared/database.py with series/files/tags)
- Tests: ~850 lines
- Helper Scripts: ~750 lines
- Database Schema: ~666 lines (PostgreSQL with series, files, tags)

**Test Coverage:** 20/20 tests passing (100% database module)

**Test Results:**
- ✅ OCR: 98.47% confidence (AWS Textract)
- ✅ Classification: 95% confidence as "bill"
- ✅ Prompt Evolution: Classifier v1→v2 (score: 0.85), Bill Summarizer v1→v2 (score: 0.85)
- ✅ Full Pipeline: pending → ocr_in_progress → classified → summarized → filed → completed
- ✅ Series Detection: Automatic entity and series_type identification
- ✅ File Generation: Collection summaries with aggregated content
- ✅ Prefect Integration: DAG execution with rate limiting and advisory locks

---

## Architecture Decision Record

### PostgreSQL Migration (2025-11-30) ✅

**Decision:** Use PostgreSQL 15+ for production scalability

**Rationale:**
- Production-ready scalability
- Better multi-user support
- asyncpg connection pooling
- Full-text search with GIN indexes
- JSONB for flexible structured data
- Unix socket connections for performance

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

### Prefect 3.x Workflow Orchestration (2025-12) ✅

**Decision:** Migrate from worker polling to Prefect DAG-based workflows

**Rationale:**
- Explicit task dependencies (no polling loops)
- Built-in rate limiting for AWS APIs
- PostgreSQL advisory locks for prompt evolution serialization
- Better observability via Prefect UI
- Crash-resistant with automatic retries
- Horizontal scaling via Prefect deployment

**Configuration:** `shared/config.py` + task decorators
- Rate limits: 3 Textract, 5 Bedrock, 2 file-gen
- Advisory locks: Per-document-type for prompt evolution
- Orchestrator: Monitors DB every 5 seconds for new documents

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
4. **Minimum Scoring Threshold** - Set to 1 for testing; production should use 5+
5. **MCP as Library** - Currently imported directly, not separate server process

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

## Recent Changes (2025-12-07)

### Prefect 3.x Migration (Phase 2A+)
- Migrated from worker polling to Prefect 3.x DAG-based workflows
- Created 7 Prefect tasks replacing worker classes
- Implemented 3 flows: document_flow, file_flow, orchestrator
- Added PostgreSQL advisory locks for per-document-type serialization
- Implemented rate limiting: 3 Textract, 5 Bedrock, 2 file-gen
- Deleted ~1,500 lines of old worker infrastructure
- Fixed multiple bugs during testing (imports, status transitions, file generation)
- Prefect UI available at http://0.0.0.0:4200
- Updated all documentation to reflect Prefect architecture
- Deleted migration planning documents (WORKFLOW_REFACTORING_PLAN.md, etc.)

---

**Status:** Phase 2A complete + Prefect migration! DAG-based pipeline with rate limiting, advisory locks, and Prefect UI monitoring. Next: Complete PWA integration and comprehensive testing.