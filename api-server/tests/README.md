# API Server Tests

Integration tests for the ALFRD API endpoints.

## Running Tests

```bash
# From project root
cd api-server
pytest tests/test_api.py -v

# Or with coverage
pytest tests/test_api.py -v --cov=src/api_server --cov-report=html
```

## Test Coverage

The test suite covers:

### Endpoint Tests
- ✅ `GET /api/v1/health` - Health check
- ✅ `GET /api/v1/documents` - List documents with pagination
- ✅ `GET /api/v1/documents?status=X` - List with filters
- ✅ `GET /api/v1/documents/{id}` - Get specific document
- ✅ `GET /api/v1/documents/{id}/file/{filename}` - Serve files

### Test Scenarios
- Empty database handling
- Document listing with test data
- Filtering by status and type
- Pagination (limit, offset)
- Document detail retrieval
- File serving with correct MIME types
- 404 handling for missing documents/files
- Validation errors for invalid parameters

## Test Structure

### Fixtures

**`temp_test_dir`** - Creates temporary directory for test data
**`test_database`** - Sets up test database with schema and sample data

### Sample Test Data

Each test run creates:
- Fresh DuckDB database with full schema
- Sample document with ID `123e4567-e89b-12d3-a456-426614174000`
- Document type: `bill`
- Status: `completed`
- Test file: `test.jpg`

## Why These Tests?

This suite catches:
1. **Schema mismatches** - Column name errors like `ocr_confidence` vs `confidence`
2. **Missing columns** - SQL queries referencing non-existent fields
3. **JSON parsing issues** - secondary_tags, key_data parsing
4. **File serving errors** - Path validation, MIME types
5. **Validation errors** - Query parameter constraints
6. **404 handling** - Missing documents/files

## Test Philosophy

These are **integration tests**, not unit tests:
- Use real FastAPI TestClient
- Create real DuckDB database
- Test full request/response cycle
- Use fixtures for test isolation

## Adding New Tests

When adding new API endpoints:

1. Add endpoint handler to `main.py`
2. Add test function to `test_api.py`
3. Use `test_database` fixture for data
4. Test success path (200)
5. Test error paths (404, 422, 500)
6. Verify response structure

Example:
```python
def test_new_endpoint(test_database):
    """Test description."""
    response = client.get("/api/v1/new-endpoint")
    assert response.status_code == 200
    data = response.json()
    assert "expected_field" in data
```

## Dependencies

The tests require:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `httpx` - TestClient dependency

Install with:
```bash
pip install pytest pytest-asyncio httpx