# Implementation Plan - Commit-by-Commit Build Guide

This document breaks down the implementation of the AI Document Secretary system into atomic, testable commits. Each commit represents a working milestone that can be deployed and tested independently.

## Branch Strategy

```
main
  └── feature/phase-1-infrastructure
       ├── feature/document-processor
       ├── feature/api-server
       ├── feature/mcp-server
       └── feature/web-ui
```

---

## Phase 1: Core Infrastructure & Basic Pipeline

**Goal**: Get a single document through the complete processing pipeline end-to-end.

### Commit 1: Project scaffolding and directory structure
**Branch**: `feature/phase-1-infrastructure`
**Files**: Project structure, .gitignore, base configs

```bash
# Create all directories
mkdir -p document-processor/src/document_processor/extractors
mkdir -p document-processor/tests
mkdir -p api-server/src/api_server/{api,services,models,db}
mkdir -p api-server/tests
mkdir -p mcp-server/src/mcp_server/{tools,prompts,llm}
mkdir -p mcp-server/tests
mkdir -p web-ui/{src,public}
mkdir -p docker/scripts
mkdir -p shared
mkdir -p data/{inbox,documents,summaries}
mkdir -p tests/{integration,load}
```

**Files to create**:
- `.gitignore`
- `.env.example`
- `pyproject.toml` (root)
- `document-processor/pyproject.toml`
- `api-server/pyproject.toml`
- `mcp-server/pyproject.toml`
- `shared/__init__.py`
- `shared/config.py`
- `shared/types.py`
- `shared/constants.py`

**Test**: Directory structure exists, Python imports work

```bash
git add .
git commit -m "feat: initial project scaffolding and directory structure

- Create monorepo structure for all subprojects
- Add base configuration files
- Set up shared utilities module
- Add .gitignore for Python, Node, and data files"
```

---

### Commit 2: Shared configuration and types
**Branch**: `feature/phase-1-infrastructure`
**Files**: `shared/config.py`, `shared/types.py`, `shared/constants.py`

**Implement**:
```python
# shared/config.py
from pydantic_settings import BaseSettings
from pathlib import Path

class Settings(BaseSettings):
    # API Keys
    claude_api_key: str
    openrouter_api_key: str = ""
    
    # Paths
    database_path: Path = Path("/data/esec.db")
    inbox_path: Path = Path("/data/inbox")
    documents_path: Path = Path("/data/documents")
    summaries_path: Path = Path("/data/summaries")
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    mcp_port: int = 3000
    
    # Logging
    log_level: str = "INFO"
    env: str = "development"
    
    class Config:
        env_file = ".env"

# shared/types.py
from enum import Enum
from typing import Optional
from datetime import datetime
from pydantic import BaseModel
from uuid import UUID

class DocumentStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class DocumentCategory(str, Enum):
    BILL = "bill"
    TAX = "tax"
    RECEIPT = "receipt"
    INSURANCE = "insurance"
    ADVERTISING = "advertising"
    OTHER = "other"

class DocumentMetadata(BaseModel):
    id: UUID
    filename: str
    file_type: str
    status: DocumentStatus
    category: Optional[DocumentCategory] = None
    vendor: Optional[str] = None
    amount: Optional[float] = None
    due_date: Optional[datetime] = None
    created_at: datetime

# shared/constants.py
SUPPORTED_IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
SUPPORTED_DOCUMENT_TYPES = {".pdf"}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB
```

**Test**: Configuration loads, types validate

```bash
git add shared/
git commit -m "feat: add shared configuration and type definitions

- Implement Settings with pydantic-settings
- Define core enums (DocumentStatus, DocumentCategory)
- Add DocumentMetadata model
- Define supported file types and constants"
```

---

### Commit 3: DuckDB schema and initialization
**Branch**: `feature/phase-1-infrastructure`
**Files**: `api-server/src/api_server/db/schema.sql`, `scripts/init-db.py`

