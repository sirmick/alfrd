# ALFRD - System Architecture

**Automated Ledger & Filing Research Database**

**Current Status:** Phase 1C Complete + Series Schema Stability (2025-12-12)

---

## Executive Summary

Personal document management system with AI-powered processing, self-improving classification, and series-specific extraction for schema consistency.

**Tech Stack:**
- **Database:** PostgreSQL 15+ with full-text search (asyncpg connection pooling)
- **OCR:** AWS Textract (95%+ accuracy, $1.50/1000 pages)
- **LLM:** AWS Bedrock (Nova Lite for classification)
- **API:** FastAPI with asyncio
- **UI:** Ionic React PWA for mobile document capture
- **Orchestration:** Asyncio with semaphore-based concurrency
- **Deployment:** Docker with supervisord

**Key Features:**
- Asyncio-based processing pipeline with retry/recovery
- State-machine-driven document flow (crash-resistant)
- **Series-specific prompts with schema consistency**
- **PostgreSQL advisory locks for race condition prevention**
- **Event logging for debugging and audit trails**
- Series-based filing with hybrid tag approach
- Dynamic document type classification
- Real-time full-text search
- Automatic stale work recovery (every 5 minutes)

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                   ALFRD System Architecture                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌──────────────┐         ┌──────────────┐                  │
│  │  Web UI      │◄───────►│ API Server   │                  │
│  │  (Ionic PWA) │  REST   │ (FastAPI)    │                  │
│  └──────────────┘         └──────┬───────┘                  │
│                                   │                           │
│                          ┌────────▼────────┐                 │
│                          │  PostgreSQL 15  │                 │
│                          │  + Full-Text    │                 │
│                          │  + Advisory     │                 │
│                          │    Locks        │                 │
│                          └────────┬────────┘                 │
│                                   │                           │
│  ┌───────────────────────────────▼────────────────────────┐ │
│  │    Document Processor (Asyncio Orchestrator)           │ │
│  │                                                          │ │
│  │  OCR → Classify → Summarize → File → Series Extract   │ │
│  │    ↓       ↓          ↓         ↓          ↓           │ │
│  │  Textract  Bedrock  Generic   Series    Series        │ │
│  │            LLM      Summary   Detect    Prompt        │ │
│  │                                                          │ │
│  │  Background Tasks:                                       │ │
│  │  - Score Classification (prompt evolution)              │ │
│  │  - Score Summary (prompt evolution)                     │ │
│  │  - Score Series Extraction (prompt evolution)           │ │
│  │                                                          │ │
│  │  Series Regeneration:                                    │ │
│  │  - Triggered when series prompt improves                │ │
│  │  - Updates all documents in series                      │ │
│  │                                                          │ │
│  │  Recovery: Periodic scan for stuck/failed work         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Document & Series Hierarchy

ALFRD organizes documents into a hierarchy:

```
Documents → Series → Files
    │          │        │
    │          │        └─ Aggregated summaries by tag
    │          └─ Recurring collections (e.g., "PG&E Monthly Bills")
    └─ Individual scanned documents
```

### Series Concept

A **Series** represents recurring documents from the same entity:
- "Pacific Gas & Electric" monthly utility bills
- "State Farm" quarterly insurance statements
- "Bay Area Properties LLC" monthly rent receipts

Each series has:
- **Entity**: The organization (e.g., "Pacific Gas & Electric")
- **Series Type**: The document pattern (e.g., "monthly_utility_bill")
- **Active Prompt**: Series-specific extraction prompt
- **Schema**: Consistent field names across all documents

### Why Series Matter

**Problem Solved:** Schema Drift

Without series prompts, documents processed at different times would have inconsistent field names:
- Document 1: `usage_kwh: 450`
- Document 2: `electric_usage: 475`
- Document 3: `total_kwh: 420`

**Solution:** Each series gets ONE prompt that extracts with consistent field names:
- All documents: `usage_kwh: 450, 475, 420...`

This enables clean data tables, aggregation, and financial tracking.

---

## Processing Pipeline

### Complete Document Flow

