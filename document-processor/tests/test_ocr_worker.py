"""Tests for OCR Worker."""

import pytest
import asyncio
from pathlib import Path
from datetime import datetime
import json
import sys
import tempfile
import shutil
import duckdb

# Add parent directories to path
_test_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_test_dir))

from shared.config import Settings
from shared.types import DocumentStatus
from shared.constants import META_JSON_FILENAME
from document_processor.ocr_worker import OCRWorker


@pytest.fixture
def settings(tmp_path):
    """Create test settings with temporary paths."""
    # Create temp directories
    inbox = tmp_path / "inbox"
    documents = tmp_path / "documents"
    db_path = tmp_path / "test.db"
    
    inbox.mkdir()
    documents.mkdir()
    
    settings = Settings(
        inbox_path=inbox,
        documents_path=documents,
        database_path=db_path,
        ocr_workers=2,
        ocr_poll_interval=1,
        worker_batch_multiplier=2
    )
    
    # Initialize database schema
    conn = duckdb.connect(str(db_path))
    try:
        # Create minimal schema for testing
        conn.execute("""
            CREATE TABLE documents (
                id VARCHAR PRIMARY KEY,
                filename VARCHAR NOT NULL,
                original_path VARCHAR NOT NULL,
                file_type VARCHAR NOT NULL,
                file_size BIGINT,
                status VARCHAR NOT NULL,
                folder_path VARCHAR,
                extracted_text TEXT,
                extracted_text_path VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message VARCHAR
            )
        """)
    finally:
        conn.close()
    
    return settings


@pytest.fixture
def sample_folder(tmp_path):
    """Create a sample document folder with meta.json."""
    folder = tmp_path / "test_doc_folder"
    folder.mkdir()
    
    # Create meta.json
    doc_id = "test-doc-123"
    meta = {
        "id": doc_id,
        "created_at": datetime.utcnow().isoformat(),
        "documents": [
            {
                "file": "page1.txt",
                "type": "text",
                "order": 1
            },
            {
                "file": "page2.txt",
                "type": "text",
                "order": 2
            }
        ]
    }
    
    meta_file = folder / META_JSON_FILENAME
    meta_file.write_text(json.dumps(meta, indent=2))
    
    # Create sample text files
    (folder / "page1.txt").write_text("This is page 1 content.")
    (folder / "page2.txt").write_text("This is page 2 content.")
    
    return folder, doc_id, meta


@pytest.mark.asyncio
async def test_ocr_worker_initialization(settings):
    """Test OCRWorker initializes correctly."""
    worker = OCRWorker(settings)
    
    assert worker.worker_name == "OCR Worker"
    assert worker.source_status == DocumentStatus.PENDING
    assert worker.target_status == DocumentStatus.OCR_COMPLETED
    assert worker.concurrency == 2
    assert worker.poll_interval == 1
    assert worker.running == False


@pytest.mark.asyncio
async def test_ocr_worker_get_documents(settings):
    """Test OCRWorker can query documents from database."""
    worker = OCRWorker(settings)
    
    # Insert test documents
    conn = duckdb.connect(str(settings.database_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            "doc1", "test1", "/path/to/test1", "folder", 1000, DocumentStatus.PENDING.value, "/path/to/test1"
        ])
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            "doc2", "test2", "/path/to/test2", "folder", 2000, DocumentStatus.PENDING.value, "/path/to/test2"
        ])
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            "doc3", "test3", "/path/to/test3", "folder", 3000, DocumentStatus.OCR_COMPLETED.value, "/path/to/test3"
        ])
    finally:
        conn.close()
    
    # Query for pending documents
    documents = await worker.get_documents(DocumentStatus.PENDING, limit=10)
    
    assert len(documents) == 2
    assert documents[0]["id"] == "doc1"
    assert documents[1]["id"] == "doc2"
    assert all("folder_path" in doc for doc in documents)


