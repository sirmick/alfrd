# ALFRD - Architecture Plan
**Automated Ledger & Filing Research Database**

## Executive Summary

A personal document management system with AI-powered processing, structured storage, and hierarchical summarization. The system processes documents (photos, PDFs, emails) through LLM analysis, extracts structured data, and maintains running summaries organized by category (bills, taxes, receipts, insurance).

**Key Design Principles:**
- Isolated per-user Docker containers for data privacy
- Async document processing pipeline
- Multi-LLM provider support (Claude API, OpenRouter, local models)
- Offline-first web UI with native mobile path
- MCP server for Claude Desktop integration
- Modular microservice architecture within containers

---

## System Architecture Overview

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      PRODUCTION DEPLOYMENT                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────┐              ┌────────────────────────┐  │
│  │   Web UI Server  │◄────REST────►│   API Gateway Server   │  │
│  │   (Multi-User)   │              │   (Route to users)     │  │
│  │   React+Capacitor│              │      FastAPI           │  │
│  └──────────────────┘              └───────────┬────────────┘  │
│                                                 │                │
│                                                 │ HTTP           │
│                                    ┌────────────▼────────────┐  │
│                                    │  Per-User Container 1    │  │
│                                    │  ┌────────────────────┐ │  │
│                                    │  │ API Server         │ │  │
│                                    │  │ (FastAPI)          │ │  │
│                                    │  └─────────┬──────────┘ │  │
│                                    │            │            │  │
│                                    │  ┌─────────▼──────────┐ │  │
│                                    │  │ MCP Server         │ │  │
│                                    │  │ (LLM Integration)  │ │  │
│                                    │  └────────────────────┘ │  │
│                                    │                          │  │
│                                    │  ┌────────────────────┐ │  │
│                                    │  │ Doc Processor      │ │  │
│                                    │  │ (Watchdog+Batch)   │ │  │
│                                    │  └────────────────────┘ │  │
│                                    │                          │  │
│                                    │  ┌────────────────────┐ │  │
│                                    │  │ DuckDB + Documents │ │  │
│                                    │  │ (Filesystem)       │ │  │
│                                    │  └────────────────────┘ │  │
│                                    └──────────────────────────┘  │
│                                                                   │
│                                    ┌──────────────────────────┐  │
│                                    │  Per-User Container N    │  │
│                                    │  (Same structure)        │  │
│                                    └──────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                     DEVELOPMENT/MVP DEPLOYMENT                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │              Single Docker Container                       │  │
│  │                                                            │  │
│  │  ┌──────────────┐         ┌──────────────┐              │  │
│  │  │  Web UI      │◄───────►│ API Server   │              │  │
│  │  │  Server      │  REST   │ (FastAPI)    │              │  │
│  │  │ (FastAPI+React)        └──────┬───────┘              │  │
│  │  └──────────────┘                │                       │  │
│  │                         ┌─────────▼──────────┐           │  │
│  │                         │ MCP Server         │           │  │
│  │                         │ (LLM Integration)  │           │  │
│  │                         └────────────────────┘           │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────┐            │  │
│  │  │ Document Processor (Watchdog + Batch)    │            │  │
│  │  └──────────────────────────────────────────┘            │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────┐            │  │
│  │  │ DuckDB Database + Document Filesystem    │            │  │
│  │  └──────────────────────────────────────────┘            │  │
│  │                                                            │  │
│  │  Managed by: supervisord                                  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

### Component Interaction Flow (Phase 1B - Worker Pool Architecture)

```
┌──────────┐
│  User    │
│  Adds    │──────┐
│Document  │      │
└──────────┘      │
                  ▼
         ┌─────────────────┐
         │ add-document.py │
         │ Creates folder  │
         │ in inbox/       │
         └────────┬─────────┘
                  │
                  ▼
         ┌─────────────────┐
         │ /data/inbox/    │
         │ doc_folder/     │
         │ ├── meta.json   │
         │ └── image.jpg   │
         └────────┬─────────┘
                  │
        ┌─────────▼──────────┐
        │ main.py             │
        │ Scans inbox         │
        │ Creates PENDING     │
        │ DB entries          │
        └─────────┬───────────┘
                  │
                  ▼
         ┌──────────────────────────┐
         │   Worker Pool            │
         │   ┌──────────────────┐   │
         │   │  OCRWorker       │   │
         │   │  PENDING →       │   │
         │   │  OCR_COMPLETED   │   │
         │   └────────┬─────────┘   │
         │            │              │
         │   ┌────────▼─────────┐   │
         │   │ ClassifierWorker │   │
         │   │ OCR_COMPLETED → │   │
         │   │ CLASSIFIED       │   │
         │   └────────┬─────────┘   │
         │            │              │
         │   ┌────────▼─────────┐   │
         │   │ WorkflowWorker   │   │
         │   │ CLASSIFIED →     │   │
         │   │ COMPLETED        │   │
         │   │                  │   │
         │   │ ┌──────────────┐ │   │
         │   │ │BillHandler   │ │   │
         │   │ │FinanceHandler│ │   │
         │   │ │JunkHandler   │ │   │
         │   │ └──────────────┘ │   │
         │   └──────────────────┘   │
         └──────────────────────────┘
                     │
                     │ uses
                     ▼
            ┌───────────────────────────┐
            │   MCP Tools (Library)     │
            │   - classify_document     │
            │   - summarize_bill        │
            │   - BedrockClient         │
            │     (Claude + Nova)       │
            └───────────────────────────┘
                     │
                     ▼
            ┌────────────────────┐
            │   DuckDB           │
            │   - documents      │
            │   - structured_data│
            └────────────────────┘
```

