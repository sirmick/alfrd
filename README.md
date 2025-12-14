<div align="center">
  <img src="ALFRD.svg" alt="ALFRD Logo" width="200" />
  
  # ALFRD - Automated Ledger & Filing Research Database
  
  > Your personal AI-powered document management system that ingests, processes, and summarizes documents automatically using AWS Textract OCR and LLM classification via AWS Bedrock.
</div>

## What is ALFRD?

**ALFRD** (Automated Ledger & Filing Research Database) is a personal document management system that uses AI to automatically process, categorize, and summarize your documents. Drop a document folder in the inbox and ALFRD will:

- **Extract text** using AWS Textract OCR with block-level data preservation
- **Process folders** with multiple documents (multi-page bills, receipts, etc.)
- **Classify via MCP** using LLM-powered document type detection (AWS Bedrock)
- **Extract structured data** (vendor, amount, due date, line items) from bills automatically
- **Organize into series** with schema-consistent extraction across recurring documents
- **Store in PostgreSQL** with full-text search capability
- **Preserve for LLMs** with combined text + block-level structure for spatial reasoning

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 15+
- AWS credentials (for Textract OCR and Bedrock LLM)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/alfrd.git
cd alfrd

# Install dependencies
pip install -r requirements.txt

# Configure AWS credentials in .env
cp .env.example .env
# Edit .env and add AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION

# Initialize database (REQUIRED!)
./scripts/create-alfrd-db
```

### Process Your First Document

```bash
# 1. Add a document (creates folder with meta.json)
python scripts/add-document.py ~/Downloads/bill.jpg --tags bill utilities

# 2. Process documents (OCR + storage)
python3 document-processor/src/document_processor/main.py

# 3. Check results
ls -la data/processed/     # Processed folders
ls -la data/documents/     # Stored documents with extracted text
```

## Architecture Overview

### Folder-Based Document Input

Documents are organized in folders with metadata:

```
data/inbox/
└── bill_20241125_120000/
    ├── meta.json          # Document metadata
    ├── bill.jpg           # Page 1
    └── page2.jpg          # Page 2
```

### Asyncio Processing Pipeline with Recovery

```
User adds document → Folder created in inbox (PENDING)
                     ↓
         OCR Step → AWS Textract OCR (OCR_COMPLETED)
                     ↓
    Classify Step → Bedrock LLM classification (CLASSIFIED)
                     ↓
                Background: Score Classification (for prompt evolution)
                     ↓
   Summarize Step → Type-specific summarization (SUMMARIZED)
                     ↓
                Background: Score Summary (for prompt evolution)
                     ↓
       File Step → Series detection & tagging (FILED)
                     ↓
Series Summarize → Series-specific extraction (SERIES_SUMMARIZED)
                     ↓
                Background: Score Series Extraction
                     ↓
         Complete → Updates status (COMPLETED)