```
User uploads folder → pending
         ↓
    OCR Step (AWS Textract) → ocr_completed
         ↓
    Classify Step (Bedrock + DB prompts) → classified
         ↓
    [Background] Score Classification → scored_classification
         ↓
    Summarize Step (Generic, type-specific) → summarized
         ↓
    [Background] Score Summary → scored_summary
         ↓
    File Step (Series detection & tagging) → filed
         ↓
    Series Summarize Step (Series-specific extraction) → series_summarized
         ↓
    [Background] Score Series Extraction
         ↓
    Complete Task (final status update) → completed
```

### Document Status Values

- `pending` - Folder detected in inbox
- `ocr_completed` - Text extracted via AWS Textract
- `classified` - Document type determined (utility_bill/insurance/etc.)
- `scored_classification` - Classifier performance evaluated
- `summarized` - Generic summary generated
- `scored_summary` - Summarizer performance evaluated
- `filed` - Added to series and tagged
- `series_summarized` - Series-specific extraction complete
- `completed` - All processing done
- `failed` - Error at any stage

---

## Series-Specific Prompt System

### The Schema Consistency Problem

Generic prompts evolve over time based on scoring feedback. This causes **schema drift**:

```
Month 1: Prompt extracts "total_amount"
Month 2: Evolved prompt extracts "amount_due"
Month 3: Further evolved to "total_due"
```

Result: 12 monthly bills with 12 different field names = unusable data tables.

### The Solution: Series Prompts

Each series gets its own prompt that:
1. Is created from the first document in the series
2. Enforces strict field naming
3. Is used for ALL subsequent documents in that series
4. Evolves as a unit (all documents regenerated together)

### Series Prompt Workflow

**First Document in Series:**
```
1. Document processed through generic pipeline
2. File step detects/creates series "PG&E Monthly Bills"
3. Series has NO active_prompt_id
4. WITH LOCK: Create series prompt from generic extraction
5. Store prompt with schema definition
6. Link prompt to series (active_prompt_id)
7. Extract document with series prompt
8. Store in structured_data field
```

**Subsequent Documents:**
```
1. Document processed through generic pipeline
2. File step assigns to existing series
3. Series HAS active_prompt_id
4. Get existing series prompt
5. Extract document with SAME prompt
6. All documents have IDENTICAL field names!
```

### PostgreSQL Advisory Locks

**Problem:** Multiple concurrent documents could create duplicate series prompts.

**Solution:** PostgreSQL advisory locks ensure only ONE task creates the prompt:

```python
async with series_prompt_lock(db, series_id):
    # Double-check after acquiring lock
    series = await db.get_series(series_id)
    if not series.get('active_prompt_id'):
        # We're first - create the prompt
        prompt = await create_series_prompt(...)
        await db.update_series(series_id, active_prompt_id=prompt['id'])
```

**Lock Types:**
- `document_type_lock`: Prevents concurrent processing of same document type
- `series_prompt_lock`: Prevents concurrent series prompt creation

**Event Logging:**
All lock operations are logged:
- `lock_requested` - Task wants the lock
- `lock_acquired` - Lock granted
- `lock_released` - Lock freed
- `lock_timeout` - Failed to acquire within timeout

### Series Regeneration

When a series prompt improves beyond threshold:

1. New prompt version created
2. Old prompt deactivated
3. Series marked with `regeneration_pending = TRUE`
4. After all documents processed:
   - Find all documents in series
   - Skip those already using latest prompt
   - Re-extract with new prompt (NO scoring - avoids infinite loop)
   - Mark regeneration complete

**Key Design:** Regeneration uses a dedicated function that bypasses scoring to prevent infinite loops.

---

## Event Logging System

### Purpose

Comprehensive logging for:
- Debugging processing issues
- Audit trail for LLM calls
- Performance monitoring
- Lock contention analysis

### Event Categories

| Category | Description | Examples |
|----------|-------------|----------|
| `state_transition` | Document status changes | pending → ocr_completed |
| `llm_request` | LLM API calls | classify, summarize, score |
| `processing` | Processing milestones | ocr_complete, regeneration_started |
| `error` | Failures and exceptions | extraction_failed, lock_timeout |
| `user_action` | Manual interventions | manual_reprocess |

### Event Fields