**State Machine Flow:**
```
PENDING → OCR_COMPLETED → CLASSIFIED → COMPLETED
    ↓          ↓              ↓            ↓
  OCRWorker  ClassifierWorker  WorkflowWorker
```

---

## Project Structure

```
alfrd/
├── README.md
├── ARCHITECTURE.md
├── docker/                          # Infrastructure subproject
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── supervisord.conf
│   └── scripts/
│       ├── init-db.sh
│       └── health-check.sh
│
├── document-processor/              # Document processor subproject
│   ├── pyproject.toml
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                 # Entry point - scan and process
│   │   ├── watcher.py              # Watchdog file monitoring
│   │   ├── detector.py             # File type detection
│   │   ├── extractors/
│   │   │   ├── __init__.py
│   │   │   ├── image_ocr.py        # Claude Vision API
│   │   │   ├── pdf.py              # PDF text extraction
│   │   │   └── email.py            # Email parsing (future)
│   │   ├── storage.py              # Save to filesystem + DuckDB
│   │   └── events.py               # Emit events to API server
│   └── tests/
│
├── api-server/                      # API server subproject
│   ├── pyproject.toml
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app entry point
│   │   ├── api/
│   │   │   ├── __init__.py
│   │   │   ├── documents.py        # Document endpoints
│   │   │   ├── summaries.py        # Summary endpoints
│   │   │   ├── query.py            # Query/search endpoints
│   │   │   └── events.py           # Event webhook receiver
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── document_service.py
│   │   │   ├── summary_service.py
│   │   │   └── mcp_client.py       # Talk to MCP server
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── document.py         # Pydantic models
│   │   │   ├── summary.py
│   │   │   └── events.py
│   │   └── db/
│   │       ├── __init__.py
│   │       ├── connection.py       # DuckDB connection pool
│   │       └── schema.sql          # Database schema
│   └── tests/
│
├── mcp-server/                      # MCP server subproject
│   ├── pyproject.toml
│   ├── src/
│   │   ├── __init__.py
│   │   ├── main.py                 # MCP server entry point
│   │   ├── server.py               # MCP server implementation
│   │   ├── tools/
│   │   │   ├── __init__.py
│   │   │   ├── categorize.py       # Categorize document
│   │   │   ├── extract_data.py     # Extract structured data
│   │   │   ├── summarize.py        # Generate summaries
│   │   │   ├── query.py            # Natural language queries
│   │   │   └── analyze.py          # Document analysis
│   │   ├── prompts/
│   │   │   ├── __init__.py
│   │   │   ├── categorization.py   # Prompt templates
│   │   │   ├── extraction.py
│   │   │   └── summarization.py
│   │   └── llm/
│   │       ├── __init__.py
│   │       ├── client.py           # Multi-provider LLM client
│   │       ├── claude.py           # Claude API
│   │       ├── openrouter.py       # OpenRouter
│   │       └── local.py            # Local models (future)
│   └── tests/
│
├── web-ui/                          # Web UI subproject
│   ├── package.json
│   ├── vite.config.js
│   ├── capacitor.config.json        # For native mobile
│   ├── public/
│   ├── src/
│   │   ├── main.jsx                # Entry point
│   │   ├── App.jsx
│   │   ├── api/
│   │   │   ├── client.js           # API client with offline support
│   │   │   └── sync.js             # Background sync
│   │   ├── components/
│   │   │   ├── DocumentList.jsx
│   │   │   ├── DocumentViewer.jsx
│   │   │   ├── SummaryView.jsx
│   │   │   └── Upload.jsx
│   │   ├── pages/
│   │   │   ├── Home.jsx
│   │   │   ├── Documents.jsx
│   │   │   └── Summaries.jsx
│   │   ├── store/
│   │   │   ├── index.js            # State management
│   │   │   └── offline.js          # IndexedDB for offline
│   │   └── styles/
│   └── tests/
│
├── shared/                          # Shared utilities
│   ├── __init__.py
│   ├── config.py                   # Shared configuration
│   ├── types.py                    # Shared type definitions
│   └── constants.py
│
└── data/                            # Runtime data (not in git)
    ├── inbox/                       # Watched folder for new docs
    ├── documents/                   # Processed document storage
    │   ├── 2024/
    │   │   ├── 01/
    │   │   │   ├── raw/            # Original files
    │   │   │   ├── text/           # Extracted text
    │   │   │   └── meta/           # Metadata JSON
    │   │   └── 02/
    │   └── 2025/
    ├── summaries/                   # Generated summaries
    │   ├── weekly/
    │   ├── monthly/
    │   └── yearly/
    └── alfrd.db                      # DuckDB database file
```

---

## Database Schema (DuckDB)

