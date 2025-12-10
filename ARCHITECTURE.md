# ALFRD - System Architecture

**Automated Ledger & Filing Research Database**

**Current Status:** Phase 1C Complete + PostgreSQL Migration (2025-12-10)

---

## Executive Summary

Personal document management system with AI-powered processing and self-improving classification.

**Tech Stack:**
- **Database:** PostgreSQL 15+ with full-text search (asyncpg connection pooling)
- **OCR:** AWS Textract (95%+ accuracy, $1.50/1000 pages)
- **LLM:** AWS Bedrock (Nova Lite for classification)
- **API:** FastAPI with asyncio
- **UI:** Ionic React PWA for mobile document capture
- **Orchestration:** Simple asyncio with semaphore-based concurrency
- **Deployment:** Docker with supervisord

**Key Features:**
- Asyncio-based processing pipeline with retry/recovery
- State-machine-driven document flow (crash-resistant)
- Series-based filing with hybrid tag approach
- Dynamic document type classification
- Real-time full-text search
- Block-level OCR data preservation for spatial reasoning
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
│                          └────────┬────────┘                 │
│                                   │                           │
│  ┌───────────────────────────────▼────────────────────────┐ │
│  │    Document Processor (Asyncio Orchestrator)           │ │
│  │                                                          │ │
│  │  OCR Step → Classify Step → Summarize Step → File Step│ │
│  │     ↓            ↓              ↓              ↓        │ │
│  │  Textract    Bedrock LLM   Type-Specific   Series      │ │
│  │              Classification  Summary      Detection     │ │
│  │                                                          │ │
│  │  Background: Score Classification + Score Summary       │ │
│  │              (Fire-and-forget for prompt evolution)     │ │
│  │                                                          │ │
│  │  Recovery: Periodic scan for stuck/failed work         │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Processing Pipeline

### State Machine Flow

```
User uploads folder → pending
         ↓
    OCR Task (AWS Textract) → ocr_in_progress → ocr_completed
         ↓
    Classify Task (Bedrock + DB prompts) → classified
         ↓
    Score Classification Task (evaluate & evolve) → scored_classification
         ↓
    Summarize Task (type-specific) → summarized
         ↓
    Score Summary Task (evaluate & evolve) → scored_summary
         ↓
    File Task (series detection & tagging) → filed
         ↓
    Complete Task (final status update) → completed
```

### Document Status Values
- `pending` - Folder detected in inbox
- `ocr_completed` - Text extracted
- `classified` - Type determined (utility_bill/insurance/education/etc.)
- `scored_classification` - Classifier performance evaluated
- `summarized` - Type-specific summary generated
- `scored_summary` - Summarizer performance evaluated
- `filed` - Added to series and tagged
- `completed` - All processing done (file summaries generated)
- `failed` - Error at any stage

---

## Key Design Decisions

### 1. PostgreSQL (Production Database)

**Why:**
- Production-ready scalability
- asyncpg connection pooling (5-20 connections)
- Full-text search with GIN indexes on TSVECTOR
- JSONB for flexible structured data with indexing
- Better multi-user support
- Unix socket connections for local dev performance

**Schema Highlights:**
- `documents` - Core metadata + extracted text + JSONB structured data
- `prompts` - Versioned classifier/summarizer prompts
- `document_types` - Dynamic type registry (LLM can add new types)
- `classification_suggestions` - LLM-suggested types for review
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
- `prefect_max_document_flows: int = 5` - Max documents processing simultaneously
- `prefect_max_file_flows: int = 2` - Max files generating simultaneously

**Recovery Mechanism:**
- Periodic scan every 5 minutes for stuck work
- Automatic retry with exponential backoff
- Max 3 retries per document/file
- 30-minute timeout for stale work detection

### 3. Self-Improving Prompts (Currently Disabled for Testing)

**Architecture:**
- **Classifier prompt:** Single prompt (max 300 words), evolves based on accuracy
- **Summarizer prompts:** One per document type (6 defaults: bill, finance, school, event, junk, generic)
- **Scorer workers:** LLM evaluates its own performance, suggests prompt improvements
- **Versioning:** All prompts tracked with version numbers and performance scores
- **Thresholds:** Min 5 documents before scoring, 0.05 score improvement to update

**Current Status:**
- Implemented but disabled for testing: `prompt_update_threshold = 999.0`
- Set to `1` minimum documents for testing (production should use 5+)
- To enable: Set `prompt_update_threshold = 0.05` in config

**Why:**
- System can learn from mistakes automatically
- No hardcoded handlers - all prompt-driven
- Generic architecture works for any document type
- LLM can suggest NEW document types not in initial list

### 4. AWS Textract OCR