```

**Processing Features:**
- Asyncio orchestrator with semaphore-based concurrency control
- Automatic retry on failure (max 3 attempts per document)
- Periodic recovery scan for stuck work (every 5 minutes)
- 30-minute timeout for stale work detection
- Scoring steps run in background (fire-and-forget)
- PostgreSQL advisory locks prevent race conditions
- Comprehensive event logging for debugging

**Series-Specific Extraction (Schema Consistency):**
- Each document series gets its own extraction prompt
- All documents in a series have identical field names
- Eliminates schema drift (e.g., `total_amount` vs `amount_due`)
- Enables clean data tables and aggregation
- Prompts evolve together (all documents regenerated)

**Self-Improving Features:**
- Classifier prompt evolution based on classification accuracy
- Summarizer prompt evolution based on extraction quality
- Series prompt evolution with automatic regeneration
- LLM can suggest new document types
- Configure via `PROMPT_UPDATE_THRESHOLD` in .env (default: 0.05)

### LLM-Optimized Output

```json
{
  "full_text": "--- Document: bill.jpg ---\n[extracted text]\n\n--- Document: page2.jpg ---\n[more text]",
  "blocks_by_document": [
    {
      "file": "bill.jpg",
      "blocks": {
        "PAGE": [...],
        "LINE": [...],
        "WORD": [...]
      }
    }
  ],
  "document_count": 2,
  "total_chars": 1234,
  "avg_confidence": 0.95
}
```

## Key Features

### 🧠 AI-Powered Processing
- **🤖 Self-improving prompts** - Classifier, summarizer, and series prompts evolve based on quality
- **🔮 Dynamic classification** - LLM can suggest new document types automatically
- **📝 Type-specific summarization** - DB-driven, customizable per document type
- **🎯 Series-specific extraction** - Each document series gets consistent field names
- **⚡ Nova Lite inference** - Fast, cost-effective AWS Bedrock processing

### 📄 Document Processing
- **👁️ AWS Textract OCR** - 95%+ accuracy with block-level data preservation
- **📦 Multi-page support** - Process multiple images as single document
- **🏷️ Flexible tagging** - Secondary tags for rich classification
- **📂 Series detection** - Automatic grouping of recurring documents
- **♻️ Series regeneration** - All documents updated when series prompt improves

### 🔧 Robust Architecture
- **⚙️ Asyncio orchestration** - Semaphore-based concurrency control
- **🔒 PostgreSQL advisory locks** - Prevent race conditions in concurrent processing
- **🔄 Automatic recovery** - Retry on failure (max 3 attempts) + stale work detection
- **📊 Event logging system** - Comprehensive debugging with `./scripts/view-events`
- **📈 Prompt versioning** - All prompt changes tracked with version history

### 📱 Web Interface (PWA)
- **📷 Camera capture** - Take photos directly from mobile devices
- **📋 Document list** - Real-time data from API with refresh
- **🔍 Document detail** - Full metadata, OCR text, structured data display
- **📊 Data tables** - Flattened JSONB visualization

### 🗄️ Data & Storage
- **🐘 PostgreSQL** - Full-text search and structured JSONB data
- **📐 JSON flattening** - Convert nested data to flat tables with 4 array strategies
- **📤 CSV export** - CLI tool for data extraction and analysis
- **🔗 LLM-optimized format** - Combined text + block-level structure for spatial reasoning

### ✅ Testing & Quality
- **🧪 113+ tests** - Comprehensive pytest suite
- **🔬 Workflow tests** - End-to-end scenarios with real data
- **🛡️ Database tests** - Direct PostgreSQL operation validation
- **📊 API tests** - FastAPI endpoint coverage

## Project Structure

```
alfrd/
├── document-processor/        # Asyncio orchestrator
│   ├── src/document_processor/
│   │   ├── main.py           # Entry point
│   │   ├── orchestrator.py   # SimpleOrchestrator with recovery
│   │   ├── tasks/
│   │   │   ├── document_tasks.py     # Processing steps
│   │   │   └── series_regeneration.py # Series regeneration worker
│   │   ├── utils/
│   │   │   └── locks.py      # PostgreSQL advisory locks
│   │   └── extractors/
│   │       └── aws_textract.py    # AWS Textract OCR with blocks
│   └── tests/                # Pytest test suite
├── api-server/               # REST API (30+ endpoints)
├── mcp-server/               # LLM tools (library functions)
│   └── src/mcp_server/tools/
│       ├── summarize_series.py  # Series-specific extraction
│       └── ...
├── scripts/
│   ├── create-alfrd-db      # Database initialization (REQUIRED!)
│   ├── add-document         # Add documents to inbox
│   ├── view-events          # Event log viewer
│   └── start-processor      # Process documents wrapper
├── shared/                   # Shared configuration and types
│   ├── database.py          # PostgreSQL client
│   ├── event_logger.py      # Event logging utilities
│   └── tests/
└── data/                    # Runtime data (not in git)
    ├── inbox/              # Document folders (input)
    ├── processed/          # Processed folders (archived)
    ├── documents/          # Stored documents (output)
    └── postgres/           # PostgreSQL data (Docker)
```

## Usage Examples

### Add Documents

```bash
# Single image
python scripts/add-document.py photo.jpg --tags receipt

# Multiple pages
python scripts/add-document.py page1.jpg page2.jpg page3.jpg --tags bill electric

# With source
python scripts/add-document.py doc.jpg --source mobile --tags insurance
```

### Process Documents

```bash
# Process all documents in inbox (continuous mode)
python3 document-processor/src/document_processor/main.py

# Run once and exit
python3 document-processor/src/document_processor/main.py --once

# Process single document
python3 document-processor/src/document_processor/main.py --doc-id <UUID>