```sql
-- Core documents table
CREATE TABLE documents (
    id UUID PRIMARY KEY DEFAULT uuid(),
    filename VARCHAR NOT NULL,
    original_path VARCHAR NOT NULL,
    file_type VARCHAR NOT NULL,  -- 'image', 'pdf', 'email'
    file_size BIGINT,
    mime_type VARCHAR,
    
    -- Processing status
    status VARCHAR NOT NULL,  -- 'pending', 'processing', 'completed', 'failed'
    processed_at TIMESTAMP,
    error_message VARCHAR,
    
    -- Categorization
    category VARCHAR,  -- 'bill', 'tax', 'receipt', 'insurance', 'advertising', 'other'
    subcategory VARCHAR,
    confidence FLOAT,
    
    -- Extracted structured data
    vendor VARCHAR,
    amount DECIMAL(10, 2),
    currency VARCHAR DEFAULT 'USD',
    due_date DATE,
    issue_date DATE,
    
    -- Storage locations
    raw_document_path VARCHAR,
    extracted_text_path VARCHAR,
    metadata_path VARCHAR,
    
    -- Metadata
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,  -- For multi-user support
    
    -- Full-text search support
    extracted_text TEXT,
    
    -- JSON for flexible data
    structured_data JSON,  -- Additional extracted fields
    tags JSON  -- User tags and auto-tags
);

-- Full-text search index
CREATE INDEX idx_documents_fts ON documents USING FTS (
    filename, vendor, extracted_text, category
);

-- Indexes for common queries
CREATE INDEX idx_documents_category ON documents(category, created_at DESC);
CREATE INDEX idx_documents_due_date ON documents(due_date) WHERE due_date IS NOT NULL;
CREATE INDEX idx_documents_vendor ON documents(vendor);
CREATE INDEX idx_documents_status ON documents(status);
CREATE INDEX idx_documents_user ON documents(user_id, created_at DESC);

-- Summaries table (weekly, monthly, yearly rollups)
CREATE TABLE summaries (
    id UUID PRIMARY KEY DEFAULT uuid(),
    period_type VARCHAR NOT NULL,  -- 'weekly', 'monthly', 'yearly'
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    category VARCHAR,  -- NULL for all categories
    
    -- Summary content
    summary_text TEXT NOT NULL,
    summary_markdown TEXT,  -- Formatted for display
    
    -- Statistics
    document_count INTEGER,
    total_amount DECIMAL(12, 2),
    
    -- Related documents
    document_ids JSON,  -- Array of document UUIDs
    
    -- Metadata
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    llm_model VARCHAR,  -- Which model generated this
    
    -- Allow efficient queries
    UNIQUE(period_type, period_start, period_end, category, user_id)
);

CREATE INDEX idx_summaries_period ON summaries(period_type, period_start DESC);
CREATE INDEX idx_summaries_category ON summaries(category);
CREATE INDEX idx_summaries_user ON summaries(user_id, period_start DESC);

-- Processing queue/events table
CREATE TABLE processing_events (
    id UUID PRIMARY KEY DEFAULT uuid(),
    event_type VARCHAR NOT NULL,  -- 'document_added', 'processing_started', etc.
    document_id UUID REFERENCES documents(id),
    status VARCHAR NOT NULL,  -- 'pending', 'completed', 'failed'
    
    payload JSON,
    error_message VARCHAR,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    processed_at TIMESTAMP,
    
    user_id VARCHAR
);

CREATE INDEX idx_events_status ON processing_events(status, created_at);
CREATE INDEX idx_events_document ON processing_events(document_id);

-- Analytics/insights table (for running totals, trends)
CREATE TABLE analytics (
    id UUID PRIMARY KEY DEFAULT uuid(),
    metric_name VARCHAR NOT NULL,  -- 'monthly_spending', 'bills_due_count', etc.
    category VARCHAR,
    period DATE NOT NULL,
    
    value DECIMAL(12, 2),
    metadata JSON,  -- Additional breakdown
    
    calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR,
    
    UNIQUE(metric_name, category, period, user_id)
);

CREATE INDEX idx_analytics_metric ON analytics(metric_name, period DESC);
CREATE INDEX idx_analytics_user ON analytics(user_id, period DESC);
```

---

## API Endpoints Specification

### Internal Container API (FastAPI)

**Base URL:** `http://localhost:8000` (within container)

#### Document Management

```
POST   /api/v1/documents/upload
  - Upload new document
  - Body: multipart/form-data with file
  - Returns: {document_id, status}

GET    /api/v1/documents
  - List documents with filters
  - Query params: category, date_range, status, limit, offset
  - Returns: {documents: [...], total, page}

GET    /api/v1/documents/{id}
  - Get document details
  - Returns: {document, structured_data, extracted_text}

GET    /api/v1/documents/{id}/download
  - Download original document
  - Returns: file stream

DELETE /api/v1/documents/{id}
  - Delete document (soft delete)
  - Returns: {success: boolean}

POST   /api/v1/documents/{id}/reprocess
  - Reprocess document through pipeline
  - Returns: {status, job_id}
```

#### Search & Query

```
GET    /api/v1/search
  - Full-text search across documents
  - Query params: q (query string), category, date_range
  - Returns: {results: [...], total}

POST   /api/v1/query
  - Natural language query via MCP
  - Body: {query: "What bills are due this week?"}
  - Returns: {answer, sources: [document_ids], query_type}
```

#### Summaries

```
GET    /api/v1/summaries
  - Get summaries by period
  - Query params: period_type (weekly/monthly/yearly), start_date, end_date, category
  - Returns: {summaries: [...]}

GET    /api/v1/summaries/{id}
  - Get specific summary
  - Returns: {summary, documents, statistics}

POST   /api/v1/summaries/generate
  - Manually trigger summary generation
  - Body: {period_type, period_start, period_end, category?}
  - Returns: {summary_id, status}
```