**Implement**:
```sql
-- api-server/src/api_server/db/schema.sql
-- (Use schema from ARCHITECTURE.md)
```

```python
# scripts/init-db.py
import duckdb
from pathlib import Path
from shared.config import Settings

def init_database():
    settings = Settings()
    db_path = settings.database_path
    
    # Create database
    conn = duckdb.connect(str(db_path))
    
    # Read and execute schema
    schema_path = Path("api-server/src/api_server/db/schema.sql")
    with open(schema_path) as f:
        schema_sql = f.read()
    
    conn.executescript(schema_sql)
    conn.close()
    
    print(f"✓ Database initialized at {db_path}")

if __name__ == "__main__":
    init_database()
```

**Test**: Run script, verify tables exist

```bash
git add api-server/src/api_server/db/schema.sql scripts/init-db.py
git commit -m "feat: add DuckDB schema and initialization script

- Create complete database schema with FTS5 support
- Add documents, summaries, events, and analytics tables
- Implement init-db.py script for database setup
- Add indexes for common query patterns"
```

---

### Commit 4: Docker infrastructure - base image
**Branch**: `feature/phase-1-infrastructure`
**Files**: `docker/Dockerfile`, `docker/docker-compose.yml`, `requirements.txt`

**Implement**:
```dockerfile
# docker/Dockerfile
# (Use Dockerfile from ARCHITECTURE.md)
```

```yaml
# docker/docker-compose.yml
# (Use docker-compose.yml from ARCHITECTURE.md)
```

```txt
# requirements.txt
anthropic>=0.18.0
fastapi>=0.109.0
uvicorn>=0.27.0
duckdb>=0.10.0
watchdog>=3.0.0
pydantic>=2.5.0
pydantic-settings>=2.1.0
python-multipart>=0.0.6
httpx>=0.26.0
pillow>=10.2.0
pypdf>=3.17.0
python-magic>=0.4.27
mcp>=0.9.0
jinja2>=3.1.3
```

**Test**: Build Docker image successfully

```bash
git add docker/ requirements.txt
git commit -m "feat: add Docker infrastructure for single-container deployment

- Create Alpine-based Dockerfile with Python 3.11
- Add supervisord configuration placeholder
- Set up docker-compose for development
- Add all Python dependencies to requirements.txt"
```

---

### Commit 5: Supervisord configuration
**Branch**: `feature/phase-1-infrastructure`
**Files**: `docker/supervisord.conf`

**Implement**: (Use supervisord.conf from ARCHITECTURE.md)

**Test**: Supervisord config is valid

```bash
git add docker/supervisord.conf
git commit -m "feat: add supervisord configuration for process management

- Configure API server process
- Configure MCP server process
- Configure document processor watcher
- Configure batch processor
- Add logging for all services"
```

---

### Commit 6: Document processor - file detection
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/detector.py`

**Implement**:
```python
# document-processor/src/document_processor/detector.py
import magic
from pathlib import Path
from shared.constants import SUPPORTED_IMAGE_TYPES, SUPPORTED_DOCUMENT_TYPES

class FileDetector:
    def __init__(self):
        self.magic = magic.Magic(mime=True)
    
    def detect_type(self, file_path: Path) -> tuple[str, str]:
        """
        Detect file type and category.
        Returns: (file_type, mime_type)
        file_type: 'image', 'pdf', 'unknown'
        """
        mime_type = self.magic.from_file(str(file_path))
        suffix = file_path.suffix.lower()
        
        if suffix in SUPPORTED_IMAGE_TYPES:
            return ("image", mime_type)
        elif suffix in SUPPORTED_DOCUMENT_TYPES:
            return ("pdf", mime_type)
        else:
            return ("unknown", mime_type)
    
    def is_supported(self, file_path: Path) -> bool:
        file_type, _ = self.detect_type(file_path)
        return file_type in ["image", "pdf"]