```sql
CREATE TABLE events (
    id UUID PRIMARY KEY,
    event_category VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    document_id UUID,           -- Which document
    file_id UUID,               -- Which file
    series_id UUID,             -- Which series
    task_name VARCHAR,          -- Which task
    old_status VARCHAR,         -- For state transitions
    new_status VARCHAR,
    llm_model VARCHAR,          -- For LLM requests
    llm_prompt_text TEXT,
    llm_response_text TEXT,
    llm_request_tokens INTEGER,
    llm_response_tokens INTEGER,
    llm_latency_ms INTEGER,
    llm_cost_usd FLOAT,
    error_message TEXT,         -- For errors
    details JSONB,              -- Additional context
    created_at TIMESTAMP
);
```

### Viewing Events

```bash
# View events for a document
./scripts/view-events <document-uuid>

# View events for a series
./scripts/view-events --series <series-uuid>

# Filter by category
./scripts/view-events <uuid> --category llm_request

# Show full prompt/response text
./scripts/view-events <uuid> --full

# JSON output
./scripts/view-events <uuid> --json
```

---

## Key Design Decisions

### 1. PostgreSQL (Production Database)

**Why:**
- Production-ready scalability
- asyncpg connection pooling (5-20 connections)
- Full-text search with GIN indexes
- JSONB for flexible structured data
- **Advisory locks for distributed coordination**
- Unix socket connections for local dev performance

**Schema Highlights:**
- `documents` - Core metadata + extracted text + structured data
- `series` - Document series with active_prompt_id
- `prompts` - Versioned prompts including series_summarizer type
- `events` - Comprehensive event log
- Full schema: [`api-server/src/api_server/db/schema.sql`](api-server/src/api_server/db/schema.sql)

### 2. Asyncio Orchestration with Semaphores

**Why:**
- Simple, lightweight orchestration without external dependencies
- Semaphore-based concurrency control for AWS API rate limiting
- Crash-resistant with retry logic and stale work recovery
- All state in database (not in-memory)
- Easy to understand and debug

**Configuration:** See [`shared/config.py`](shared/config.py)
- `prefect_textract_workers: int = 3` - Max concurrent Textract calls
- `prefect_bedrock_workers: int = 5` - Max concurrent Bedrock calls
- `prefect_max_document_flows: int = 5` - Max documents processing

**Recovery Mechanism:**
- Periodic scan every 5 minutes for stuck work
- Automatic retry with exponential backoff
- Max 3 retries per document/file
- 30-minute timeout for stale work detection

### 3. Self-Improving Prompts

**Architecture:**
- **Classifier prompt:** Single prompt that evolves based on accuracy
- **Summarizer prompts:** One per document type (generic extraction)
- **Series prompts:** One per series (schema-consistent extraction)
- **Scorer workers:** LLM evaluates its own performance

**Thresholds:**
- Min 1 document for testing (production should use 5+)
- Score improvement of 0.05 to trigger evolution
- Series prompts: evolution triggers regeneration of entire series

### 4. Dual Extraction Strategy

**Why Two Extractions:**
- `structured_data_generic`: Generic prompt extraction (type-specific)
- `structured_data`: Series prompt extraction (entity-specific, consistent schema)

**Benefits:**
- Generic extraction works for all documents
- Series extraction ensures consistency within series
- Fallback if series extraction fails
- Can compare quality between approaches

### 5. AWS Textract OCR

**Why:**
- 95%+ accuracy (better than Claude Vision for documents)
- Block-level preservation (PAGE, LINE, WORD with bounding boxes)
- Spatial reasoning: LLM sees text layout
- Cost-effective: $1.50/1000 pages

### 6. MCP Tools as Library Functions

**Implementation:**
- MCP tools are Python functions in `mcp-server/src/mcp_server/tools/`
- No separate server process required
- Functions imported and called directly by orchestrator

**Why:**
- Simpler deployment
- Lower latency
- Easier to debug and test

---

## Project Structure