#### Analytics

```
GET    /api/v1/analytics/overview
  - Dashboard overview data
  - Query params: period (week/month/year)
  - Returns: {total_documents, categories, spending, trends}

GET    /api/v1/analytics/spending
  - Spending breakdown
  - Query params: groupBy (category/vendor/month), date_range
  - Returns: {breakdown: [...], total}

GET    /api/v1/analytics/bills
  - Bills analysis
  - Query params: status (upcoming/overdue/paid)
  - Returns: {bills: [...], total_due}
```

#### Events (Internal)

```
POST   /api/v1/events/document-processed
  - Webhook from document processor
  - Body: {document_id, status, extracted_data}
  - Returns: {accepted: true}

GET    /api/v1/events
  - Event log for debugging
  - Query params: event_type, status, limit
  - Returns: {events: [...]}
```

#### Health & Status

```
GET    /api/v1/health
  - Health check
  - Returns: {status: "healthy", services: {...}}

GET    /api/v1/status
  - System status
  - Returns: {processor: {...}, mcp_server: {...}, db: {...}}
```

### Multi-User Web UI Server API

**Base URL:** `http://localhost:3000` (web UI server)

```
POST   /auth/login
  - User authentication
  - Body: {email, password}
  - Returns: {token, user}

POST   /auth/register
  - User registration
  - Body: {email, password, name}
  - Returns: {user, container_info}

GET    /user/profile
  - Get user profile
  - Headers: Authorization: Bearer {token}
  - Returns: {user, container_url}

POST   /user/container/proxy
  - Proxy request to user's container
  - Headers: Authorization: Bearer {token}
  - Body: {method, path, body?, query?}
  - Returns: proxied response from container API
```

---

## MCP Server Tools & Prompting Strategy

### MCP Tools Definition

The MCP server exposes tools that the API server (and Claude Desktop) can call:

```python
# Tool: categorize_document
{
  "name": "categorize_document",
  "description": "Categorize a document based on its content",
  "inputSchema": {
    "type": "object",
    "properties": {
      "document_id": {"type": "string"},
      "extracted_text": {"type": "string"},
      "filename": {"type": "string"}
    },
    "required": ["document_id", "extracted_text"]
  }
}
# Returns: {category, subcategory, confidence, reasoning}

# Tool: extract_structured_data
{
  "name": "extract_structured_data",
  "description": "Extract structured data (vendor, amount, dates, etc.) from document",
  "inputSchema": {
    "type": "object",
    "properties": {
      "document_id": {"type": "string"},
      "extracted_text": {"type": "string"},
      "category": {"type": "string"}
    },
    "required": ["document_id", "extracted_text"]
  }
}
# Returns: {vendor, amount, currency, due_date, issue_date, account_number, ...}

# Tool: generate_summary
{
  "name": "generate_summary",
  "description": "Generate a summary for a period",
  "inputSchema": {
    "type": "object",
    "properties": {
      "period_type": {"type": "string", "enum": ["weekly", "monthly", "yearly"]},
      "period_start": {"type": "string", "format": "date"},
      "period_end": {"type": "string", "format": "date"},
      "category": {"type": "string", "optional": true},
      "document_ids": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["period_type", "period_start", "period_end", "document_ids"]
  }
}
# Returns: {summary_text, summary_markdown, statistics, key_insights}

# Tool: query_documents
{
  "name": "query_documents",
  "description": "Answer natural language questions about documents",
  "inputSchema": {
    "type": "object",
    "properties": {
      "query": {"type": "string"},
      "context": {"type": "object", "optional": true}
    },
    "required": ["query"]
  }
}
# Returns: {answer, confidence, sources: [document_ids], suggested_actions}

# Tool: analyze_spending
{
  "name": "analyze_spending",
  "description": "Analyze spending patterns and trends",
  "inputSchema": {
    "type": "object",
    "properties": {
      "date_range": {"type": "object", "properties": {"start": {...}, "end": {...}}},
      "groupBy": {"type": "string", "enum": ["category", "vendor", "month"]},
      "category": {"type": "string", "optional": true}
    },
    "required": ["date_range"]
  }
}
# Returns: {breakdown: [...], total, trends, insights}
```

### Prompting Strategy

**Categorization Prompt Template:**
```
You are a document classification expert. Categorize this document into one of these categories:
- bill: Utility bills, service invoices, recurring charges
- tax: Tax documents, forms, receipts needed for taxes
- receipt: Purchase receipts, one-time purchases
- insurance: Insurance policies, claims, statements
- advertising: Promotional materials, ads, marketing
- other: Anything else

Document filename: {filename}
Extracted text:
{extracted_text}

Respond with:
1. Primary category (one of the above)
2. Subcategory (more specific, e.g., "electric bill", "credit card statement")
3. Confidence (0-1)
4. Brief reasoning (1-2 sentences)

Format as JSON.
```