# Or use wrapper script
./scripts/start-processor
```

### Test OCR

```bash
# See detailed Textract block output
python samples/test_ocr.py samples/pg\&e-bill.jpg
```

### Run Tests

```bash
# Install pytest
pip install pytest pytest-asyncio

# Run storage tests
pytest document-processor/tests/test_storage.py -v
```

## meta.json Format

Each document folder requires a `meta.json` file:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "created_at": "2024-11-25T02:00:00Z",
  "documents": [
    {"file": "bill.jpg", "type": "image", "order": 1},
    {"file": "page2.jpg", "type": "image", "order": 2}
  ],
  "metadata": {
    "source": "mobile",
    "tags": ["bill", "utilities"]
  }
}
```

The `add-document.py` script creates this automatically.

## Configuration

### Environment Variables

```bash
# AWS Credentials (Required)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# Paths (Optional - defaults for local development)
DATABASE_URL=postgresql://alfrd_user@/alfrd?host=/var/run/postgresql
POSTGRES_PASSWORD=alfrd_dev_password
INBOX_PATH=./data/inbox
DOCUMENTS_PATH=./data/documents
SUMMARIES_PATH=./data/summaries

# Logging
LOG_LEVEL=INFO
ENV=development
```

## Common Issues

### Database not initialized

```bash
# Error: relation "documents" does not exist
# Solution: Initialize database
./scripts/create-alfrd-db
```

### AWS credentials not configured

```bash
# Error: AWS authentication failed
# Solution: Set up credentials in .env
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

## Development

### Running Tests

```bash
# Run all tests
pytest -v

# Run specific test file
pytest document-processor/tests/test_storage.py -v

# Run with coverage
pytest --cov=document_processor
```

### Code Structure

All main scripts have built-in PYTHONPATH setup for standalone execution:

```python
# At top of file
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # src directory
```

No wrapper scripts or environment setup needed!

## Technical Details

### Technologies

- **Python 3.11+** - Core language
- **AWS Textract** - Production OCR ($1.50/1000 pages)
- **AWS Bedrock** - LLM for classification/summarization (Nova Lite)
- **PostgreSQL 15+** - Production database with full-text search
- **FastAPI** - REST API framework
- **Asyncio** - Orchestration and concurrency
- **Pytest** - Testing framework

### Database Schema

Key tables:
- `documents` - Core document metadata, extracted text, and structured data
- `series` - Document series with active_prompt_id and regeneration_pending
- `prompts` - Evolving classifier, summarizer, and series prompts (versioned)
- `events` - Comprehensive event log for debugging
- `document_types` - Dynamic list of known document types
- `classification_suggestions` - LLM-suggested new document types

See `api-server/src/api_server/db/schema.sql` for complete schema.

## Statistics

- **📏 Lines of Code**: ~8,000+ lines (orchestrator + tasks + MCP tools + API + Web UI + events)
- **🧪 Test Coverage**: 113+ tests passing (database, API, workflow, locks)
- **👁️ OCR Accuracy**: 95%+ with AWS Textract
- **⚡ Processing Speed**: ~2-3 seconds per page
- **⚙️ Orchestration**: Simple asyncio with semaphore-based concurrency control
- **🔄 Recovery**: Automatic retry (3 attempts) + periodic stale work detection (5 min)
- **🤖 LLM Integration**: AWS Bedrock with Amazon Nova Lite
- **📈 Prompt Evolution**: Enabled with threshold=0.05 (configure via PROMPT_UPDATE_THRESHOLD)
- **📂 Series Prompts**: One per series for schema-consistent extraction
- **🏷️ Document Types**: 6 default types + unlimited LLM-suggested types
- **🔗 API Endpoints**: 30+ endpoints (health, documents, files, series, tags, prompts, events)
- **📊 Event Logging**: Full audit trail with `./scripts/view-events`
- **📱 Web UI**: Ionic React PWA with data visualization
- **📐 Data Analysis**: JSON flattening utility with 4 array strategies and pandas integration

## Contributing

See `STATUS.md` for current status and development roadmap.

## License

MIT License - see `LICENSE` file for details.

## Documentation

- **`START_HERE.md`** - Quick start guide
- **`ARCHITECTURE.md`** - System architecture and design decisions
- **`STATUS.md`** - Current status and development roadmap
- **`docs/JSON_FLATTENING.md`** - JSON flattening utilities guide

---

**🚀 Process your documents with AI-powered OCR and classification!**