```

**Test**: Unit tests for file detection

```bash
git add document-processor/
git commit -m "feat(document-processor): implement file type detection

- Add FileDetector class using python-magic
- Support image and PDF detection
- Validate against supported file types
- Add unit tests for detection logic"
```

---

### Commit 7: Document processor - Claude Vision OCR
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/extractors/image_ocr.py`

**Implement**:
```python
# document-processor/src/document_processor/extractors/image_ocr.py
# (Use ClaudeVisionExtractor from ARCHITECTURE.md)
```

**Test**: Integration test with sample image

```bash
git add document-processor/src/document_processor/extractors/
git commit -m "feat(document-processor): implement Claude Vision OCR extractor

- Add ClaudeVisionExtractor class
- Support multiple image formats (jpg, png, webp)
- Extract text with metadata
- Handle API errors gracefully
- Add integration tests with mock API"
```

---

### Commit 8: Document processor - PDF text extraction
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/extractors/pdf.py`

**Implement**:
```python
# document-processor/src/document_processor/extractors/pdf.py
from pathlib import Path
from pypdf import PdfReader

class PDFExtractor:
    async def extract_text(self, pdf_path: Path) -> dict:
        reader = PdfReader(pdf_path)
        text = ""
        for page in reader.pages:
            text += page.extract_text() + "\n"
        
        return {
            "extracted_text": text.strip(),
            "confidence": 1.0,
            "metadata": {
                "page_count": len(reader.pages),
                "extractor": "pypdf"
            }
        }
```

**Test**: Extract text from sample PDF

```bash
git add document-processor/src/document_processor/extractors/pdf.py
git commit -m "feat(document-processor): implement PDF text extraction

- Add PDFExtractor using pypdf
- Extract text from all pages
- Return structured response matching OCR format
- Add tests with sample PDFs"
```

---

### Commit 9: Document processor - storage module
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/storage.py`

**Implement**:
```python
# document-processor/src/document_processor/storage.py
from pathlib import Path
from datetime import datetime
import shutil
import json
from uuid import uuid4
import duckdb
from shared.config import Settings
from shared.types import DocumentStatus

class DocumentStorage:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.db_path = settings.database_path
    
    async def store_document(self, source_path: Path, extracted_data: dict) -> str:
        """
        Store document and extracted data.
        Returns: document_id
        """
        doc_id = str(uuid4())
        now = datetime.utcnow()
        year_month = now.strftime("%Y/%m")
        
        # Create storage paths
        base_path = self.settings.documents_path / year_month
        raw_path = base_path / "raw"
        text_path = base_path / "text"
        meta_path = base_path / "meta"
        
        for path in [raw_path, text_path, meta_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        # Copy original file
        dest_file = raw_path / f"{doc_id}{source_path.suffix}"
        shutil.copy2(source_path, dest_file)
        
        # Save extracted text
        text_file = text_path / f"{doc_id}.txt"
        text_file.write_text(extracted_data["extracted_text"])
        
        # Save metadata
        meta_file = meta_path / f"{doc_id}.json"
        meta_file.write_text(json.dumps(extracted_data["metadata"], indent=2))
        
        # Insert into database
        conn = duckdb.connect(str(self.db_path))
        conn.execute("""
            INSERT INTO documents (
                id, filename, original_path, file_type, file_size,
                status, raw_document_path, extracted_text_path,
                metadata_path, extracted_text, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, source_path.name, str(source_path),
            extracted_data.get("file_type", "unknown"),
            source_path.stat().st_size, DocumentStatus.PROCESSING,
            str(dest_file), str(text_file), str(meta_file),
            extracted_data["extracted_text"], now
        ])
        conn.close()
        
        return doc_id
```

**Test**: Store document and verify filesystem + DB