**Data Extraction Prompt Template:**
```
Extract structured data from this {category} document.

Extracted text:
{extracted_text}

Extract the following fields (return null if not found):
- vendor: Company or service provider name
- amount: Total amount (numeric only)
- currency: Currency code (default USD)
- due_date: Payment due date (YYYY-MM-DD)
- issue_date: Document issue date (YYYY-MM-DD)
- account_number: Account or invoice number
- payment_method: How to pay (if specified)
- key_items: List of main items/charges (top 3-5)

Additional fields for specific categories:
[Category-specific fields based on document type]

Return as JSON. Be precise with numbers and dates.
```

**Summarization Prompt Template:**
```
Generate a summary for {period_type} period from {period_start} to {period_end}.

Documents in this period:
{document_summaries}

Category: {category or "All"}

Create a summary that includes:
1. Overview: High-level summary (2-3 sentences)
2. Key Statistics:
   - Total documents: {count}
   - Total spending: ${amount}
   - By category breakdown
3. Notable Items: Any unusual or important documents
4. Trends: Compared to previous period (if available)
5. Action Items: Bills due, documents needing attention

Format as markdown for readability.
```

---

## Event System Design

### Event Flow

```python
# Document processor emits events via HTTP POST

# Event payload structure
{
  "event_type": "document_processed",
  "event_id": "uuid",
  "timestamp": "ISO-8601 timestamp",
  "data": {
    "document_id": "uuid",
    "status": "completed" | "failed",
    "extracted_text_path": "/data/documents/2024/01/text/doc123.txt",
    "error": null | "error message"
  }
}

# API Server receives event at POST /api/v1/events/document-processed
# Triggers MCP orchestration workflow
```

### Event Types

```python
EVENT_TYPES = {
    "document_added": "New document detected in inbox",
    "ocr_started": "OCR processing started",
    "ocr_completed": "OCR completed, text extracted",
    "ocr_failed": "OCR failed",
    "document_processed": "Document fully processed and stored",
    "categorization_completed": "Document categorized by MCP",
    "extraction_completed": "Structured data extracted",
    "summary_generated": "Summary generated for period",
    "error": "General error event"
}
```

### Event Handler (API Server)

```python
@app.post("/api/v1/events/document-processed")
async def handle_document_processed(event: ProcessedEvent):
    """
    Orchestrate post-processing workflow:
    1. Call MCP to categorize document
    2. Call MCP to extract structured data
    3. Update document in database
    4. Check if summary needs regeneration
    5. Optionally trigger summary update
    """
    doc_id = event.data.document_id
    
    # Get document details from DB
    document = await get_document(doc_id)
    
    # Call MCP for categorization
    category_result = await mcp_client.call_tool(
        "categorize_document",
        {
            "document_id": doc_id,
            "extracted_text": document.extracted_text,
            "filename": document.filename
        }
    )
    
    # Call MCP for data extraction
    extraction_result = await mcp_client.call_tool(
        "extract_structured_data",
        {
            "document_id": doc_id,
            "extracted_text": document.extracted_text,
            "category": category_result.category
        }
    )
    
    # Update document in DB
    await update_document(doc_id, {
        "category": category_result.category,
        "subcategory": category_result.subcategory,
        "vendor": extraction_result.vendor,
        "amount": extraction_result.amount,
        "due_date": extraction_result.due_date,
        "structured_data": extraction_result,
        "status": "completed"
    })
    
    # Check if we need to update summaries
    await check_and_update_summaries(document)
    
    return {"accepted": true, "document_id": doc_id}
```

---

## Filesystem Structure

```
/data/
├── inbox/                           # Watched folder (new documents)
│   ├── photo_2024_01_15.jpg
│   └── bill.pdf
│
├── documents/                       # Processed documents
│   └── 2024/
│       ├── 01/
│       │   ├── raw/                # Original files (immutable)
│       │   │   ├── doc_uuid1.jpg
│       │   │   └── doc_uuid2.pdf
│       │   ├── text/               # Extracted text
│       │   │   ├── doc_uuid1.txt
│       │   │   └── doc_uuid2.txt
│       │   └── meta/               # Metadata JSON
│       │       ├── doc_uuid1.json  # {category, vendor, amount, ...}
│       │       └── doc_uuid2.json
│       └── 02/
│
├── summaries/                       # Generated summaries
│   ├── weekly/
│   │   ├── 2024-W03-bills.md
│   │   ├── 2024-W03-all.md
│   │   └── 2024-W04-bills.md
│   ├── monthly/
│   │   ├── 2024-01-bills.md
│   │   └── 2024-01-all.md
│   └── yearly/
│       └── 2024-all.md
│
└── alfrd.db                          # DuckDB database
```

**File Naming Convention:**
- Raw documents: `{uuid}.{original_extension}`
- Text files: `{uuid}.txt`
- Metadata: `{uuid}.json`
- Summaries: `{period}-{category}.md`

---

## Docker Infrastructure Specification

### Dockerfile (Alpine Linux)

```dockerfile
FROM python:3.11-alpine

# Install system dependencies
RUN apk add --no-cache \
    supervisor \
    curl \
    bash \
    gcc \
    musl-dev \
    libffi-dev

# Create app user
RUN addgroup -g 1000 alfrd && \
    adduser -D -u 1000 -G alfrd alfrd

# Set working directory
WORKDIR /app

# Create directory structure
RUN mkdir -p /data/inbox /data/documents /data/summaries && \
    chown -R alfrd:alfrd /data

# Copy application code
COPY --chown=alfrd:alfrd . /app

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install each subproject
RUN pip install -e /app/document-processor && \
    pip install -e /app/api-server && \
    pip install -e /app/mcp-server

# Copy supervisor config
COPY docker/supervisord.conf /etc/supervisord.conf

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose ports
EXPOSE 8000  # API Server
EXPOSE 8080  # Web UI (dev mode)
EXPOSE 3000  # MCP Server

# Switch to app user
USER alfrd

# Start supervisord
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisord.conf"]
```

