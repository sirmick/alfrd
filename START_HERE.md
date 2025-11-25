# ALFRD - Quick Start Guide

**Automated Ledger & Filing Research Database**

## Initial Setup

### 1. Prerequisites
- Python 3.11+ installed
- AWS credentials configured (for Textract OCR)
- Virtual environment at `./venv` (if using venv)

### 2. Install Dependencies

```bash
# Install all dependencies
pip install -r requirements.txt

# Optional: Install in development mode for faster iteration
pip install -e ./document-processor
pip install -e ./api-server
pip install -e ./mcp-server
```

### 3. Configure Environment

```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your AWS credentials
nano .env  # or use your preferred editor
```

**Required settings in .env:**
```bash
# AWS Credentials (for Textract OCR)
AWS_ACCESS_KEY_ID=your-access-key
AWS_SECRET_ACCESS_KEY=your-secret-key
AWS_REGION=us-east-1

# Optional (already set for local development)
DATABASE_PATH=./data/alfrd.db
INBOX_PATH=./data/inbox
DOCUMENTS_PATH=./data/documents
SUMMARIES_PATH=./data/summaries
```

### 4. Initialize Database

**IMPORTANT: You must initialize the database before first use!**

```bash
# This creates the ./data directory and DuckDB database with schema
python3 scripts/init-db.py
```

Expected output:
```
Initializing database at ./data/alfrd.db
✓ Database initialized successfully at ./data/alfrd.db
  Tables created: documents, summaries, processing_events, analytics
```

## Document Processing Workflow

### Adding Documents

Use the `add-document.py` script to add documents to the inbox:

```bash
# Single image with default settings
python scripts/add-document.py ~/Downloads/bill.jpg

# Multiple images (multi-page document)
python scripts/add-document.py page1.jpg page2.jpg page3.jpg

# With custom tags and source
python scripts/add-document.py bill.jpg --tags bill utilities electric --source mobile

# Text files also supported
python scripts/add-document.py receipt.txt --tags receipt --source email
```

**Document Folder Structure:**

The script creates folders in `data/inbox/` with this structure:
```
data/inbox/
└── bill_20241125_120000/
    ├── meta.json          # Metadata with document list
    ├── bill.jpg           # Your document(s)
    └── page2.jpg          # Additional pages (if any)
```

### Processing Documents

Run the document processor to extract text and store documents:

```bash
# Standalone execution (no PYTHONPATH setup needed!)
python3 document-processor/src/document_processor/main.py

# Or use the convenience script
./scripts/process-documents.sh
```

**What it does:**
1. Scans `data/inbox/` for document folders
2. Reads `meta.json` from each folder
3. Runs AWS Textract OCR on images
4. Extracts text from text files
5. Combines into LLM-optimized format with blocks
6. Stores in database and filesystem
7. Moves processed folders to `data/processed/`

**Output:**
```
data/documents/2024/11/
├── raw/{doc-id}/          # Original folder copy
├── text/
│   ├── {doc-id}.txt       # Combined full text
│   └── {doc-id}_llm.json  # LLM-formatted with blocks
└── meta/{doc-id}.json     # Detailed metadata
```

### Complete Example

```bash
# 1. Initialize database (first time only)
python3 scripts/init-db.py

# 2. Add a document
python scripts/add-document.py samples/pg\&e-bill.jpg --tags bill utilities

# 3. Process documents
python3 document-processor/src/document_processor/main.py

# 4. Check results
ls -la data/processed/     # Processed folders
ls -la data/documents/     # Stored documents
```

## Running Services

### API Server

```bash
# Run directly (standalone)
python3 api-server/src/api_server/main.py

# Check health
curl http://localhost:8000/api/v1/health
```

### MCP Server

```bash
# Run directly (standalone)
python3 mcp-server/src/mcp_server/main.py
```

### Document Processor (Watcher Mode)

```bash
# Run watcher for continuous monitoring (not yet fully implemented)
python3 document-processor/src/document_processor/watcher.py

# Or use batch mode (process once and exit)
python3 document-processor/src/document_processor/main.py
```

## Testing

### Run Unit Tests

```bash
# Install pytest
pip install pytest pytest-asyncio

# Run storage tests
pytest document-processor/tests/test_storage.py -v

# Run all tests
pytest -v
```

### Test OCR Extraction

```bash
# Test AWS Textract with block display
python samples/test_ocr.py samples/pg\&e-bill.jpg
```

## Project Structure

```
alfrd/
├── shared/                    # Shared configuration and types
├── document-processor/        # Document ingestion and OCR
│   ├── src/document_processor/
│   │   ├── main.py           # Batch processor (STANDALONE)
│   │   ├── watcher.py        # File watcher
│   │   ├── detector.py       # File type detection
│   │   ├── storage.py        # Database and filesystem storage
│   │   └── extractors/
│   │       ├── aws_textract.py  # AWS Textract OCR
│   │       └── text.py          # Plain text extraction
│   └── tests/
├── api-server/               # REST API and orchestration
├── mcp-server/               # AI/LLM integration
├── scripts/
│   ├── init-db.py           # Database initialization (REQUIRED!)
│   ├── add-document.py      # Add documents to inbox
│   └── process-documents.sh # Process documents wrapper
└── data/                    # Runtime data (not in git)
    ├── inbox/              # Document folders (input)
    ├── processed/          # Processed folders (archived)
    ├── documents/          # Stored documents (output)
    └── alfrd.db            # DuckDB database
```

## Key Features

### Folder-Based Document Input

Documents are organized in folders with `meta.json`:

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

### LLM-Optimized Output

The processor creates structured output perfect for LLM consumption:

```json
{
  "full_text": "--- Document: bill.jpg ---\n[text]\n\n--- Document: page2.jpg ---\n[text]",
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

### Standalone Execution

All main scripts have built-in PYTHONPATH setup - no wrapper scripts needed:

```python
# At top of file
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root
sys.path.insert(0, str(Path(__file__).parent.parent))  # src directory
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
# Solution: Set up AWS credentials in .env
AWS_ACCESS_KEY_ID=your-key
AWS_SECRET_ACCESS_KEY=your-secret
AWS_REGION=us-east-1
```

### Import errors

```bash
# If you see ModuleNotFoundError
# The scripts should work standalone, but if not:
pip install -e ./document-processor
pip install -e ./api-server
pip install -e ./mcp-server
```

## Next Steps

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for detailed system design.
See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for development roadmap.
See [`PROGRESS.md`](PROGRESS.md) for current status.

## Development Commands

```bash
# Initialize database (required once)
python3 scripts/init-db.py

# Add a document
python scripts/add-document.py image.jpg --tags bill

# Process documents
python3 document-processor/src/document_processor/main.py

# Run tests
pytest document-processor/tests/ -v

# Test OCR
python samples/test_ocr.py samples/pg\&e-bill.jpg
```

---

**🚀 Ready to process your documents with AI!**