```bash
git add document-processor/src/document_processor/storage.py
git commit -m "feat(document-processor): implement document storage

- Store original files in dated directories
- Save extracted text and metadata
- Insert records into DuckDB
- Generate UUIDs for document tracking
- Add comprehensive tests"
```

---

### Commit 10: Document processor - event emitter
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/events.py`

**Implement**:
```python
# document-processor/src/document_processor/events.py
import httpx
from datetime import datetime
from uuid import uuid4
from shared.config import Settings

class EventEmitter:
    def __init__(self, settings: Settings):
        self.api_url = f"http://localhost:{settings.api_port}"
    
    async def emit_document_processed(self, document_id: str, status: str, error: str = None):
        event = {
            "event_type": "document_processed",
            "event_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "document_id": document_id,
                "status": status,
                "error": error
            }
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/api/v1/events/document-processed",
                    json=event,
                    timeout=10.0
                )
                response.raise_for_status()
            except Exception as e:
                print(f"Failed to emit event: {e}")
```

**Test**: Mock HTTP call, verify payload

```bash
git add document-processor/src/document_processor/events.py
git commit -m "feat(document-processor): implement event emission to API

- Add EventEmitter for document_processed events
- POST to API server event webhook
- Handle network errors gracefully
- Add structured event payload with timestamps"
```

---

### Commit 11: Document processor - main processing loop
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/main.py`

**Implement**:
```python
# document-processor/src/document_processor/main.py
import asyncio
from pathlib import Path
from shared.config import Settings
from document_processor.detector import FileDetector
from document_processor.extractors.image_ocr import ClaudeVisionExtractor
from document_processor.extractors.pdf import PDFExtractor
from document_processor.storage import DocumentStorage
from document_processor.events import EventEmitter

async def process_document(file_path: Path, settings: Settings):
    """Process a single document through the pipeline."""
    print(f"Processing: {file_path}")
    
    detector = FileDetector()
    storage = DocumentStorage(settings)
    events = EventEmitter(settings)
    
    try:
        # Detect file type
        file_type, mime_type = detector.detect_type(file_path)
        
        if not detector.is_supported(file_path):
            print(f"Unsupported file type: {file_type}")
            return
        
        # Extract text
        if file_type == "image":
            extractor = ClaudeVisionExtractor(settings.claude_api_key)
            extracted = await extractor.extract_text(file_path)
        elif file_type == "pdf":
            extractor = PDFExtractor()
            extracted = await extractor.extract_text(file_path)
        
        extracted["file_type"] = file_type
        extracted["mime_type"] = mime_type
        
        # Store document
        doc_id = await storage.store_document(file_path, extracted)
        
        # Emit event
        await events.emit_document_processed(doc_id, "completed")
        
        # Move processed file out of inbox
        processed_dir = settings.inbox_path.parent / "processed"
        processed_dir.mkdir(exist_ok=True)
        file_path.rename(processed_dir / file_path.name)
        
        print(f"✓ Processed: {doc_id}")
        
    except Exception as e:
        print(f"✗ Error processing {file_path}: {e}")
        if 'doc_id' in locals():
            await events.emit_document_processed(doc_id, "failed", str(e))

async def main():
    """Scan inbox and process all documents."""
    settings = Settings()
    inbox = settings.inbox_path
    
    if not inbox.exists():
        print(f"Inbox directory does not exist: {inbox}")
        return
    
    files = list(inbox.iterdir())
    if not files:
        print("No files in inbox")
        return
    
    print(f"Found {len(files)} files to process")
    
    for file_path in files:
        if file_path.is_file():
            await process_document(file_path, settings)

if __name__ == "__main__":
    asyncio.run(main())
```

**Test**: Process sample document end-to-end

```bash
git add document-processor/src/document_processor/main.py
git commit -m "feat(document-processor): implement main processing loop

- Scan inbox for new documents
- Detect file type and extract text
- Store in database and filesystem
- Emit processing events
- Move processed files out of inbox
- Add error handling and logging"
```

---