### supervisord.conf

```ini
[supervisord]
nodaemon=true
user=alfrd
logfile=/data/logs/supervisord.log
pidfile=/tmp/supervisord.pid

[program:api-server]
command=python -m api_server.main
directory=/app/api-server
autostart=true
autorestart=true
stderr_logfile=/data/logs/api-server.err.log
stdout_logfile=/data/logs/api-server.out.log
environment=PYTHONUNBUFFERED=1

[program:mcp-server]
command=python -m mcp_server.main
directory=/app/mcp-server
autostart=true
autorestart=true
stderr_logfile=/data/logs/mcp-server.err.log
stdout_logfile=/data/logs/mcp-server.out.log
environment=PYTHONUNBUFFERED=1

[program:doc-processor-watcher]
command=python -m document_processor.watcher
directory=/app/document-processor
autostart=true
autorestart=true
stderr_logfile=/data/logs/doc-watcher.err.log
stdout_logfile=/data/logs/doc-watcher.out.log
environment=PYTHONUNBUFFERED=1

[program:doc-processor-batch]
command=python -m document_processor.main
directory=/app/document-processor
autostart=false
autorestart=false
stderr_logfile=/data/logs/doc-batch.err.log
stdout_logfile=/data/logs/doc-batch.out.log
environment=PYTHONUNBUFFERED=1

# Web UI in dev mode (single container)
[program:web-ui]
command=python -m http.server 8080 -d /app/web-ui/dist
directory=/app/web-ui
autostart=true
autorestart=true
stderr_logfile=/data/logs/web-ui.err.log
stdout_logfile=/data/logs/web-ui.out.log
environment=PYTHONUNBUFFERED=1
```

### docker-compose.yml (Development)

```yaml
version: '3.8'

services:
  alfrd:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: alfrd-dev
    ports:
      - "8000:8000"  # API Server
      - "8080:8080"  # Web UI
      - "3000:3000"  # MCP Server
    volumes:
      - ./data:/data
      - ./document-processor:/app/document-processor
      - ./api-server:/app/api-server
      - ./mcp-server:/app/mcp-server
      - ./web-ui:/app/web-ui
    environment:
      - ENV=development
      - CLAUDE_API_KEY=${CLAUDE_API_KEY}
      - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
      - LOG_LEVEL=DEBUG
    restart: unless-stopped
```

---

## OCR Integration - Claude Vision API

Using Claude's vision API instead of AWS Textract for MVP (simpler, one less service):

```python
import anthropic
import base64
from pathlib import Path

class ClaudeVisionExtractor:
    def __init__(self, api_key: str):
        self.client = anthropic.Anthropic(api_key=api_key)
    
    async def extract_text(self, image_path: Path) -> dict:
        """
        Extract text from image using Claude vision
        
        Returns:
            {
                "extracted_text": str,
                "confidence": float,
                "metadata": dict
            }
        """
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")
        
        # Determine media type
        suffix = image_path.suffix.lower()
        media_type_map = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp"
        }
        media_type = media_type_map.get(suffix, "image/jpeg")
        
        # Call Claude vision API
        message = self.client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=4096,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": image_data
                            }
                        },
                        {
                            "type": "text",
                            "text": """Extract all text from this document image. 

Provide:
1. The complete extracted text (maintain formatting/structure)
2. Document type (bill, receipt, form, letter, etc.)
3. Key information visible (amounts, dates, company names)
4. Any damage/quality issues affecting readability

Format as JSON."""
                        }
                    ]
                }
            ]
        )
        
        # Parse response
        response_text = message.content[0].text
        
        # For MVP, return simple structure
        return {
            "extracted_text": response_text,
            "confidence": 0.9,  # Claude is generally high confidence
            "metadata": {
                "model": "claude-3-5-sonnet-20241022",
                "image_format": media_type
            }
        }
```

**Alternative: AWS Textract** (for production if needed)
```python
import boto3

class TextractExtractor:
    def __init__(self):
        self.client = boto3.client('textract')
    
    async def extract_text(self, image_path: Path) -> dict:
        with open(image_path, 'rb') as document:
            response = self.client.detect_document_text(
                Document={'Bytes': document.read()}
            )
        
        # Parse blocks and reconstruct text
        text = "\n".join([
            block['Text'] 
            for block in response['Blocks'] 
            if block['BlockType'] == 'LINE'
        ])
        
        return {
            "extracted_text": text,
            "confidence": ...,
            "metadata": response
        }
```

---

## Web UI Structure (React + Capacitor)

### Key Features
- **Offline-first**: IndexedDB for local document/summary cache
- **Background sync**: Sync with API when online
- **Responsive**: Mobile-first design
- **Native-ready**: Capacitor for iOS/Android packaging

### Main Views

