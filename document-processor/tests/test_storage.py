"""Tests for document storage module."""

import pytest
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
import json
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.config import Settings
from shared.types import DocumentStatus
from document_processor.storage import DocumentStorage


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    temp_root = Path(tempfile.mkdtemp())
    
    # Create structure
    data_dir = temp_root / "data"
    inbox_dir = data_dir / "inbox"
    documents_dir = data_dir / "documents"
    db_path = data_dir / "test.db"
    
    inbox_dir.mkdir(parents=True)
    documents_dir.mkdir(parents=True)
    
    yield {
        'root': temp_root,
        'data': data_dir,
        'inbox': inbox_dir,
        'documents': documents_dir,
        'db_path': db_path
    }
    
    # Cleanup
    shutil.rmtree(temp_root)


@pytest.fixture
def test_settings(temp_dirs):
    """Create test settings with temporary paths."""
    class TestSettings(Settings):
        def __init__(self):
            # Override settings for testing
            self.database_path = temp_dirs['db_path']
            self.inbox_path = temp_dirs['inbox']
            self.documents_path = temp_dirs['documents']
            self.summaries_path = temp_dirs['data'] / "summaries"
            self.aws_region = "us-east-1"
            self.env = "test"
    
    return TestSettings()


@pytest.fixture
def initialized_db(test_settings):
    """Initialize database with schema."""
    import duckdb
    
    # Read schema
    schema_path = Path(__file__).parent.parent.parent.parent / "api-server" / "src" / "api_server" / "db" / "schema.sql"
    
    if not schema_path.exists():
        pytest.skip("Schema file not found")
    
    with open(schema_path) as f:
        schema_sql = f.read()
    
    # Create database
    conn = duckdb.connect(str(test_settings.database_path))
    conn.executescript(schema_sql)
    conn.close()
    
    return test_settings


@pytest.fixture
def sample_document_folder(temp_dirs):
    """Create a sample document folder with meta.json."""
    folder = temp_dirs['inbox'] / "test-document"
    folder.mkdir()
    
    # Create meta.json
    meta = {
        "id": "test-doc-123",
        "created_at": datetime.utcnow().isoformat() + "Z",
        "documents": [
            {"file": "page1.txt", "type": "text", "order": 1}
        ],
        "metadata": {
            "source": "test",
            "tags": ["test"]
        }
    }
    
    meta_file = folder / "meta.json"
    with open(meta_file, 'w') as f:
        json.dump(meta, f, indent=2)
    
    # Create test file
    test_file = folder / "page1.txt"
    test_file.write_text("This is a test document.")
    
    return folder, meta