### Commit 12: Document processor - watchdog file monitor
**Branch**: `feature/document-processor`
**Files**: `document-processor/src/document_processor/watcher.py`

**Implement**:
```python
# document-processor/src/document_processor/watcher.py
import asyncio
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from shared.config import Settings
from document_processor.main import process_document

class DocumentHandler(FileSystemEventHandler):
    def __init__(self, settings: Settings):
        self.settings = settings
        self.processing = set()
    
    def on_created(self, event):
        if event.is_directory:
            return
        
        file_path = Path(event.src_path)
        
        # Debounce: wait for file to be fully written
        time.sleep(1)
        
        if file_path in self.processing:
            return
        
        self.processing.add(file_path)
        
        # Process in async context
        asyncio.run(self._process(file_path))
        
        self.processing.discard(file_path)
    
    async def _process(self, file_path: Path):
        await process_document(file_path, self.settings)

def main():
    settings = Settings()
    inbox = settings.inbox_path
    
    if not inbox.exists():
        inbox.mkdir(parents=True)
        print(f"Created inbox directory: {inbox}")
    
    event_handler = DocumentHandler(settings)
    observer = Observer()
    observer.schedule(event_handler, str(inbox), recursive=False)
    observer.start()
    
    print(f"👀 Watching {inbox} for new documents...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    main()
```

**Test**: Drop file in inbox, verify processing

```bash
git add document-processor/src/document_processor/watcher.py
git commit -m "feat(document-processor): implement watchdog file monitoring

- Watch inbox directory for new files
- Process files immediately on creation
- Debounce to wait for complete file writes
- Prevent duplicate processing
- Add graceful shutdown on Ctrl+C"
```

---

### Commit 13: API server - database connection module
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/db/connection.py`

**Implement**:
```python
# api-server/src/api_server/db/connection.py
import duckdb
from contextlib import contextmanager
from shared.config import Settings

class Database:
    def __init__(self, settings: Settings):
        self.db_path = str(settings.database_path)
    
    @contextmanager
    def get_connection(self):
        conn = duckdb.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def execute(self, query: str, params: list = None):
        with self.get_connection() as conn:
            if params:
                return conn.execute(query, params).fetchall()
            return conn.execute(query).fetchall()
    
    def execute_one(self, query: str, params: list = None):
        with self.get_connection() as conn:
            if params:
                result = conn.execute(query, params).fetchone()
            else:
                result = conn.execute(query).fetchone()
            return result
```

**Test**: Connect to DB, run queries

```bash
git add api-server/src/api_server/db/
git commit -m "feat(api-server): implement database connection management

- Add Database class with connection pooling
- Provide context manager for safe connections
- Add execute and execute_one helper methods
- Handle connection cleanup automatically"
```

---

### Commit 14: API server - Pydantic models
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/models/*.py`

**Implement**: All Pydantic models for API (Document, Summary, Event, Query responses)

```bash
git add api-server/src/api_server/models/
git commit -m "feat(api-server): add Pydantic models for API

- Add Document model with full metadata
- Add Summary model for rollups
- Add Event model for webhook payloads
- Add Query request/response models
- Add validators and examples"
```

---

### Commit 15: API server - document service
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/services/document_service.py`

**Implement**: Document CRUD operations, search, filtering

```bash
git add api-server/src/api_server/services/document_service.py
git commit -m "feat(api-server): implement document service

- Add document listing with filters
- Implement full-text search
- Add document retrieval by ID
- Support pagination and sorting
- Add comprehensive error handling"
```

---

### Commit 16: API server - event webhook endpoint
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/api/events.py`