```
┌─────────────────────────────────────┐
│  Home Dashboard                     │
│  - Document count                   │
│  - Spending overview                │
│  - Bills due this week              │
│  - Recent documents                 │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Documents List                     │
│  - Filter by category               │
│  - Search                           │
│  - Sort by date/amount              │
│  - Upload button (FAB)              │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Document Viewer                    │
│  - Original image/PDF               │
│  - Extracted text                   │
│  - Structured data display          │
│  - Edit metadata                    │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Summaries                          │
│  - Hierarchical view:               │
│    - Yearly                         │
│      - Monthly                      │
│        - Weekly                     │
│  - Filter by category               │
│  - Download as PDF                  │
└─────────────────────────────────────┘

┌─────────────────────────────────────┐
│  Analytics                          │
│  - Spending charts                  │
│  - Category breakdown               │
│  - Trends over time                 │
└─────────────────────────────────────┘
```

### Offline Support Strategy

```javascript
// src/store/offline.js
import Dexie from 'dexie';

// IndexedDB schema
const db = new Dexie('alfrd');
db.version(1).stores({
  documents: 'id, category, created_at, vendor, amount',
  summaries: 'id, period_type, period_start, category',
  pendingUploads: '++id, file, created_at',
  syncQueue: '++id, action, data, created_at'
});

// Background sync
class SyncManager {
  async syncWhenOnline() {
    if (navigator.onLine) {
      // Upload pending documents
      const pending = await db.pendingUploads.toArray();
      for (const upload of pending) {
        await api.uploadDocument(upload.file);
        await db.pendingUploads.delete(upload.id);
      }
      
      // Sync document list
      const docs = await api.getDocuments();
      await db.documents.bulkPut(docs);
      
      // Sync summaries
      const summaries = await api.getSummaries();
      await db.summaries.bulkPut(summaries);
    }
  }
}

// Service worker for offline access
self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request)
      .then(response => response || fetch(event.request))
  );
});
```

---

## Implementation Phases & Testing Strategy

### Phase 1: Core Infrastructure (Week 1)

**Goal:** Single-container MVP with basic pipeline working

**Tasks:**
1. Set up project structure
2. Create Dockerfile and supervisord config
3. Initialize DuckDB schema
4. Implement basic document processor (file detection + OCR)
5. Implement basic API server (health endpoint, document list)
6. Implement basic MCP server (categorization tool only)
7. Wire up event system (processor → API → MCP)

**Success Criteria:**
- Drop image in inbox → processor extracts text → stores in DB → MCP categorizes → viewable via API
- All services running in single container
- Basic CLI to query API works

**Testing:**
```bash
# Manual test flow
cp test-bill.jpg data/inbox/
sleep 5  # Wait for processing
curl http://localhost:8000/api/v1/documents | jq
# Should show categorized document
```

### Phase 2: Web UI & Summaries (Week 2)

**Goal:** Basic web interface and summary generation

**Tasks:**
1. Set up React + Vite project
2. Implement document list view
3. Implement document viewer
4. Add MCP summarization tool
5. Implement summary generation logic
6. Add summary view to UI

**Success Criteria:**
- Can view documents in browser
- Can trigger summary generation
- Summaries display in UI

**Testing:**
```bash
# Integration test
npm run test:e2e  # Playwright tests
# - Upload document via UI
# - Verify it appears in list
# - Generate weekly summary
# - Verify summary renders
```

### Phase 3: Enhanced Features (Week 3-4)

**Goal:** Full MVP feature set

**Tasks:**
1. Implement full data extraction (amounts, dates, vendors)
2. Add search functionality
3. Add analytics dashboard
4. Implement offline support (IndexedDB)
5. Add Capacitor configuration
6. Improve error handling and logging

**Success Criteria:**
- Can search documents by text/category/vendor
- Analytics dashboard shows spending trends
- App works offline
- Can package as mobile app

**Testing:**
```python
# Unit tests for each component
pytest document-processor/tests/
pytest api-server/tests/
pytest mcp-server/tests/

# Integration tests
pytest tests/integration/

# Load test
locust -f tests/load/locustfile.py
```

### Phase 4: Multi-User & Production (Future)

**Goal:** Split architecture for multi-user deployment

**Tasks:**
1. Extract Web UI to separate server
2. Implement user authentication
3. Implement container orchestration (K8s or Docker Swarm)
4. Add API gateway for routing
5. Implement backup/restore
6. Set up monitoring (Prometheus/Grafana)

---

## Dependencies & Development Environment

### Python Dependencies

**document-processor:**
```toml
[tool.poetry.dependencies]
python = "^3.11"
anthropic = "^0.18.0"  # Claude API
watchdog = "^3.0.0"     # File system monitoring
pillow = "^10.2.0"      # Image processing
pypdf = "^3.17.0"       # PDF text extraction
httpx = "^0.26.0"       # HTTP client for events
pydantic = "^2.5.0"     # Data validation
python-magic = "^0.4.27" # File type detection
```

**api-server:**
```toml
[tool.poetry.dependencies]
python = "^3.11"
fastapi = "^0.109.0"
uvicorn = "^0.27.0"
duckdb = "^0.10.0"
pydantic = "^2.5.0"
python-multipart = "^0.0.6"  # File uploads
httpx = "^0.26.0"
```

**mcp-server:**
```toml
[tool.poetry.dependencies]
python = "^3.11"
mcp = "^0.9.0"          # Official MCP SDK
anthropic = "^0.18.0"   # Claude API
openai = "^1.10.0"      # For OpenRouter
pydantic = "^2.5.0"
jinja2 = "^3.1.3"       # Prompt templates
```