@pytest.mark.asyncio
async def test_ocr_worker_get_documents_respects_limit(settings):
    """Test that get_documents respects the limit parameter."""
    worker = OCRWorker(settings)
    
    # Insert 5 test documents
    conn = duckdb.connect(str(settings.database_path))
    try:
        for i in range(5):
            conn.execute("""
                INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, [
                f"doc{i}", f"test{i}", f"/path/to/test{i}", "folder", 1000, 
                DocumentStatus.PENDING.value, f"/path/to/test{i}"
            ])
    finally:
        conn.close()
    
    # Query with limit
    documents = await worker.get_documents(DocumentStatus.PENDING, limit=3)
    
    assert len(documents) == 3


@pytest.mark.asyncio
async def test_ocr_worker_process_document(settings, sample_folder):
    """Test OCRWorker can process a document folder."""
    folder, doc_id, meta = sample_folder
    worker = OCRWorker(settings)
    
    # Insert document in database
    conn = duckdb.connect(str(settings.database_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, folder.name, str(folder), "folder", 1000, 
            DocumentStatus.PENDING.value, str(folder)
        ])
    finally:
        conn.close()
    
    # Process document
    document = {
        "id": doc_id,
        "filename": folder.name,
        "folder_path": str(folder),
        "original_path": str(folder)
    }
    
    result = await worker.process_document(document)
    
    assert result == True
    
    # Verify database was updated
    conn = duckdb.connect(str(settings.database_path))
    try:
        row = conn.execute("""
            SELECT status, extracted_text, extracted_text_path
            FROM documents
            WHERE id = ?
        """, [doc_id]).fetchone()
        
        assert row[0] == DocumentStatus.OCR_COMPLETED.value
        assert "This is page 1 content" in row[1]
        assert "This is page 2 content" in row[1]
        assert row[2] is not None
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_ocr_worker_handles_missing_folder(settings):
    """Test OCRWorker handles missing folder gracefully."""
    worker = OCRWorker(settings)
    doc_id = "missing-doc"
    
    # Insert document pointing to non-existent folder
    conn = duckdb.connect(str(settings.database_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, "missing", "/nonexistent/path", "folder", 1000,
            DocumentStatus.PENDING.value, "/nonexistent/path"
        ])
    finally:
        conn.close()
    
    # Process document
    document = {
        "id": doc_id,
        "filename": "missing",
        "folder_path": "/nonexistent/path",
        "original_path": "/nonexistent/path"
    }
    
    with pytest.raises(FileNotFoundError):
        await worker.process_document(document)
    
    # Verify status was set to FAILED
    conn = duckdb.connect(str(settings.database_path))
    try:
        row = conn.execute("""
            SELECT status, error_message
            FROM documents
            WHERE id = ?
        """, [doc_id]).fetchone()
        
        assert row[0] == DocumentStatus.FAILED.value
        assert row[1] is not None
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_ocr_worker_handles_invalid_meta_json(settings, tmp_path):
    """Test OCRWorker handles invalid meta.json."""
    worker = OCRWorker(settings)
    
    # Create folder with invalid meta.json
    folder = tmp_path / "invalid_doc"
    folder.mkdir()
    (folder / META_JSON_FILENAME).write_text("{invalid json")
    
    doc_id = "invalid-meta-doc"
    
    # Insert document
    conn = duckdb.connect(str(settings.database_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, folder.name, str(folder), "folder", 1000,
            DocumentStatus.PENDING.value, str(folder)
        ])
    finally:
        conn.close()
    
    # Process document
    document = {
        "id": doc_id,
        "filename": folder.name,
        "folder_path": str(folder),
        "original_path": str(folder)
    }
    
    with pytest.raises(json.JSONDecodeError):
        await worker.process_document(document)


@pytest.mark.asyncio
async def test_ocr_worker_updates_status_transitions(settings, sample_folder):
    """Test OCRWorker updates status through correct transitions."""
    folder, doc_id, meta = sample_folder
    worker = OCRWorker(settings)
    
    # Insert document
    conn = duckdb.connect(str(settings.database_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, folder.name, str(folder), "folder", 1000,
            DocumentStatus.PENDING.value, str(folder)
        ])
    finally:
        conn.close()
    
    # Track status changes
    status_history = []
    
    async def check_status():
        conn = duckdb.connect(str(settings.database_path))
        try:
            row = conn.execute("SELECT status FROM documents WHERE id = ?", [doc_id]).fetchone()
            if row:
                status_history.append(row[0])
        finally:
            conn.close()
    
    # Initial status
    await check_status()
    
    # Process document
    document = {
        "id": doc_id,
        "filename": folder.name,
        "folder_path": str(folder),
        "original_path": str(folder)
    }
    
    await worker.process_document(document)
    
    # Final status
    await check_status()
    
    # Verify transitions: PENDING -> OCR_STARTED -> OCR_COMPLETED
    assert status_history[0] == DocumentStatus.PENDING.value
    assert status_history[-1] == DocumentStatus.OCR_COMPLETED.value


@pytest.mark.asyncio
async def test_ocr_worker_creates_llm_formatted_output(settings, sample_folder):
    """Test OCRWorker creates LLM-formatted output files."""
    folder, doc_id, meta = sample_folder
    worker = OCRWorker(settings)
    
    # Insert document
    conn = duckdb.connect(str(settings.database_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, folder.name, str(folder), "folder", 1000,
            DocumentStatus.PENDING.value, str(folder)
        ])
    finally:
        conn.close()
    
    # Process document
    document = {
        "id": doc_id,
        "filename": folder.name,
        "folder_path": str(folder),
        "original_path": str(folder)
    }
    
    await worker.process_document(document)
    
    # Verify LLM-formatted file was created
    now = datetime.utcnow()
    year_month = now.strftime("%Y/%m")
    text_path = settings.documents_path / year_month / "text"
    llm_file = text_path / f"{doc_id}_llm.json"
    
    assert llm_file.exists()
    
    # Verify content
    llm_data = json.loads(llm_file.read_text())
    assert "full_text" in llm_data
    assert "document_count" in llm_data
    assert llm_data["document_count"] == 2
    assert "page 1" in llm_data["full_text"].lower()
    assert "page 2" in llm_data["full_text"].lower()


@pytest.mark.asyncio
async def test_ocr_worker_stop_gracefully(settings):
    """Test OCRWorker stops gracefully."""
    worker = OCRWorker(settings)
    
    # Start worker in background
    task = asyncio.create_task(worker.run())
    
    # Wait a bit
    await asyncio.sleep(0.1)
    
    # Stop worker
    worker.stop()
    
    # Wait for task to complete
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail("Worker did not stop within timeout")
    
    assert worker.running == False