**Why:**
- 95%+ accuracy (better than Claude Vision for documents)
- Block-level preservation (PAGE, LINE, WORD with bounding boxes)
- Spatial reasoning: LLM sees text layout for better understanding
- Cost-effective: $1.50/1000 pages
- Supports tables and forms

**Output Format:**
```json
{
  "full_text": "Combined text from all pages",
  "blocks_by_document": [
    {
      "file": "page1.jpg",
      "blocks": {
        "PAGE": [...],
        "LINE": [...bounding boxes...],
        "WORD": [...]
      }
    }
  ],
  "document_count": 2,
  "avg_confidence": 0.95
}
```

### 5. MCP Tools as Library Functions

**MCP Implementation:**
- MCP tools are Python functions in `mcp-server/src/mcp_server/tools/`
- No separate server process required
- Functions imported and called directly by orchestrator
- `mcp-server/main.py` explicitly states: "No separate MCP server process needed"

**Why:**
- Simpler deployment - no additional service to manage
- Direct function calls - lower latency
- Easier to debug and test
- Future: Can be exposed as MCP server if needed

---

## Project Structure

```
esec/
├── api-server/              # FastAPI REST API
│   └── src/api_server/
│       ├── main.py          # 30+ endpoints including /flatten
│       └── db/schema.sql
├── document-processor/      # Prefect 3.x pipeline
│   └── src/document_processor/
│       ├── main.py          # Prefect orchestrator entry point
│       ├── flows/
│       │   ├── document_flow.py    # Main processing DAG
│       │   ├── file_flow.py        # File generation flow
│       │   └── orchestrator.py     # DB monitoring orchestrator
│       ├── tasks/
│       │   └── document_tasks.py   # All 7 Prefect tasks
│       ├── utils/
│       │   └── locks.py            # PostgreSQL advisory locks
│       └── extractors/aws_textract.py
├── mcp-server/              # LLM tools (used as library)
│   └── src/mcp_server/
│       ├── llm/bedrock.py
│       └── tools/           # classify, summarize, score
├── web-ui/                  # Ionic React PWA
│   └── src/
│       ├── components/DataTable.jsx  # Flattened data display
│       └── pages/FileDetailPage.jsx  # Shows flattened table
├── shared/                  # Shared utilities
│   ├── database.py          # PostgreSQL client (1776 lines)
│   ├── json_flattener.py    # JSONB to DataFrame conversion (428 lines)
│   ├── config.py
│   └── tests/
│       ├── test_database.py
│       └── test_json_flattener.py  # 458 lines, 25+ tests
├── scripts/
│   ├── analyze-file-data    # CLI for data extraction & CSV export
│   └── ...
├── docs/
│   └── JSON_FLATTENING.md   # Complete flattening documentation
├── docker/                  # Deployment
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── supervisord.conf
└── data/                    # Runtime (not in git)
    ├── inbox/              # Input folders
    ├── documents/          # Processed output
    └── postgres/           # PostgreSQL data (Docker)
```

---

## Database Schema (PostgreSQL)

### Core Tables

**documents** - Main document metadata
```sql
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename VARCHAR NOT NULL,
    status VARCHAR NOT NULL CHECK (status IN (
        'pending', 'ocr_completed', 'classified', 
        'scored_classification', 'summarized', 'completed', 'failed'
    )),
    document_type VARCHAR,  -- bill/finance/school/event/junk/generic
    extracted_text TEXT,
    extracted_text_tsv TSVECTOR,  -- Full-text search
    structured_data JSONB,         -- Type-specific extracted data
    tags JSONB,                    -- User tags + auto-tags
    folder_metadata JSONB,         -- meta.json content
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_fts ON documents USING GIN(extracted_text_tsv);
CREATE INDEX idx_documents_structured_data ON documents USING GIN(structured_data);
```

**prompts** - Versioned prompts with performance tracking
```sql
CREATE TABLE prompts (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    prompt_type VARCHAR NOT NULL,  -- 'classifier' or 'summarizer'
    document_type VARCHAR,          -- NULL for classifier, type for summarizer
    prompt_text TEXT NOT NULL CHECK (length(prompt_text) <= 1500),
    version INT NOT NULL,
    is_active BOOLEAN DEFAULT TRUE,
    performance_score FLOAT,
    documents_processed INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**document_types** - Dynamic type registry
```sql
CREATE TABLE document_types (
    type_name VARCHAR PRIMARY KEY,
    description TEXT,
    created_by VARCHAR DEFAULT 'system',  -- 'system' or 'llm'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
```

**classification_suggestions** - LLM-suggested new types
```sql
CREATE TABLE classification_suggestions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID REFERENCES documents(id),
    suggested_type VARCHAR NOT NULL,
    confidence FLOAT,
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed BOOLEAN DEFAULT FALSE
);
```

---

## Deployment

### Development (Native)

```bash
# Terminal 1: PostgreSQL
brew services start postgresql@15  # or systemctl start postgresql

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

