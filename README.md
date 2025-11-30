# ALFRD - Automated Ledger & Filing Research Database

> Your personal AI-powered document management system that ingests, processes, and summarizes documents automatically using AWS Textract OCR and LLM classification via AWS Bedrock.

## What is ALFRD?

**ALFRD** (Automated Ledger & Filing Research Database) is a personal document management system that uses AI to automatically process, categorize, and summarize your documents. Drop a document folder in the inbox and ALFRD will:

- **Extract text** using AWS Textract OCR with block-level data preservation
- **Process folders** with multiple documents (multi-page bills, receipts, etc.)
- **Classify via MCP** using LLM-powered document type detection (AWS Bedrock)
- **Extract structured data** (vendor, amount, due date, line items) from bills automatically
- **Store in DuckDB** with full-text search capability
- **Preserve for LLMs** with combined text + block-level structure for spatial reasoning

## Quick Start

### Prerequisites
- Python 3.11+
- AWS credentials (for Textract OCR)
- DuckDB (installed via pip)

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
python3 scripts/init-db.py
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

### Self-Improving Processing Pipeline

```
User adds document → Folder created in inbox (PENDING)
                     ↓
              OCRWorker → Textract OCR (OCR_COMPLETED)
                     ↓
          ClassifierWorker → DB prompt classification (CLASSIFIED)
                     ↓
      ClassifierScorerWorker → Scores & evolves prompt (SCORED_CLASSIFICATION)
                     ↓
         SummarizerWorker → Type-specific summarization (SUMMARIZED)
                     ↓
      SummarizerScorerWorker → Scores & evolves prompt (COMPLETED)
```

**Self-Improving Features:**
- Classifier prompt (max 300 words) evolves based on classification accuracy
- Summarizer prompts (per document type) evolve based on extraction quality
- LLM can suggest new document types beyond initial set (bill, finance, junk, school, event)
- System learns from mistakes and improves automatically

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

### ✅ Phase 1C Complete - Self-Improving Prompt Architecture

- **🧠 Self-improving prompts** - Prompts evolve based on performance feedback
- **🔄 Dynamic classification** - LLM can suggest new document types
- **📊 Generic workflow** - No hardcoded handlers, all DB-driven
- **🎯 Scorer workers** - Evaluate and improve classifier/summarizer prompts
- **🏷️ Secondary tags** - Flexible classification (tax, university, utility, etc.)
- **📝 Prompt versioning** - All prompt changes tracked with version history
- **Worker pool architecture** - State-machine-driven parallel processing (5 workers)
- **OCRWorker** - AWS Textract OCR with 95%+ accuracy
- **ClassifierWorker** - DB-driven classification with new type suggestions
- **SummarizerWorker** - Type-specific DB-driven summarization
- **Folder-based document input** with `meta.json` metadata
- **Block-level data preservation** (PAGE, LINE, WORD with bounding boxes)
- **Multi-document folders** (process multiple images as single document)
- **DuckDB storage** with full-text search and structured data
- **LLM-optimized format** for AI processing with spatial reasoning
- **Comprehensive logging** with timestamps
- **Test suite** with pytest (11/11 tests passing)
- **Standalone execution** (no PYTHONPATH setup needed)

### ⏳ Phase 2 - Coming Soon

- PWA interface with camera capture
- Image upload API endpoint
- Hierarchical summaries (weekly → monthly → yearly)
- Financial tracking with CSV exports
- Integration tests for full pipeline
- Real-time file watching (watchdog)

## Project Structure