**Implement**:
```python
# api-server/src/api_server/api/events.py
from fastapi import APIRouter, HTTPException
from api_server.models.events import ProcessedEvent

router = APIRouter(prefix="/api/v1/events", tags=["events"])

@router.post("/document-processed")
async def handle_document_processed(event: ProcessedEvent):
    """
    Webhook receiver for document_processed events.
    Triggers MCP orchestration workflow.
    """
    # For now, just acknowledge
    # MCP integration comes in next phase
    print(f"Received event: {event.event_type} for {event.data.document_id}")
    return {"accepted": True, "document_id": event.data.document_id}
```

**Test**: POST event, verify response

```bash
git add api-server/src/api_server/api/events.py
git commit -m "feat(api-server): add event webhook endpoint

- Implement POST /api/v1/events/document-processed
- Accept ProcessedEvent payload
- Log events for debugging
- Return acknowledgment
- Prepare for MCP integration"
```

---

### Commit 17: API server - document endpoints
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/api/documents.py`

**Implement**: All document endpoints (list, get, search, upload, delete)

```bash
git add api-server/src/api_server/api/documents.py
git commit -m "feat(api-server): implement document REST endpoints

- GET /api/v1/documents - list with filters
- GET /api/v1/documents/{id} - get by ID
- POST /api/v1/documents/upload - upload new document
- DELETE /api/v1/documents/{id} - soft delete
- GET /api/v1/search - full-text search
- Add OpenAPI documentation"
```

---

### Commit 18: API server - health and status endpoints
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/api/health.py`

**Implement**:
```python
# api-server/src/api_server/api/health.py
from fastapi import APIRouter
from api_server.db.connection import Database
from shared.config import Settings

router = APIRouter(prefix="/api/v1", tags=["health"])

@router.get("/health")
async def health_check():
    settings = Settings()
    db = Database(settings)
    
    # Check database
    try:
        db.execute("SELECT 1")
        db_status = "healthy"
    except Exception as e:
        db_status = f"unhealthy: {e}"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "services": {
            "database": db_status
        }
    }

@router.get("/status")
async def status():
    return {
        "processor": {"status": "unknown"},
        "mcp_server": {"status": "unknown"},
        "api_server": {"status": "healthy"}
    }
```

**Test**: curl health endpoint

```bash
git add api-server/src/api_server/api/health.py
git commit -m "feat(api-server): add health and status endpoints

- Implement GET /api/v1/health with DB check
- Implement GET /api/v1/status for system overview
- Return service health indicators
- Add error handling for failed checks"
```

---

### Commit 19: API server - FastAPI app initialization
**Branch**: `feature/api-server`
**Files**: `api-server/src/api_server/main.py`

**Implement**:
```python
# api-server/src/api_server/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api_server.api import documents, events, health
from shared.config import Settings

def create_app() -> FastAPI:
    settings = Settings()
    
    app = FastAPI(
        title="esec API",
        description="AI Document Secretary API",
        version="0.1.0"
    )
    
    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.env == "development" else [],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Include routers
    app.include_router(documents.router)
    app.include_router(events.router)
    app.include_router(health.router)
    
    return app

app = create_app()

if __name__ == "__main__":
    import uvicorn
    settings = Settings()
    uvicorn.run(
        "api_server.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.env == "development"
    )
```

**Test**: Start API server, check OpenAPI docs

```bash
git add api-server/src/api_server/main.py
git commit -m "feat(api-server): initialize FastAPI application

- Create FastAPI app with all routers
- Add CORS middleware for development
- Configure OpenAPI documentation
- Add uvicorn server startup
- Support hot reload in development"
```

---

### Commit 20: Integration test - end-to-end pipeline
**Branch**: `feature/phase-1-infrastructure`
**Files**: `tests/integration/test_pipeline.py`

**Implement**: Test that drops file in inbox, waits for processing, checks DB and API

```bash
git add tests/integration/
git commit -m "test: add end-to-end pipeline integration test

- Test document ingestion flow
- Verify OCR extraction
- Verify database storage
- Verify API retrieval
- Check filesystem organization
- Add test fixtures and cleanup"
```

---

