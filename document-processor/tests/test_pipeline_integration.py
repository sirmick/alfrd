"""Integration test for complete document processing pipeline."""

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
from document_processor.workers import WorkerPool
from document_processor.ocr_worker import OCRWorker


@pytest.fixture
def test_env(tmp_path):
    """Create test environment with database and directories."""
    # Create directories
    inbox = tmp_path / "inbox"
    documents = tmp_path / "documents"
    db_path = tmp_path / "test.db"
    
    inbox.mkdir()
    documents.mkdir()
    
    # Create settings
    settings = Settings(
        inbox_path=inbox,
        documents_path=documents,
        database_path=db_path,
        ocr_workers=1,
        ocr_poll_interval=1,
        worker_batch_multiplier=2
    )
    
    # Initialize database schema
    conn = duckdb.connect(str(db_path))
    try:
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
                document_type VARCHAR,
                classification_confidence FLOAT,
                classification_reasoning TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                error_message VARCHAR
            )
        """)
    finally:
        conn.close()
    
    return settings, inbox, documents, db_path


@pytest.mark.asyncio
async def test_ocr_worker_end_to_end(test_env):
    """Test OCR worker processes a document from pending to ocr_completed."""
    settings, inbox, documents, db_path = test_env
    
    # Create a test document folder
    doc_folder = inbox / "test_document"
    doc_folder.mkdir()
    
    doc_id = "test-doc-001"
    
    # Create meta.json
    meta = {
        "id": doc_id,
        "created_at": datetime.utcnow().isoformat(),
        "documents": [
            {"file": "page1.txt", "type": "text", "order": 1}
        ]
    }
    (doc_folder / META_JSON_FILENAME).write_text(json.dumps(meta, indent=2))
    
    # Create sample text file
    (doc_folder / "page1.txt").write_text("This is a test utility bill from PG&E.\nAmount due: $125.50")
    
    # Insert document in pending status
    conn = duckdb.connect(str(db_path))
    try:
        conn.execute("""
            INSERT INTO documents (id, filename, original_path, file_type, file_size, status, folder_path)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            doc_id, doc_folder.name, str(doc_folder), "folder", 1000,
            DocumentStatus.PENDING.value, str(doc_folder)
        ])
    finally:
        conn.close()
    
    # Create OCR worker
    worker = OCRWorker(settings)
    
    # Process the document
    documents_to_process = await worker.get_documents(DocumentStatus.PENDING, limit=10)
    assert len(documents_to_process) == 1
    assert documents_to_process[0]["id"] == doc_id
    
    # Process
    result = await worker.process_document(documents_to_process[0])
    assert result == True
    
    # Verify status updated
    conn = duckdb.connect(str(db_path))
    try:
        row = conn.execute("""
            SELECT status, extracted_text
            FROM documents
            WHERE id = ?
        """, [doc_id]).fetchone()
        
        assert row[0] == DocumentStatus.OCR_COMPLETED.value
        assert "utility bill" in row[1].lower()
        assert "125.50" in row[1]
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_worker_pool_manages_ocr_worker(test_env):
    """Test WorkerPool can start and stop OCR worker."""
    settings, inbox, documents, db_path = test_env
    
    # Create worker pool
    pool = WorkerPool()
    worker = OCRWorker(settings)
    pool.add_worker(worker)
    
    # Start pool in background
    task = asyncio.create_task(pool.start())
    
    # Wait a bit
    await asyncio.sleep(0.5)
    
    # Stop pool
    await pool.stop()
    
    # Verify task completed
    try:
        await asyncio.wait_for(task, timeout=2.0)
    except asyncio.TimeoutError:
        pytest.fail("Worker pool did not stop within timeout")


@pytest.mark.asyncio
async def test_empty_queue_does_not_block(test_env):
    """Test worker handles empty queue gracefully."""
    settings, inbox, documents, db_path = test_env
    
    worker = OCRWorker(settings)
    
    # Query empty queue
    documents_to_process = await worker.get_documents(DocumentStatus.PENDING, limit=10)
    assert len(documents_to_process) == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])