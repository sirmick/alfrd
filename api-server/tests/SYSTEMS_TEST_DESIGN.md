# ALFRD Systems Test Design

## Overview

This document describes the design for **systems tests** (also called end-to-end tests) for ALFRD. These tests treat the entire system as a black box, interacting only through the API without any direct database manipulation.

## Key Principles

### 1. No Direct Database Access
- Tests do NOT create/modify the database directly
- Tests do NOT insert test data via SQL
- Tests do NOT load prompts programmatically
- Database is managed ONLY through existing scripts (`init-db`, etc.)

### 2. Black Box Testing
- Tests interact ONLY through the HTTP API
- Tests treat the system as a running production environment
- Tests use only the public API endpoints
- No access to internal state except through API responses

### 3. Use Production Scripts
- Use `scripts/init-db` to initialize database
- Use `scripts/start-api` to start API server
- Use `scripts/start-processor` to start document processor
- Tests verify the system works as users would experience it

## Test Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Systems Test Suite                     │
│  (Python pytest - interacts only via HTTP)               │
└─────────────────────────────────────────────────────────┘
                            ↓ HTTP only
┌─────────────────────────────────────────────────────────┐
│                    API Server (port 8000)                 │
│  - Document upload endpoints                             │
│  - Document retrieval endpoints                          │
│  - File generation endpoints                             │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│              Document Processor (background)              │
│  - OCR worker                                            │
│  - Classifier worker                                     │
│  - Summarizer worker                                     │
│  - File generator worker                                 │
└─────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────┐
│                  PostgreSQL Database                      │
│  (managed by init-db script, not tests)                 │
└─────────────────────────────────────────────────────────┘
```

## Test Setup Process

### 1. Environment Preparation
```bash
# Create clean test database (using production script)
./scripts/init-db

# This script:
# - Drops and recreates database
# - Loads schema
# - Loads prompts from YAML files
# - Loads document types
# - Creates data directories
```

### 2. Service Startup
```bash
# Start API server (using production script)
./scripts/start-api &
API_PID=$!

# Start document processor (using production script)
./scripts/start-processor &
PROCESSOR_PID=$!

# Wait for services to be ready
wait_for_api_health
```

### 3. Test Execution
```python
# Test interacts ONLY via HTTP
response = requests.post("http://localhost:8000/api/v1/documents/upload-image", 
                        files={"file": open("test.jpg", "rb")})
doc_id = response.json()["document_id"]

# Poll for completion via API
while True:
    response = requests.get(f"http://localhost:8000/api/v1/documents/{doc_id}")
    if response.json()["status"] == "completed":
        break
```

### 4. Cleanup
```bash
# Stop services
kill $API_PID $PROCESSOR_PID

# Optionally clean database
./scripts/reset-db
```

## Test Scenarios

### Scenario 1: Single Document Processing
**Objective**: Verify complete document processing pipeline

**Steps**:
1. Upload document via API
2. Poll document status until "completed"
3. Retrieve document via API
4. Verify extracted text exists
5. Verify classification is correct
6. Verify summary is generated

**Verification**:
- Document status transitions: pending → ocr_completed → classified → completed
- Extracted text length > 100 characters
- Document type is set
- Classification confidence > 50%
- Summary is generated

### Scenario 2: Multiple Documents Processing
**Objective**: Verify batch processing works correctly

**Steps**:
1. Upload 5 documents via API
2. Poll each document until all are "completed"
3. Retrieve all documents via API
4. Verify all have correct data

**Verification**:
- All 5 documents complete successfully
- Processing time is reasonable (< 2 minutes per document)
- No documents fail
- All have extracted text, classification, and summary

### Scenario 3: File Generation from Processed Documents
**Objective**: Verify file generation and aggregation

**Steps**:
1. Upload 3 documents via API
2. Wait for all documents to complete processing
3. Create file via API with document IDs
4. Poll file status until "generated"
5. Retrieve file via API
6. Verify file summary

**Verification**:
- File status transitions: pending → generated
- File contains all 3 documents
- File summary is generated (not null/empty)
- File summary mentions content from all 3 documents
- File is downloadable

### Scenario 4: End-to-End Workflow
**Objective**: Verify complete user workflow

**Steps**:
1. Upload utility bills (PG&E) via API
2. Wait for processing
3. Create "2024 Utility Bills" file via API
4. Wait for file generation
5. Download/retrieve file
6. Upload more utility bills
7. Add to existing file via API
8. Wait for file regeneration
9. Verify file updated

**Verification**:
- All documents process successfully
- File is created correctly
- File summary is comprehensive
- File can be updated with new documents
- File regenerates correctly

## Test Data

### Use AI-Generated Dataset
- Location: `test-dataset-generator/output/`
- 12 utility bills (PG&E)
- 12 property documents (rent receipts)
- 12 vehicle documents (insurance)
- 2 education documents (tuition)
- Total: 38 test documents

### Document Characteristics
- Realistic format (images with text)
- Known expected outcomes
- Varied content for classification testing
- Different document types for variety

## Success Criteria

### Test Passes If:
- ✅ All API requests succeed (200 status)
- ✅ Documents process to completion
- ✅ Extracted text is meaningful (> 100 chars)
- ✅ Classification is reasonable (confidence > 50%)
- ✅ Summaries are generated (not empty)
- ✅ Files are created successfully
- ✅ File summaries aggregate document content
- ✅ No errors or failures in processing

### Test Fails If:
- ❌ API returns error status (4xx, 5xx)
- ❌ Document processing fails (status = "failed")
- ❌ Document stays in intermediate state (timeout)
- ❌ Extracted text is empty or too short
- ❌ Classification confidence is too low
- ❌ Summary is not generated
- ❌ File creation fails
- ❌ File summary is empty or generic

## Implementation

### Directory Structure
```
api-server/systems-tests/
├── README.md              # This file
├── conftest.py           # Pytest fixtures for setup/teardown
├── test_systems.py       # Main systems test suite
├── utils.py              # Helper functions
└── run_systems_tests.sh  # Script to run full suite
```

### Key Test Functions

```python
def test_single_document_processing():
    """Test uploading and processing a single document."""
    # Upload via API
    doc_id = upload_document("test-dataset-generator/output/bills/pge_2024_01.jpg")
    
    # Wait for completion (via API polling)
    doc = wait_for_completion(doc_id, timeout=300)
    
    # Verify via API responses
    assert doc["status"] == "completed"
    assert len(doc["extracted_text"]) > 100
    assert doc["document_type"] == "utility_bill"
    assert doc["classification_confidence"] > 0.5
    assert len(doc["summary"]) > 0