```
alfrd/
├── document-processor/        # OCR and text extraction
│   ├── src/document_processor/
│   │   ├── main.py           # Batch processor (STANDALONE)
│   │   ├── detector.py       # File type detection
│   │   ├── storage.py        # Database and filesystem storage
│   │   └── extractors/
│   │       └── aws_textract.py  # AWS Textract OCR with blocks
│   └── tests/                # Pytest test suite
├── api-server/               # REST API (basic health endpoints)
├── mcp-server/               # AI/LLM integration (stub)
├── scripts/
│   ├── init-db.py           # Database initialization (REQUIRED!)
│   ├── add-document.py      # Add documents to inbox
│   └── process-documents.sh # Process documents wrapper
├── shared/                   # Shared configuration and types
└── data/                    # Runtime data (not in git)
    ├── inbox/              # Document folders (input)
    ├── processed/          # Processed folders (archived)
    ├── documents/          # Stored documents (output)
    └── alfrd.db            # DuckDB database
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
# Process all documents in inbox
python3 document-processor/src/document_processor/main.py

# Or use wrapper script
./scripts/process-documents.sh
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
DATABASE_PATH=./data/alfrd.db
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
# Error: Table 'documents' does not exist
# Solution: Initialize database
python3 scripts/init-db.py
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

## Roadmap

### Phase 1A: Core Document Processing ✅
- [x] Folder-based document input
- [x] AWS Textract OCR
- [x] LLM-optimized output format
- [x] DuckDB storage
- [x] Test suite
- [x] Helper scripts

### Phase 1B: Worker Pool Architecture ✅
- [x] BaseWorker + WorkerPool classes
- [x] OCRWorker with AWS Textract
- [x] ClassifierWorker with MCP integration
- [x] WorkflowWorker with type-specific handlers
- [x] MCP tools (classify_document, summarize_bill)
- [x] BedrockClient for AWS Bedrock API
- [x] Main orchestrator running all workers

### Phase 1C: Self-Improving Prompts ✅
- [x] Prompts table for classifier and summarizers
- [x] Classification suggestions table
- [x] Document types table (dynamic)
- [x] ClassifierScorerWorker with prompt evolution
- [x] SummarizerScorerWorker with prompt evolution
- [x] Generic SummarizerWorker (replaces hardcoded handlers)
- [x] Dynamic classification with new type suggestions
- [x] Secondary tags for flexible classification
- [x] Prompt versioning and performance tracking
- [x] Default prompts initialization

### Phase 2: PWA Interface (Next)
- [ ] Ionic PWA with camera capture
- [ ] Image upload API endpoint
- [ ] Mobile photo workflow
- [ ] Integration tests

### Phase 3: Analytics & UI
- [ ] Hierarchical summaries
- [ ] Financial tracking
- [ ] Web UI
- [ ] Real-time file watching

### Phase 4: Production
- [ ] Multi-user support
- [ ] API authentication
- [ ] Container deployment
- [ ] Backup/restore

## Technical Details

### Technologies

- **Python 3.11+** - Core language
- **AWS Textract** - Production OCR ($1.50/1000 pages)
- **DuckDB** - Embedded analytical database
- **FastAPI** - REST API framework
- **MCP SDK** - Model Context Protocol
- **Pytest** - Testing framework

### Database Schema

Key tables:
- `documents` - Core document metadata and extracted text
- `prompts` - Evolving classifier and summarizer prompts (versioned)
- `classification_suggestions` - LLM-suggested new document types
- `document_types` - Dynamic list of known document types
- `summaries` - Generated summaries by period
- `processing_events` - Event log for pipeline
- `analytics` - Pre-computed metrics

See `api-server/src/api_server/db/schema.sql` for complete schema.

## Statistics

- **Lines of Code**: ~5,000+ lines (core + workers + scorers + MCP tools + API + Web UI)
- **Test Coverage**: 14/14 tests passing (storage + worker infrastructure + pipeline integration)
- **OCR Accuracy**: 95%+ with AWS Textract
- **Processing Speed**: ~2-3 seconds per page
- **Worker Architecture**: 5 workers (OCR, Classifier, ClassifierScorer, Summarizer, SummarizerScorer)
- **MCP Integration**: Bedrock with Claude Sonnet 4 + Amazon Nova
- **Prompt Evolution**: Automatic improvement based on performance feedback
- **Document Types**: 6 default types (bill, finance, school, event, junk, generic) + unlimited LLM-suggested types
- **API Endpoints**: 5 endpoints (health, documents list/detail/file, upload-image)
- **Web UI**: Ionic React PWA with 3 pages (capture, documents, detail)

## Contributing

See `IMPLEMENTATION_PLAN.md` for development roadmap and `PROGRESS.md` for current status.

## License

MIT License - see `LICENSE` file for details.

## Documentation

- **`START_HERE.md`** - Quick start guide
- **`ARCHITECTURE.md`** - System architecture
- **`IMPLEMENTATION_PLAN.md`** - Development roadmap
- **`PROGRESS.md`** - Current status

---

**🚀 Process your documents with AI-powered OCR and classification!**
