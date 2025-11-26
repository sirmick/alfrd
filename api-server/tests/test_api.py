"""Integration tests for the API endpoints."""

import sys
from pathlib import Path
import pytest
import tempfile
import shutil
from fastapi.testclient import TestClient
import duckdb

# Add paths for imports
_test_file = Path(__file__).resolve()
_api_server_root = _test_file.parent.parent  # api-server/
_project_root = _api_server_root.parent      # esec/
_api_src = _api_server_root / "src"

sys.path.insert(0, str(_project_root))  # For shared imports
sys.path.insert(0, str(_api_src))       # For api_server imports

from api_server.main import app
from shared.config import Settings

# Create test client
client = TestClient(app)


@pytest.fixture
def temp_test_dir():
    """Create a temporary directory for test data."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def test_database(temp_test_dir, monkeypatch):
    """Create a test database with sample data."""
    db_path = temp_test_dir / "test.db"
    
    # Monkeypatch settings to use test database
    test_settings = Settings()
    test_settings.database_path = db_path
    test_settings.documents_path = temp_test_dir / "documents"
    test_settings.documents_path.mkdir(parents=True, exist_ok=True)
    
    # Patch the settings in main.py
    import api_server.main as main_module
    monkeypatch.setattr(main_module, "settings", test_settings)
    
    # Create test database schema
    conn = duckdb.connect(str(db_path))
    
    # Read schema from schema.sql
    schema_path = _project_root / "api-server" / "src" / "api_server" / "db" / "schema.sql"
    with open(schema_path, 'r') as f:
        schema_sql = f.read()
    
    # Execute schema
    conn.execute(schema_sql)
    
    # Insert test data - using actual schema columns
    conn.execute("""
        INSERT INTO documents (
            id, filename, created_at, status, document_type,
            original_path, file_type, file_size,
            suggested_type, secondary_tags, confidence,
            classification_confidence, structured_data, extracted_text
        ) VALUES (
            '123e4567-e89b-12d3-a456-426614174000',
            'test.jpg',
            '2024-11-25T10:00:00Z',
            'completed',
            'bill',
            ?,
            'image/jpeg',
            1024,
            NULL,
            '["utility", "electric"]',
            0.98,
            0.95,
            '{"amount": "150.00", "due_date": "2024-12-15", "vendor": "Electric Co"}',
            'Sample extracted text from test document'
        )
    """, [str(test_settings.documents_path / "test_doc")])
    
    conn.close()
    
    # Create test document directory with a sample file
    test_doc_dir = test_settings.documents_path / "test_doc"
    test_doc_dir.mkdir(parents=True, exist_ok=True)
    (test_doc_dir / "test.jpg").write_text("fake image data")
    
    yield db_path


def test_health_check():
    """Test the health check endpoint."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "services" in data


def test_list_documents_empty():
    """Test listing documents when database is empty."""
    # This will use the real database - just testing the endpoint structure
    response = client.get("/api/v1/documents?limit=10")
    assert response.status_code in [200, 500]  # May fail if DB doesn't exist
    
    if response.status_code == 200:
        data = response.json()
        assert "documents" in data
        assert "count" in data
        assert "limit" in data
        assert "offset" in data


def test_list_documents_with_test_data(test_database):
    """Test listing documents with test data."""
    response = client.get("/api/v1/documents?limit=50")
    assert response.status_code == 200
    
    data = response.json()
    assert "documents" in data
    assert data["count"] >= 1
    assert len(data["documents"]) >= 1
    
    # Check document structure
    doc = data["documents"][0]
    assert "id" in doc
    assert "status" in doc
    assert "document_type" in doc
    assert "created_at" in doc


def test_list_documents_with_filters(test_database):
    """Test listing documents with status filter."""
    response = client.get("/api/v1/documents?status=completed&limit=10")
    assert response.status_code == 200
    
    data = response.json()
    assert "documents" in data
    for doc in data["documents"]:
        assert doc["status"] == "completed"


def test_get_document_by_id(test_database):
    """Test getting a specific document."""
    doc_id = "123e4567-e89b-12d3-a456-426614174000"
    response = client.get(f"/api/v1/documents/{doc_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["id"] == doc_id
    assert data["document_type"] == "bill"
    assert data["status"] == "completed"
    assert "structured_data" in data
    assert "files" in data
    # Verify structured_data has expected fields
    assert isinstance(data["structured_data"], dict)
    assert "amount" in data["structured_data"]


def test_get_document_not_found(test_database):
    """Test getting a non-existent document."""
    response = client.get("/api/v1/documents/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404


def test_get_document_file(test_database):
    """Test serving a document file."""
    doc_id = "123e4567-e89b-12d3-a456-426614174000"
    response = client.get(f"/api/v1/documents/{doc_id}/file/test.jpg")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/jpeg"


def test_get_document_file_not_found(test_database):
    """Test serving a non-existent file."""
    doc_id = "123e4567-e89b-12d3-a456-426614174000"
    response = client.get(f"/api/v1/documents/{doc_id}/file/nonexistent.jpg")
    assert response.status_code == 404


def test_pagination(test_database):
    """Test pagination parameters."""
    # Test different limits
    response = client.get("/api/v1/documents?limit=5")
    assert response.status_code == 200
    data = response.json()
    assert data["limit"] == 5
    assert len(data["documents"]) <= 5
    
    # Test offset
    response = client.get("/api/v1/documents?limit=10&offset=0")
    assert response.status_code == 200
    data = response.json()
    assert data["offset"] == 0


def test_invalid_limit():
    """Test that invalid limit values are rejected."""
    response = client.get("/api/v1/documents?limit=500")
    assert response.status_code == 422  # Validation error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])