### Commit 21: Documentation - getting started guide
**Branch**: `feature/phase-1-infrastructure`
**Files**: `docs/GETTING_STARTED.md`

**Implement**: Step-by-step setup and first document guide

```bash
git add docs/
git commit -m "docs: add getting started guide

- Document installation steps
- Explain configuration options
- Show how to process first document
- Add troubleshooting section
- Include API usage examples"
```

---

### Commit 22: Phase 1 completion - working MVP
**Branch**: Merge to `main`

```bash
git checkout main
git merge feature/phase-1-infrastructure
git tag v0.1.0-mvp
git commit -m "feat: Phase 1 complete - basic document processing pipeline

MVP milestone achieved:
- Document processor with OCR
- API server with document endpoints
- DuckDB storage with full-text search
- Docker deployment
- End-to-end integration tests

Next: Phase 2 - MCP integration and summaries"
```

---

## Phase 2: MCP Server & AI Analysis (Commits 23-40)

### Commits 23-30: MCP Server Implementation
- MCP server scaffolding
- LLM client (Claude API)
- Categorization tool
- Extraction tool
- Prompt templates
- Tool registration
- Server initialization
- Integration tests

### Commits 31-35: API-MCP Integration
- MCP client in API server
- Event handler orchestration
- Update document with AI results
- Error handling and retries
- Performance optimization

### Commits 36-40: Summary Generation
- Summary service
- Weekly summary generation
- Summary storage and retrieval
- Summary API endpoints
- Scheduled summary jobs

---

## Phase 3: Web UI & Enhanced Features (Commits 41-60)

### Commits 41-50: React Web UI
- Project setup (Vite + React)
- API client with axios
- Document list view
- Document viewer
- Upload component
- Summary view
- Routing and navigation
- State management
- Responsive design
- Capacitor configuration

### Commits 51-55: Offline Support
- IndexedDB integration
- Service worker
- Background sync
- Offline indicator
- Conflict resolution

### Commits 56-60: Analytics & Search
- Search implementation
- Analytics dashboard
- Spending charts
- Bill tracking
- Query interface

---

## Phase 4: Production Ready (Commits 61-80)

### Commits 61-70: Multi-User Architecture
- User authentication
- Container orchestration
- API gateway
- Web UI server
- User isolation
- Backup system

### Commits 71-80: Polish & Production
- Monitoring (Prometheus)
- Logging (structured)
- Error tracking
- Performance optimization
- Security hardening
- CI/CD pipeline
- Load testing
- Documentation updates

---

## Commit Best Practices

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types**: feat, fix, docs, test, refactor, chore

**Example**:
```
feat(api-server): add document upload endpoint

- Implement POST /api/v1/documents/upload
- Support multipart/form-data
- Validate file types and size
- Return document ID on success

Closes #42
```

### Testing Strategy per Commit
- Unit tests for new functions/classes
- Integration tests for cross-component features
- Manual smoke test for UI changes
- Update docs if public API changes

### Branch Protection
- Phase branches require review before merge to main
- All tests must pass
- No direct commits to main
- Tag releases after phase completion

---

## Development Workflow

```bash
# Start new feature
git checkout main
git pull
git checkout -b feature/my-feature

# Make changes
git add <files>
git commit -m "feat: description"

# Push and create PR
git push origin feature/my-feature
# Create PR on GitHub

# After review, squash merge to main
# Tag if completing phase
git tag v0.X.0
git push --tags
```

## Next Steps

After completing Phase 1 (Commits 1-22):
1. Test the complete pipeline manually
2. Fix any bugs discovered
3. Document learnings in ARCHITECTURE.md
4. Plan Phase 2 detailed commits
5. Begin MCP server implementation

---

**Current Status**: Ready to begin Commit 1
**Estimated Time to Phase 1 Complete**: 2-3 days
**Estimated Time to Phase 2 Complete**: 3-4 days
**Estimated Time to Production Ready**: 2-3 weeks