def test_file_generation():
    """Test creating a file from multiple processed documents."""
    # Upload and process multiple documents
    doc_ids = []
    for i in range(3):
        doc_id = upload_document(f"test-dataset-generator/output/bills/pge_2024_0{i+1}.jpg")
        wait_for_completion(doc_id)
        doc_ids.append(doc_id)
    
    # Create file via API
    file_id = create_file(doc_ids, document_type="bill", tags=["utility", "pge"])
    
    # Wait for file generation
    file_data = wait_for_file_generation(file_id, timeout=300)
    
    # Verify via API responses
    assert file_data["file"]["status"] == "generated"
    assert len(file_data["documents"]) == 3
    assert file_data["file"]["file_summary"] is not None
    assert len(file_data["file"]["file_summary"]) > 100
```

### Helper Functions

```python
def upload_document(filepath: str) -> str:
    """Upload document via API and return document ID."""
    with open(filepath, "rb") as f:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/documents/upload-image",
            files={"file": (filepath, f, "image/jpeg")}
        )
    response.raise_for_status()
    return response.json()["document_id"]

def wait_for_completion(doc_id: str, timeout: int = 300) -> dict:
    """Poll document status until completed or timeout."""
    start = time.time()
    while time.time() - start < timeout:
        response = requests.get(f"{API_BASE_URL}/api/v1/documents/{doc_id}")
        response.raise_for_status()
        doc = response.json()
        
        if doc["status"] == "completed":
            return doc
        elif doc["status"] == "failed":
            raise Exception(f"Document processing failed: {doc.get('error_message')}")
        
        time.sleep(5)
    
    raise TimeoutError(f"Document did not complete within {timeout} seconds")

def create_file(doc_ids: list[str], document_type: str, tags: list[str]) -> str:
    """Create file via API and return file ID."""
    response = requests.post(
        f"{API_BASE_URL}/api/v1/files/create",
        params={
            "document_type": document_type,
            "tags": tags,
            "document_ids": doc_ids
        }
    )
    response.raise_for_status()
    return response.json()["file"]["id"]
```

## Running Tests

### Manual Run
```bash
# 1. Setup (one-time)
./scripts/init-db

# 2. Start services
./scripts/start-api &
./scripts/start-processor &

# 3. Run tests
cd api-server/systems-tests
pytest test_systems.py -v -s

# 4. Cleanup
pkill -f api_server
pkill -f document_processor
```

### Automated Run
```bash
# Use test runner script
./api-server/systems-tests/run_systems_tests.sh

# This script:
# 1. Initializes test database
# 2. Starts services
# 3. Runs tests
# 4. Stops services
# 5. Reports results
```

## Advantages of This Approach

### 1. Tests Real System
- Tests exactly what users experience
- No mocking or test doubles
- Catches integration issues
- Verifies end-to-end workflows

### 2. Production-Like
- Uses same scripts as production
- Same database initialization
- Same service startup
- Same API interactions

### 3. Independent
- Tests don't depend on internals
- Can run against any environment
- No coupling to implementation
- Survives refactoring

### 4. Comprehensive
- Tests all layers together
- Verifies complete workflows
- Catches configuration issues
- Tests performance under load

## Disadvantages

### 1. Slower
- Must start real services
- Must wait for real processing
- Each test takes minutes
- Can't run in parallel easily

### 2. Requires Infrastructure
- Needs PostgreSQL running
- Needs AWS credentials
- Needs test data files
- Needs enough disk space

### 3. Harder to Debug
- Can't inspect internal state
- Must rely on API responses
- Harder to isolate failures
- Logs are in multiple places

## Best Practices

1. **Test Isolation**: Each test should clean up after itself
2. **Timeouts**: Use reasonable timeouts (5 min per document)
3. **Retries**: Retry transient failures (network issues)
4. **Assertions**: Verify outputs thoroughly, not just status
5. **Logging**: Log all API requests/responses for debugging
6. **Data**: Use known test data with predictable outcomes
7. **Performance**: Track test execution time
8. **Cleanup**: Always stop services and clean database

## Future Enhancements

- [ ] Parallel test execution
- [ ] Performance benchmarking
- [ ] Load testing (100+ documents)
- [ ] Failure injection testing
- [ ] Multi-environment testing (dev, staging, prod)
- [ ] Continuous testing in CI/CD
- [ ] Test result dashboards
- [ ] Automated test data generation

---

**Last Updated**: 2025-12-02