```
esec/
├── api-server/              # FastAPI REST API
│   └── src/api_server/
│       ├── main.py          # 30+ endpoints
│       └── db/schema.sql    # PostgreSQL schema
├── document-processor/      # Asyncio processing pipeline
│   └── src/document_processor/
│       ├── main.py          # Entry point
│       ├── orchestrator.py  # SimpleOrchestrator with recovery
│       ├── tasks/
│       │   ├── document_tasks.py    # All processing steps
│       │   └── series_regeneration.py  # Series regeneration worker
│       ├── utils/
│       │   └── locks.py     # PostgreSQL advisory locks
│       └── extractors/
│           └── aws_textract.py
├── mcp-server/              # LLM tools (used as library)
│   └── src/mcp_server/
│       ├── llm/bedrock.py
│       └── tools/
│           ├── classify.py
│           ├── summarize.py
│           ├── summarize_series.py  # Series-specific extraction
│           ├── detect_series.py
│           └── score_performance.py
├── web-ui/                  # Ionic React PWA
│   └── src/
│       ├── components/DataTable.jsx
│       └── pages/
├── shared/                  # Shared utilities
│   ├── database.py          # PostgreSQL client
│   ├── event_logger.py      # Event logging utilities
│   ├── config.py
│   └── types.py
├── scripts/
│   ├── create-alfrd-db      # Database initialization
│   ├── view-events          # Event log viewer
│   └── ...
├── docker/                  # Deployment
│   ├── Dockerfile
│   └── docker-compose.yml
└── data/                    # Runtime (not in git)
    ├── inbox/              # Input folders
    ├── documents/          # Processed output
    └── postgres/           # PostgreSQL data
```

---

## Database Schema Overview

### Core Tables

**documents** - Individual document records
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY,
    filename VARCHAR NOT NULL,
    status VARCHAR NOT NULL,
    document_type VARCHAR,
    extracted_text TEXT,
    structured_data JSONB,          -- Series-specific extraction
    structured_data_generic JSONB,  -- Generic extraction
    series_prompt_id UUID,          -- Which series prompt used
    extraction_method VARCHAR,      -- 'generic' or 'series'
    -- ... other fields
);
```

**series** - Document series (recurring collections)
```sql
CREATE TABLE series (
    id UUID PRIMARY KEY,
    title VARCHAR NOT NULL,
    entity VARCHAR NOT NULL,
    series_type VARCHAR NOT NULL,
    active_prompt_id UUID,          -- Current series prompt
    regeneration_pending BOOLEAN,   -- Needs regeneration
    -- ... other fields
);
```

**prompts** - All prompt types including series_summarizer
```sql
CREATE TABLE prompts (
    id UUID PRIMARY KEY,
    prompt_type VARCHAR NOT NULL,   -- 'series_summarizer' for series
    document_type VARCHAR,          -- Series ID for series prompts
    prompt_text TEXT NOT NULL,
    version INTEGER,
    is_active BOOLEAN,
    performance_score FLOAT,
    performance_metrics JSONB,      -- Includes schema_definition
    -- ... other fields
);
```

**events** - Processing event log
```sql
CREATE TABLE events (
    id UUID PRIMARY KEY,
    event_category VARCHAR NOT NULL,
    event_type VARCHAR NOT NULL,
    document_id UUID,
    series_id UUID,
    -- ... LLM tracking fields
    details JSONB,
    created_at TIMESTAMP
);
```

---

## API Endpoints

**Base URL:** `http://localhost:8000/api/v1`

- `GET /health` - Health check with DB status
- `GET /documents` - List documents with filters
- `GET /documents/{id}` - Document details
- `GET /series` - List all series
- `GET /series/{id}` - Series details with documents
- `GET /files/{id}` - File with aggregated documents
- `POST /upload-image` - Upload document image

Full OpenAPI docs: `http://localhost:8000/docs`

---

## Deployment

### Development (Native)

```bash
# Terminal 1: PostgreSQL
brew services start postgresql@15

# Terminal 2: API Server
./scripts/start-api

# Terminal 3: Document Processor
./scripts/start-processor

# Terminal 4: Web UI
./scripts/start-webui
```

### Docker (Single Container)

```bash
docker-compose -f docker/docker-compose.yml up -d
```

---

## References

- **Getting Started:** [`START_HERE.md`](START_HERE.md)
- **Current Status:** [`STATUS.md`](STATUS.md)
- **Database Schema:** [`api-server/src/api_server/db/schema.sql`](api-server/src/api_server/db/schema.sql)

---

**Last Updated:** 2025-12-12