**Supervisord manages:**
- API Server (port 8000)
- Document Processor (7 workers)
- Web UI (port 5173)
- PostgreSQL (via socket or TCP)

See [`docker/supervisord.conf`](docker/supervisord.conf) for process configuration.

---

## API Endpoints

**Base URL:** `http://localhost:8000/api/v1`

- `GET /health` - Health check with DB status
- `GET /documents` - List documents with filters
- `GET /documents/{id}` - Document details
- `GET /documents/{id}/file` - Download original file
- `POST /upload-image` - Upload document image

Full OpenAPI docs: `http://localhost:8000/docs`

---

## Current Status (2025-12-10)

### ✅ Completed (Phase 1C + 2A + 2B)
- PostgreSQL database with asyncpg connection pooling
- Asyncio orchestrator with semaphore-based concurrency control
- Automatic retry and stale work recovery mechanisms
- AWS Textract OCR with block preservation
- Dynamic document type classification
- Series-based filing with hybrid tag approach
- File generation with collection summaries
- API server with 30+ endpoints
- Ionic React PWA with data visualization
- Docker deployment
- Full database schema with series, files, and tags
- **JSON flattening system** - Extract nested JSONB to pandas DataFrames
- **CLI tool** - `analyze-file-data` for data analysis and CSV export
- **API endpoint** - `/api/v1/files/{file_id}/flatten`
- **UI integration** - DataTable component in file detail view
- **Multiple array strategies** - flatten, json, first, count
- **Comprehensive tests** - 25+ test cases for all scenarios

### ⏳ In Progress (Phase 2C)
- Real-time status updates in UI
- End-to-end mobile workflow testing

### ❌ Planned (Phase 3)
- Hierarchical summaries (weekly → monthly → yearly)
- Financial tracking with advanced analytics
- Analytics dashboard with charts
- Advanced search and filtering

---

## Series-Based Filing System

### Overview
Documents are automatically organized into **series** - recurring collections of related documents from the same entity (e.g., monthly PG&E bills, State Farm insurance statements).

### How It Works

**File Task Process:**
1. Triggered for documents with status='scored_summary'
2. Calls `detect_series` MCP tool to analyze document and identify:
   - Entity name (e.g., "Pacific Gas & Electric")
   - Series type (e.g., "monthly_utility_bill")
   - Frequency (monthly/quarterly/annual)
   - Key metadata (account numbers, policy info)
3. Creates or finds existing series in database
4. Adds document to series via junction table
5. Creates series-specific tag (e.g., "series:pge")
6. Applies tag to document
7. Creates file based on series tag
8. Updates status to 'filed'

**Hybrid Approach:**
- **Series entities** track recurring relationships and metadata
- **Tags** provide flexible, user-friendly organization
- **Files** aggregate documents with matching tags into collections

**Database Tables:**
- `series` - Series entities with metadata
- `document_series` - Many-to-many junction table
- `tags` - Unique tags with usage statistics
- `document_tags` - Document-tag associations
- `files` - Auto-generated document collections
- `file_documents` - File-document associations

### File Generation Flow
Generates summaries for file collections:
1. Triggered for files with status='pending' or 'outdated'
2. Fetches all documents matching file's tags
3. Builds aggregated content (reverse chronological)
4. Calls `summarize_file` MCP tool
5. Updates file with summary and metadata
6. Sets status='generated'

**File Types:**
- **LLM-generated**: Created automatically by file task
- **User-created**: Manual file creation via API

## Prompt Management System

### Self-Improving Prompts
All LLM interactions use database-stored prompts that evolve based on performance:

**Prompt Types:**
- `classifier` - Document type classification (single prompt)
- `summarizer` - Type-specific summaries (one per document type)
- `file_summarizer` - File collection summaries
- `series_detector` - Series identification

**Evolution Process:**
1. Scorer workers evaluate LLM outputs
2. Generate performance metrics and scores
3. Suggest prompt improvements
4. New prompt version created if score improves by ≥0.05
5. Old versions archived (is_active=false)

**Thresholds:**
- Minimum 5 documents before scoring
- Score improvement of 0.05 to update prompt
- All versions retained for analysis

## References

- **Getting Started:** [`START_HERE.md`](START_HERE.md)
- **Current Status:** [`STATUS.md`](STATUS.md)
- **Database Schema:** [`api-server/src/api_server/db/schema.sql`](api-server/src/api_server/db/schema.sql)

---

**Last Updated:** 2025-12-10