# ALFRD - Current Status & Roadmap

**Last Updated:** 2025-11-30 (PostgreSQL Migration Complete)

**Current Phase:** Phase 1C Complete ✅

---

## What's Working ✅

### Phase 1C: Self-Improving Pipeline (Complete)

1. **5-Worker Self-Improving Pipeline**
   - OCRWorker → ClassifierWorker → ClassifierScorerWorker → SummarizerWorker → SummarizerScorerWorker
   - State-machine-driven polling (crash-resistant)
   - Configurable concurrency per worker type

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

6. **API Server**
   - 5 REST endpoints (health, documents list/detail/file, upload-image)
   - FastAPI with asyncio
   - OpenAPI documentation at `/docs`

7. **Ionic React PWA**
   - 3 pages: CapturePage, DocumentsPage, DocumentDetailPage
   - Basic structure ready
   - Needs integration with API

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

### Phase 2B: PWA Integration (In Progress)

1. **Camera to API Upload Flow**
   - ⏳ Test camera capture in PWA
   - ⏳ Wire upload to `/api/v1/upload-image`
   - ⏳ Handle upload progress/errors

2. **Real-Time Status Updates**
   - ⏳ Poll API for document status
   - ⏳ Show pipeline progress in UI
   - ⏳ Refresh document list after upload

3. **End-to-End Testing**
   - ⏳ Photo → Upload → Process → Classify → Summarize → View
   - ⏳ Error handling and edge cases

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

**Lines of Code:** ~5,700+ lines
- Document Processor: ~800 lines (core)
- Worker Infrastructure: ~1,700 lines (5 workers + scorers)
- MCP Server: ~400 lines (tools + Bedrock client)
- API Server: ~452 lines
- Web UI: ~100+ lines
- Database Layer: ~674 lines (shared/database.py)
- Tests: ~850 lines
- Helper Scripts: ~750 lines
- Database Schema: ~246 lines (PostgreSQL)

**Test Coverage:** 20/20 tests passing (100% database module)

**Test Results (samples/test-pipeline.sh):**
- ✅ OCR: 98.47% confidence (AWS Textract)
- ✅ Classification: 95% confidence as "bill"
- ✅ Prompt Evolution: Classifier v1→v2 (score: 0.85), Bill Summarizer v1→v2 (score: 0.85)
- ✅ Full Pipeline: pending → completed (all 5 workers)

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

### State-Machine-Driven Workers (2024-11) ✅

**Decision:** All state in PostgreSQL, workers poll database

**Rationale:**
- Crash-resistant (resume from DB state)
- Observable (query DB for status)
- No message queue needed for MVP
- Horizontal scaling (run multiple workers)

**Configuration:** `shared/config.py`
- `ocr_workers: int = 3` (AWS Textract TPS limit)
- `classifier_workers: int = 5` (Bedrock concurrency)
- Poll intervals: 2-5 seconds per worker type

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
1. Complete PWA camera to API upload flow
2. Add real-time document status polling in UI
3. Test end-to-end mobile workflow
4. Add error handling and loading states
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
├── document-processor/      # 5-worker pipeline
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
    ├── ARCHITECTURE.md     # System design
    ├── STATUS.md           # This file
    ├── DOCUMENT_PROCESSING_DESIGN.md
    ├── START_HERE.md       # User guide
    └── README.md           # Project overview
```

---

## Recent Changes (2025-11-30)

### PostgreSQL Migration
- PostgreSQL 15 with asyncpg connection pooling
- Added asyncpg connection pooling
- Implemented full-text search with GIN indexes
- Created 20 comprehensive tests
- Updated all documentation

### Documentation Streamlining
- Reduced ARCHITECTURE.md from 1572 to 369 lines
- Merged PROGRESS.md + IMPLEMENTATION_PLAN.md into STATUS.md
- Removed self-evident code blocks and historical commits
- Focused on design decisions, current status, next steps

---

**Status:** Phase 1C complete! Self-improving prompt architecture with production-ready PostgreSQL database. Next: Complete PWA integration for mobile photo capture.