### JavaScript/Node Dependencies

**web-ui:**
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "@capacitor/core": "^5.6.0",
    "@capacitor/cli": "^5.6.0",
    "@capacitor/ios": "^5.6.0",
    "@capacitor/android": "^5.6.0",
    "dexie": "^3.2.4",
    "react-router-dom": "^6.21.0",
    "axios": "^1.6.5",
    "recharts": "^2.10.0",
    "date-fns": "^3.2.0"
  },
  "devDependencies": {
    "vite": "^5.0.0",
    "@vitejs/plugin-react": "^4.2.0",
    "tailwindcss": "^3.4.0",
    "playwright": "^1.41.0"
  }
}
```

### Environment Variables

```bash
# .env file
CLAUDE_API_KEY=sk-ant-...
OPENROUTER_API_KEY=sk-or-...
DATABASE_PATH=/data/alfrd.db
INBOX_PATH=/data/inbox
DOCUMENTS_PATH=/data/documents
SUMMARIES_PATH=/data/summaries
API_HOST=0.0.0.0
API_PORT=8000
MCP_PORT=3000
LOG_LEVEL=INFO
ENV=development
```

### Development Setup

```bash
# Clone and setup
git clone <repo>
cd alfrd

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install poetry
poetry install

# Set up environment
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python scripts/init-db.py

# Run in development (without Docker)
# Terminal 1: API Server
cd api-server && python -m api_server.main

# Terminal 2: MCP Server
cd mcp-server && python -m mcp_server.main

# Terminal 3: Document Processor
cd document-processor && python -m document_processor.watcher

# Terminal 4: Web UI
cd web-ui && npm run dev

# OR run with Docker
docker-compose up
```

---

## Next Steps & Discussion Points

### For Milestone 1 Implementation

**Immediate priorities:**
1. Scaffold project structure
2. Set up Docker environment
3. Implement document processor with Claude Vision OCR
4. Wire up basic event flow
5. Get one document through the pipeline end-to-end

### Open Questions

1. **LLM Provider Priority:** Should we implement multi-provider support in Phase 1, or start with Claude only?
   
2. **MCP Server Communication:** Should API server talk to MCP server via:
   - HTTP (MCP over HTTP transport)
   - Direct Python function calls (import mcp_server)
   - Unix socket

3. **Summary Triggers:** When should summaries auto-generate?
   - End of each period (cron job)?
   - On-demand only?
   - After N documents processed?

4. **Mobile Features:** Which native features are highest priority for mobile app?
   - Camera integration for document scanning
   - Push notifications for bill reminders
   - Biometric authentication

5. **Data Backup:** How should backups work in production?
   - Periodic DB snapshots to S3
   - Document filesystem backup
   - User export functionality

### Architecture Decisions - Phase 1C Complete + Phase 2A Partial

✅ **Validated:**
- **DuckDB** - Performing well for document storage and queries
- **AWS Textract** - Chosen over Claude Vision for production OCR quality (95%+ accuracy)
- **Worker Pool Pattern** - State-machine-driven polling works efficiently
- **MCP as Library** - Direct import working well, no separate server process needed
- **BedrockClient** - Multi-model support (Claude Sonnet 4 + Amazon Nova) working well
- **Self-Improving Prompts** - Prompt evolution system tested and functional
- **FastAPI** - API server with 5 endpoints implemented and tested
- **Ionic React** - Basic PWA UI structure created successfully

⏳ **To Validate:**
- **Camera Capture** - UI structure ready, needs backend integration testing
- **PWA Offline Support** - Not yet implemented
- **Supervisord** - Sufficient for single-container, may need K8s for multi-user

---

## Conclusion

This architecture provides a solid foundation for the ALFRD (Automated Ledger & Filing Research Database) system. **Phase 1B is now complete** with a fully functional worker pool architecture and MCP integration.

### Key Achievements:

1. **Worker Pool Architecture** - State-machine-driven parallel document processing
2. **AWS Textract OCR** - Production-quality text extraction with block-level data
3. **MCP Integration** - classify_document and summarize_bill tools working via Bedrock
4. **Type-Specific Handlers** - BillHandler extracts structured bill data automatically
5. **Full Pipeline** - Documents flow from inbox → OCR → classification → summarization → completed

### What's Working:

- ✅ Folder-based document input with meta.json
- ✅ AWS Textract OCR with 95%+ accuracy
- ✅ Three-worker pipeline (OCR → Classifier → Workflow)
- ✅ MCP classification via Bedrock (Claude Sonnet 4 + Amazon Nova)
- ✅ Bill summarization with structured data extraction
- ✅ DuckDB storage with full-text search
- ✅ LLM-optimized output with blocks for spatial reasoning
- ✅ Comprehensive logging and error handling
- ✅ Test suite (11/11 tests passing)

### Next Phase (Phase 2B - Complete PWA Integration):

1. ⏳ Wire up camera capture to API upload
2. ⏳ Fetch and display documents from API in UI
3. ⏳ Test end-to-end mobile workflow
4. ⏳ Add real-time status updates in UI
5. ❌ Implement hierarchical summaries (not started)
6. ❌ Add financial CSV exports (not started)

The system is ready for the next milestone: mobile photo capture and PWA interface.