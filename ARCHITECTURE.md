# ALFRD - System Architecture

**Automated Ledger & Filing Research Database**

**Current Status:** Phase 1C Complete + PostgreSQL Migration (2025-11-30)

---

## Executive Summary

Personal document management system with AI-powered processing and self-improving classification.

**Tech Stack:**
- **Database:** PostgreSQL 15+ with full-text search (asyncpg connection pooling)
- **OCR:** AWS Textract (95%+ accuracy, $1.50/1000 pages)
- **LLM:** AWS Bedrock (Nova Lite for classification, Claude Sonnet 4 for scoring)
- **API:** FastAPI with asyncio
- **UI:** Ionic React PWA for mobile document capture
- **Deployment:** Docker with supervisord

**Key Features:**
- 5-worker self-improving pipeline with prompt evolution
- State-machine-driven processing (crash-resistant)
- Dynamic document type classification
- Real-time full-text search
- Block-level OCR data preservation for spatial reasoning

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
│  │         Document Processor (5-Worker Pipeline)         │ │
│  │                                                          │ │
│  │  OCRWorker → ClassifierWorker → ClassifierScorerWorker │ │
│  │     ↓              ↓                    ↓               │ │
│  │  AWS Textract   AWS Bedrock      Prompt Evolution      │ │
│  │                                                          │ │
│  │  SummarizerWorker → SummarizerScorerWorker             │ │
│  │     ↓                      ↓                            │ │
│  │  Type-Specific      Prompt Evolution                    │ │
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
    OCRWorker (AWS Textract) → ocr_completed
         ↓
    ClassifierWorker (Bedrock + DB prompts) → classified
         ↓
    ClassifierScorerWorker (evaluate & evolve) → scored_classification
         ↓
    SummarizerWorker (type-specific) → summarized
         ↓
    SummarizerScorerWorker (evaluate & evolve) → completed
```

### Document Status Values
- `pending` - Folder detected in inbox
- `ocr_completed` - Text extracted
- `classified` - Type determined (bill/finance/junk/school/event/generic)
- `scored_classification` - Classifier performance evaluated
- `summarized` - Type-specific summary generated
- `completed` - All processing done
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

### 2. State-Machine-Driven Workers

**Why:**
- All state in database (not in-memory) → crash-resistant
- Workers poll PostgreSQL for documents in specific statuses
- Observable: `SELECT status, COUNT(*) FROM documents GROUP BY status`
- Horizontal scaling: Run multiple worker instances
- No message queues needed for MVP

**Configuration:** See [`shared/config.py`](shared/config.py)

### 3. Self-Improving Prompts

**Architecture:**
- **Classifier prompt:** Single prompt (max 300 words), evolves based on accuracy
- **Summarizer prompts:** One per document type (6 defaults: bill, finance, school, event, junk, generic)
- **Scorer workers:** LLM evaluates its own performance, suggests prompt improvements
- **Versioning:** All prompts tracked with version numbers and performance scores
- **Thresholds:** Min 5 documents before scoring, 0.05 score improvement to update

**Why:**
- System learns from mistakes automatically
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

### 5. MCP Architecture Rule ⚠️

**All document processors MUST:**
- ✅ Call MCP tools only (e.g., `score_classification()`, `summarize_dynamic()`)
- ❌ Never call LLM clients directly (e.g., `bedrock_client.invoke_model()`)

**Why:**
- Consistent prompt management and versioning
- Makes future MCP server transition seamless
- All LLM interactions logged and trackable

---

## Project Structure

```
esec/
├── api-server/              # FastAPI REST API
│   └── src/api_server/db/schema.sql
├── document-processor/      # 5-worker pipeline
│   └── src/document_processor/
│       ├── main.py          # Orchestrator
│       ├── workers.py       # BaseWorker + WorkerPool
│       ├── ocr_worker.py
│       ├── classifier_worker.py
│       ├── summarizer_worker.py
│       ├── scorer_workers.py
│       └── extractors/aws_textract.py
├── mcp-server/              # LLM tools (used as library)
│   └── src/mcp_server/
│       ├── llm/bedrock.py
│       └── tools/           # classify, summarize, score
├── web-ui/                  # Ionic React PWA
├── shared/                  # Shared utilities
│   ├── database.py          # PostgreSQL client (674 lines)
│   ├── config.py
│   └── tests/test_database.py
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
- Document Processor (5 workers)
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

## Current Status (2025-11-30)

### ✅ Completed (Phase 1C)
- PostgreSQL database with asyncpg
- 5-worker self-improving pipeline
- AWS Textract OCR with block preservation
- Dynamic document type classification
- Prompt evolution system
- API server with 5 endpoints
- Ionic React PWA (basic structure)
- Docker deployment
- 20/20 tests passing

### ⏳ In Progress (Phase 2B)
- PWA camera to API integration
- Real-time status updates in UI
- End-to-end mobile workflow testing

### ❌ Planned (Phase 3)
- Hierarchical summaries (weekly → monthly → yearly)
- Financial tracking with CSV exports
- Analytics dashboard
- Advanced search and filtering

---

## References

- **Getting Started:** [`START_HERE.md`](START_HERE.md)
- **Current Status:** [`STATUS.md`](STATUS.md) (formerly PROGRESS.md + IMPLEMENTATION_PLAN.md)
- **Worker Design:** [`DOCUMENT_PROCESSING_DESIGN.md`](DOCUMENT_PROCESSING_DESIGN.md)
- **Database Schema:** [`api-server/src/api_server/db/schema.sql`](api-server/src/api_server/db/schema.sql)

---

**Last Updated:** 2025-11-30