class TestDocumentStorage:
    """Test document storage functionality."""
    
    def test_database_connection(self, initialized_db):
        """Test that we can connect to the database."""
        storage = DocumentStorage(initialized_db)
        assert storage.db_path == initialized_db.database_path
        assert initialized_db.database_path.exists()
    
    @pytest.mark.asyncio
    async def test_store_document_folder(self, initialized_db, sample_document_folder):
        """Test storing a document folder."""
        storage = DocumentStorage(initialized_db)
        folder_path, meta = sample_document_folder
        
        extracted_documents = [{
            'file': 'page1.txt',
            'type': 'text',
            'order': 1,
            'extracted_text': 'This is a test document.',
            'confidence': 1.0,
            'metadata': {'extractor': 'test'}
        }]
        
        llm_formatted = {
            'full_text': 'This is a test document.',
            'blocks_by_document': None,
            'document_count': 1,
            'total_chars': 24,
            'avg_confidence': 1.0
        }
        
        # Store the document
        doc_id = await storage.store_document_folder(
            folder_path=folder_path,
            doc_id=meta['id'],
            meta=meta,
            extracted_documents=extracted_documents,
            llm_formatted=llm_formatted
        )
        
        assert doc_id == "test-doc-123"
        
        # Verify files were created
        year_month = datetime.utcnow().strftime("%Y/%m")
        text_file = initialized_db.documents_path / year_month / "text" / f"{doc_id}.txt"
        llm_file = initialized_db.documents_path / year_month / "text" / f"{doc_id}_llm.json"
        
        assert text_file.exists()
        assert llm_file.exists()
        
        # Verify content
        assert text_file.read_text() == 'This is a test document.'
        
        llm_data = json.loads(llm_file.read_text())
        assert llm_data['document_count'] == 1
        assert llm_data['avg_confidence'] == 1.0
    
    @pytest.mark.asyncio
    async def test_update_document_status(self, initialized_db, sample_document_folder):
        """Test updating document status."""
        storage = DocumentStorage(initialized_db)
        folder_path, meta = sample_document_folder
        
        # First store a document
        extracted_documents = [{
            'file': 'page1.txt',
            'type': 'text',
            'order': 1,
            'extracted_text': 'Test',
            'confidence': 1.0,
            'metadata': {}
        }]
        
        llm_formatted = {
            'full_text': 'Test',
            'blocks_by_document': None,
            'document_count': 1,
            'total_chars': 4,
            'avg_confidence': 1.0
        }
        
        doc_id = await storage.store_document_folder(
            folder_path=folder_path,
            doc_id=meta['id'],
            meta=meta,
            extracted_documents=extracted_documents,
            llm_formatted=llm_formatted
        )
        
        # Update status
        await storage.update_document_status(doc_id, DocumentStatus.COMPLETED)
        
        # Verify in database
        import duckdb
        conn = duckdb.connect(str(initialized_db.database_path))
        result = conn.execute(
            "SELECT status FROM documents WHERE id = ?",
            [doc_id]
        ).fetchone()
        conn.close()
        
        assert result[0] == DocumentStatus.COMPLETED
    
    @pytest.mark.asyncio
    async def test_update_document_status_with_error(self, initialized_db, sample_document_folder):
        """Test updating document status with error message."""
        storage = DocumentStorage(initialized_db)
        folder_path, meta = sample_document_folder
        
        # Store document
        extracted_documents = [{
            'file': 'page1.txt',
            'type': 'text',
            'order': 1,
            'extracted_text': 'Test',
            'confidence': 1.0,
            'metadata': {}
        }]
        
        llm_formatted = {
            'full_text': 'Test',
            'blocks_by_document': None,
            'document_count': 1,
            'total_chars': 4,
            'avg_confidence': 1.0
        }
        
        doc_id = await storage.store_document_folder(
            folder_path=folder_path,
            doc_id=meta['id'],
            meta=meta,
            extracted_documents=extracted_documents,
            llm_formatted=llm_formatted
        )
        
        # Update with error
        error_msg = "Test error message"
        await storage.update_document_status(doc_id, DocumentStatus.FAILED, error_msg)
        
        # Verify in database
        import duckdb
        conn = duckdb.connect(str(initialized_db.database_path))
        result = conn.execute(
            "SELECT status, error_message FROM documents WHERE id = ?",
            [doc_id]
        ).fetchone()
        conn.close()
        
        assert result[0] == DocumentStatus.FAILED
        assert result[1] == error_msg
    
    @pytest.mark.asyncio
    async def test_get_document(self, initialized_db, sample_document_folder):
        """Test retrieving document metadata."""
        storage = DocumentStorage(initialized_db)
        folder_path, meta = sample_document_folder
        
        # Store document
        extracted_documents = [{
            'file': 'page1.txt',
            'type': 'text',
            'order': 1,
            'extracted_text': 'Test content',
            'confidence': 1.0,
            'metadata': {}
        }]
        
        llm_formatted = {
            'full_text': 'Test content',
            'blocks_by_document': None,
            'document_count': 1,
            'total_chars': 12,
            'avg_confidence': 1.0
        }
        
        doc_id = await storage.store_document_folder(
            folder_path=folder_path,
            doc_id=meta['id'],
            meta=meta,
            extracted_documents=extracted_documents,
            llm_formatted=llm_formatted
        )
        
        # Retrieve document
        doc = await storage.get_document(doc_id)
        
        assert doc is not None
        assert doc['id'] == doc_id
        assert doc['filename'] == folder_path.name
        assert doc['file_type'] == 'folder'
        assert doc['extracted_text'] == 'Test content'


if __name__ == "__main__":
    pytest.main([__file__, "-v"])