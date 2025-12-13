# ALFRD - Quick Start Guide

**Automated Ledger & Filing Research Database**

> **Current Status:** Phase 1C Complete + Series Schema Stability
>
> Simple asyncio orchestration with PostgreSQL database, series-specific extraction, and Ionic React PWA interface.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Database Setup](#database-setup)
- [Starting Services](#starting-services)
- [Processing Documents](#processing-documents)
- [Using the Web UI](#using-the-web-ui)
- [Debugging with Events](#debugging-with-events)
- [Command Reference](#command-reference)
- [Project Structure](#project-structure)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Software

- **Python 3.11+** - Core application runtime
- **PostgreSQL 15+** - Production database with full-text search
- **Node.js 18+** - Web UI development
- **AWS Account** - For Textract OCR and Bedrock LLM services

### AWS Services Required

- **AWS Textract** - OCR text extraction ($1.50/1000 pages)
- **AWS Bedrock** - LLM for classification/summarization
  - Using `us.amazon.nova-lite-v1:0` inference profile

---

## Installation

### 1. Clone Repository

```bash
git clone <repository-url>
cd esec
```

### 2. Install Python Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Install Web UI Dependencies

```bash
cd web-ui
npm install
cd ..
```

### 4. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your credentials
nano .env  # or use your preferred editor
```

**Required settings in `.env`:**

```bash
# AWS Credentials (for Textract OCR and Bedrock LLM)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# PostgreSQL Database (local development)
DATABASE_URL=postgresql://alfrd_user@/alfrd?host=/var/run/postgresql
POSTGRES_PASSWORD=alfrd_dev_password

# Prompt Evolution (default: 0.05 - enabled)
PROMPT_UPDATE_THRESHOLD=0.05

# Optional: Customize paths
INBOX_PATH=./data/inbox
DOCUMENTS_PATH=./data/documents
```

---

## Database Setup

### Option 1: Native PostgreSQL (Recommended for Development)

**Install PostgreSQL:**

```bash
# macOS (Homebrew)
brew install postgresql@15
brew services start postgresql@15

# Ubuntu/Debian
sudo apt install postgresql-15
sudo systemctl start postgresql

# Arch Linux
sudo pacman -S postgresql
sudo systemctl start postgresql
```

**Create Database:**

```bash
# Create user and database
./scripts/create-alfrd-db

# Or manually:
createuser -s alfrd_user
createdb -O alfrd_user alfrd
```

**Initialize Schema:**

```bash
# Run schema initialization
psql -U alfrd_user -d alfrd -f api-server/src/api_server/db/schema.sql
```

### Option 2: Docker (Complete Isolated Environment)

```bash
# Start PostgreSQL and ALFRD services
docker-compose -f docker/docker-compose.yml up -d

# Database is automatically initialized via schema.sql
```

**Docker includes:**
- PostgreSQL 15 with persistent storage
- Automatic schema initialization
- Unix socket connection for performance
- Health checks for service readiness

---

## Starting Services

### Development Mode (Native)

Run each service in a separate terminal:

```bash
# Terminal 1: API Server (port 8000)
./scripts/start-api

# Terminal 2: Document Processor Workers
./scripts/start-processor

# Terminal 3: Web UI (port 3000)
./scripts/start-webui
```

### Docker Mode

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up

# Or in detached mode
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f alfrd
```

**Services:**
- API Server: http://localhost:8000
- Web UI: http://localhost:5173 (Vite dev server)
- PostgreSQL: localhost:5432

---

## Processing Documents

### 1. Add a Document

```bash
# Single image
./scripts/add-document ~/Downloads/bill.jpg --tags bill utilities

# Multiple pages (processed as one document)
./scripts/add-document page1.jpg page2.jpg --tags invoice

# With custom source
./scripts/add-document receipt.jpg --tags receipt --source mobile
```

**This creates:**
```
data/inbox/
└── bill_20241130_140000/
    ├── meta.json          # Metadata with document list
    └── bill.jpg           # Your document
```

### 2. Process Documents

The document processor runs an asyncio orchestrator:

```bash
# Run processor (continuous mode - processes all inbox documents)
./scripts/start-processor

# Or run once and exit
python3 document-processor/src/document_processor/main.py --once

# Or process single document
python3 document-processor/src/document_processor/main.py --doc-id <UUID>
```

**Pipeline stages:**
1. **OCR Step** - AWS Textract OCR extraction
2. **Classify Step** - Document type classification (bill/finance/junk/etc)
3. **Background: Score Classification** - Evaluate classifier performance
4. **Summarize Step** - Generate type-specific summary
5. **Background: Score Summary** - Evaluate summarizer performance
6. **File Step** - Series detection and filing
7. **Series Summarize Step** - Entity-specific extraction with schema enforcement
8. **Background: Score Series** - Evaluate and evolve series prompt
9. **Complete** - Final status update

**Recovery Features:**
- Automatic retry on failure (max 3 attempts)
- Periodic stale work detection (every 5 minutes)
- 30-minute timeout for stuck work
- Startup recovery scan

### 3. View Results

```bash
# List all documents
./scripts/view-document

# View specific document
./scripts/view-document <doc-id>

# View with statistics
./scripts/view-document --stats

# View prompt evolution
./scripts/view-prompts
```

**Output structure:**
```
data/documents/2024/11/
├── raw/{doc-id}/              # Original folder copy
├── text/
│   ├── {doc-id}.txt          # Full extracted text
│   └── {doc-id}_llm.json     # LLM-formatted with blocks
└── meta/{doc-id}.json         # Processing metadata
```

---

## Using the Web UI

### Features

- **Camera Capture** - Take photos of documents
- **Document List** - View all processed documents
- **Document Details** - See OCR text, summaries, and classifications
- **Status Tracking** - Real-time processing status

### Workflow

1. **Start Web UI**: `./scripts/start-webui`
2. **Navigate to**: http://localhost:3000
3. **Capture or Upload**: Use camera or file upload
4. **Monitor**: Watch document process through pipeline
5. **Review**: View extracted data and summaries

---

## Debugging with Events

ALFRD includes a comprehensive event logging system for debugging:

### View Events

```bash
# View events for any entity (auto-detects document/file/series)
./scripts/view-events <uuid>

# View events for a specific document
./scripts/view-events --document <uuid>

# View events for a series
./scripts/view-events --series <uuid>

# Filter by category
./scripts/view-events <uuid> --category llm_request
./scripts/view-events <uuid> --category processing
./scripts/view-events <uuid> --category error

# Show full prompt/response text
./scripts/view-events <uuid> --full

# JSON output for scripting
./scripts/view-events <uuid> --json

# Limit results
./scripts/view-events <uuid> --limit 100
```

### Event Categories

- **state_transition** - Document status changes (pending → classified)
- **llm_request** - LLM API calls with prompt/response
- **processing** - Processing milestones (regeneration_started, lock_acquired)
- **error** - Failures and exceptions
- **user_action** - Manual interventions

### Example: Debug Series Prompt Creation

```bash
# Find the series
./scripts/view-events --series <series-uuid> --category processing

# Look for these events:
# - lock_requested: Task wants the series_prompt lock
# - lock_acquired: Lock granted
# - prompt_created: New series prompt created
# - lock_released: Lock freed
```

---

## Command Reference

### Database Commands

```bash
# Initialize database (PostgreSQL)
./scripts/create-alfrd-db

# Reset database (DELETES ALL DATA!)
psql -U alfrd_user -d alfrd -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
psql -U alfrd_user -d alfrd -f api-server/src/api_server/db/schema.sql
```

### Document Management

```bash
# Add document
./scripts/add-document <files...> [--tags tag1 tag2] [--source mobile]

# View documents
./scripts/view-document              # List all
./scripts/view-document <doc-id>     # View specific
./scripts/view-document --stats      # Show statistics
./scripts/view-document --list       # List recent
```

### Service Management

```bash
# Start services individually
./scripts/start-api         # API Server (port 8000)
./scripts/start-processor   # Document processor (asyncio orchestrator)
./scripts/start-webui       # Web UI (port 3000)

# View logs (Docker)
docker-compose -f docker/docker-compose.yml logs -f
```

### Prompt Management

```bash
# View all prompts with history
./scripts/view-prompts

# View classifier prompts only
./scripts/view-prompts --type classifier

# View summarizer prompts only
./scripts/view-prompts --type summarizer

# View series prompts
./scripts/view-prompts --type series_summarizer

# Include archived versions
./scripts/view-prompts --archived
```

### Event Logging

```bash
# View events for any entity
./scripts/view-events <uuid>

# Filter by category
./scripts/view-events <uuid> --category llm_request

# Show full LLM prompt/response text
./scripts/view-events <uuid> --full

# JSON output
./scripts/view-events <uuid> --json
```

### Testing

```bash
# Run all tests
pytest -v

# Run database tests
pytest shared/tests/test_database.py -v

# Test complete pipeline
./samples/test-pipeline.sh
```

---

## Project Structure

```
esec/
├── api-server/              # FastAPI REST API
│   ├── src/api_server/
│   │   ├── main.py         # API server entry point (30+ endpoints)
│   │   └── db/schema.sql   # PostgreSQL schema
│   └── tests/
├── document-processor/      # Document processing workers
│   ├── src/document_processor/
│   │   ├── main.py         # Asyncio orchestrator entry point
│   │   ├── orchestrator.py # SimpleOrchestrator with recovery
│   │   ├── tasks/
│   │   │   ├── document_tasks.py      # All processing tasks
│   │   │   └── series_regeneration.py # Series regeneration worker
│   │   ├── utils/
│   │   │   └── locks.py    # PostgreSQL advisory locks
│   │   └── extractors/
│   │       └── aws_textract.py  # Textract integration
│   └── tests/
├── mcp-server/              # LLM integration tools
│   └── src/mcp_server/
│       ├── tools/           # MCP tool implementations
│       │   └── summarize_series.py  # Series-specific extraction
│       └── llm/bedrock.py   # AWS Bedrock client
├── web-ui/                  # Ionic React PWA
│   ├── src/
│   │   ├── components/
│   │   │   └── DataTable.jsx         # Flattened data table
│   │   ├── pages/          # UI pages
│   │   │   └── FileDetailPage.jsx    # Shows data table
│   │   └── App.jsx         # Main app component
│   └── public/
├── shared/                  # Shared utilities
│   ├── config.py           # Configuration
│   ├── database.py         # PostgreSQL client
│   ├── event_logger.py     # Event logging utilities
│   ├── types.py            # Type definitions
│   └── tests/
│       └── test_database.py
├── scripts/                 # CLI utilities
│   ├── add-document        # Add documents to inbox
│   ├── view-document       # View processed documents
│   ├── view-prompts        # View prompt evolution
│   ├── view-events         # Event log viewer
│   ├── start-api           # Start API server
│   ├── start-processor     # Start workers
│   └── start-webui         # Start web UI
├── docker/                  # Docker configuration
│   ├── Dockerfile
│   ├── docker-compose.yml
│   └── supervisord.conf
└── data/                    # Runtime data (not in git)
    ├── inbox/              # Document input folders
    ├── documents/          # Processed documents
    └── postgres/           # PostgreSQL data (Docker)
```

---

## Troubleshooting

### PostgreSQL Connection Issues

**Error:** `could not connect to server`

```bash
# Check PostgreSQL is running
pg_isready -h /var/run/postgresql

# Start PostgreSQL service
brew services start postgresql@15  # macOS
sudo systemctl start postgresql    # Linux
```

**Error:** `role "alfrd_user" does not exist`

```bash
# Create user and database
./scripts/create-alfrd-db
```

### AWS Credentials Not Configured

**Error:** `AWS authentication failed`

```bash
# Set up AWS credentials in .env
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1

# Or use AWS CLI
aws configure
```

### Import Errors

**Error:** `ModuleNotFoundError`

```bash
# Activate virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Port Already in Use

**Error:** `Address already in use (port 8000)`

```bash
# Find and kill process using port
lsof -ti:8000 | xargs kill -9

# Or use different port
API_PORT=8001 ./scripts/start-api
```

### Database Schema Out of Date

```bash
# Re-initialize schema (DELETES ALL DATA!)
psql -U alfrd_user -d alfrd -f api-server/src/api_server/db/schema.sql
```

### Debugging Processing Issues

```bash
# View events for a document to see what happened
./scripts/view-events <document-uuid>

# Check for errors
./scripts/view-events <document-uuid> --category error

# See LLM calls with full prompts
./scripts/view-events <document-uuid> --category llm_request --full
```

---

## Key Features

### Series-Specific Extraction (Schema Consistency)

ALFRD ensures all documents in a series have identical field names:

- **First document** creates the series prompt from generic extraction
- **Subsequent documents** use the SAME prompt for consistent field names
- **PostgreSQL advisory locks** prevent race conditions
- **Automatic regeneration** when series prompt improves

This eliminates schema drift:
- Before: `total_amount` vs `amount_due` vs `premium_amount`
- After: All documents use `total_amount`

### Self-Improving Prompts

- Classifier prompt evolution based on accuracy
- Summarizer prompt evolution based on extraction quality
- Series prompt evolution with automatic regeneration
- LLM can suggest new document types
- Configure threshold via `PROMPT_UPDATE_THRESHOLD` (default: 0.05)

### Document Processing Pipeline

```
User uploads → OCR → Classify → Summarize → File → Series Summarize → Complete
                ↓       ↓          ↓          ↓            ↓             ↓
            Textract  Bedrock   Type-Spec  Series      Entity-Spec    Status
                              Summary    Detection    Extraction     Update

Background Tasks (fire-and-forget):
- Score Classification → Prompt evolution
- Score Summary → Prompt evolution
- Score Series → Series prompt evolution + regeneration
```

### Recovery & Retry Features

- **Automatic Retry**: Failed documents retried up to 3 times
- **Stale Work Detection**: Periodic scan every 5 minutes
- **Timeout Management**: 30-minute timeout for in-progress work
- **Startup Recovery**: Initial scan on startup to recover from crashes
- **Error Tracking**: Comprehensive logging and retry count tracking

### Supported Document Types

- **bill** - Utility bills, invoices, statements
- **finance** - Bank statements, credit card statements
- **school** - Educational documents
- **event** - Event tickets, confirmations
- **junk** - Spam, promotional materials
- **generic** - Catch-all for other documents

LLM can suggest additional types dynamically!

---

## Next Steps

- **See [`ARCHITECTURE.md`](ARCHITECTURE.md)** - System design and architecture
- **See [`STATUS.md`](STATUS.md)** - Current development status

---

**Ready to process documents with AI-powered OCR, classification, and schema-consistent extraction!**

**Last Updated:** 2025-12-12 (Series Schema Stability)
