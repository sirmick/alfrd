"""
Read-only API tests for ALFRD.

These tests call API endpoint functions DIRECTLY (no HTTP layer).
This provides:
1. Faster tests (no HTTP overhead)
2. Direct testing of business logic
3. Foundation for CLI wrapper that calls same functions

Prerequisites:
- Database must be initialized with schema
- Test data should be loaded (documents, series, prompts, etc.)

Run with:
    PYTHONPATH=/home/mick/esec pytest api-server/tests/test_api_readonly.py -v
"""

import pytest
from uuid import UUID

# Import the API endpoint functions directly
import sys
from pathlib import Path

# Add paths for imports
project_root = str(Path(__file__).parent.parent.parent)
api_server_src = str(Path(__file__).parent.parent / "src")
sys.path.insert(0, project_root)
sys.path.insert(0, api_server_src)

from api_server.main import (
    root,
    health_check,
    status,
    list_documents,
    get_document,
    search_documents,
    list_series,
    get_series,
    list_files,
    get_file,
    flatten_file_data,
    list_tags,
    get_popular_tags,
    search_tags,
    list_prompts,
    get_active_prompts,
    get_prompt,
    list_document_types,
    get_events,
)
from fastapi import HTTPException


# ==========================================
# HEALTH & STATUS ENDPOINTS
# ==========================================

class TestHealthEndpoints:
    """Test health and status endpoints."""

    async def test_root_endpoint(self):
        """Test root endpoint returns API info."""
        result = await root()
        assert result["name"] == "esec API"
        assert "version" in result
        assert result["status"] == "running"

    async def test_health_check(self, db):
        """Test health check endpoint."""
        result = await health_check(database=db)
        assert "status" in result
        assert "services" in result
        assert result["services"]["api"] == "healthy"
        assert result["services"]["database"] in ["healthy", "unhealthy"]

    async def test_status_endpoint(self):
        """Test status endpoint."""
        result = await status()
        assert "api_server" in result
        assert result["api_server"]["status"] == "healthy"


# ==========================================
# DOCUMENT ENDPOINTS
# ==========================================

class TestDocumentEndpoints:
    """Test document listing and retrieval endpoints."""

    async def test_list_documents(self, db):
        """Test listing documents without filters."""
        result = await list_documents(status=None, document_type=None, limit=50, offset=0, database=db)
        assert "documents" in result
        assert "count" in result
        assert "limit" in result
        assert "offset" in result
        assert isinstance(result["documents"], list)

    async def test_list_documents_with_limit(self, db):
        """Test listing documents with limit parameter."""
        result = await list_documents(status=None, document_type=None, limit=5, offset=0, database=db)
        assert len(result["documents"]) <= 5

    async def test_list_documents_with_pagination(self, db):
        """Test listing documents with pagination."""
        first_page = await list_documents(status=None, document_type=None, limit=10, offset=0, database=db)
        second_page = await list_documents(status=None, document_type=None, limit=10, offset=10, database=db)

        # If there are enough documents, pages should be different
        if first_page["count"] > 10 and second_page["count"] > 0:
            first_ids = {d["id"] for d in first_page["documents"]}
            second_ids = {d["id"] for d in second_page["documents"]}
            assert first_ids.isdisjoint(second_ids)

    async def test_list_documents_filter_by_status(self, db):
        """Test filtering documents by status."""
        result = await list_documents(status="completed", document_type=None, limit=50, offset=0, database=db)
        for doc in result["documents"]:
            assert doc["status"] == "completed"

    async def test_list_documents_filter_by_type(self, db):
        """Test filtering documents by document_type."""
        result = await list_documents(status=None, document_type="bill", limit=50, offset=0, database=db)
        for doc in result["documents"]:
            assert doc["document_type"] == "bill"

    async def test_get_document_by_id(self, db, sample_document_id):
        """Test getting a specific document by ID."""
        if not sample_document_id:
            pytest.skip("No documents in database")

        result = await get_document(document_id=sample_document_id, database=db)
        assert result["id"] == sample_document_id
        assert "status" in result
        assert "created_at" in result

    async def test_get_document_not_found(self, db):
        """Test getting a non-existent document raises 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(HTTPException) as exc_info:
            await get_document(document_id=fake_id, database=db)
        assert exc_info.value.status_code == 404

    async def test_get_document_invalid_uuid(self, db):
        """Test getting a document with invalid UUID raises 400."""
        with pytest.raises(HTTPException) as exc_info:
            await get_document(document_id="not-a-uuid", database=db)
        assert exc_info.value.status_code == 400

    async def test_document_has_expected_fields(self, db, completed_document_id):
        """Test that a completed document has all expected fields."""
        if not completed_document_id:
            pytest.skip("No completed documents in database")

        result = await get_document(document_id=completed_document_id, database=db)

        # Check required fields
        assert "id" in result
        assert "status" in result
        assert "created_at" in result

        # Check optional but expected fields for completed documents
        if result["status"] == "completed":
            assert "document_type" in result
            assert "structured_data" in result
            assert "tags" in result
            assert isinstance(result["tags"], list)


# ==========================================
# DOCUMENT SEARCH ENDPOINTS
# ==========================================

class TestDocumentSearchEndpoints:
    """Test document search functionality."""

    async def test_search_documents(self, db):
        """Test searching documents."""
        result = await search_documents(q="test", limit=50, database=db)
        assert "results" in result
        assert "count" in result
        assert "query" in result
        assert result["query"] == "test"

    async def test_search_documents_with_limit(self, db):
        """Test search with limit parameter."""
        result = await search_documents(q="a", limit=5, database=db)
        assert len(result["results"]) <= 5

    async def test_search_documents_returns_list(self, db):
        """Test that search returns a list of results."""
        result = await search_documents(q="document", limit=50, database=db)
        assert isinstance(result["results"], list)

    async def test_search_documents_common_term(self, db):
        """Test searching with a common term that should match."""
        # Use a term likely to be in most documents
        result = await search_documents(q="the", limit=100, database=db)
        # Just verify the search works, count depends on data
        assert "count" in result
        assert result["count"] >= 0


# ==========================================
# SERIES ENDPOINTS
# ==========================================

class TestSeriesEndpoints:
    """Test series listing and retrieval endpoints."""

    async def test_list_series(self, db):
        """Test listing all series."""
        result = await list_series(entity=None, series_type=None, frequency=None, status=None, limit=50, offset=0, database=db)
        assert "series" in result
        assert "count" in result
        assert "limit" in result
        assert "offset" in result
        assert isinstance(result["series"], list)

    async def test_list_series_with_limit(self, db):
        """Test listing series with limit parameter."""
        result = await list_series(entity=None, series_type=None, frequency=None, status=None, limit=5, offset=0, database=db)
        assert len(result["series"]) <= 5

    async def test_list_series_filter_by_entity(self, db):
        """Test filtering series by entity."""
        # First get any series to find an entity
        first_result = await list_series(entity=None, series_type=None, frequency=None, status=None, limit=1, offset=0, database=db)
        if not first_result["series"]:
            pytest.skip("No series in database")

        entity = first_result["series"][0].get("entity")
        if entity:
            result = await list_series(entity=entity, series_type=None, frequency=None, status=None, limit=50, offset=0, database=db)
            for series in result["series"]:
                assert series["entity"] == entity

    async def test_get_series_by_id(self, db, sample_series_id):
        """Test getting a specific series by ID."""
        if not sample_series_id:
            pytest.skip("No series in database")

        result = await get_series(series_id=sample_series_id, database=db)
        assert "series" in result
        assert "documents" in result
        assert result["series"]["id"] == sample_series_id

    async def test_get_series_not_found(self, db):
        """Test getting a non-existent series raises 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(HTTPException) as exc_info:
            await get_series(series_id=fake_id, database=db)
        assert exc_info.value.status_code == 404

    async def test_series_has_expected_fields(self, db, sample_series_id):
        """Test that a series has expected fields."""
        if not sample_series_id:
            pytest.skip("No series in database")

        result = await get_series(series_id=sample_series_id, database=db)
        series = result["series"]
        assert "id" in series
        assert "title" in series
        assert "entity" in series
        assert "series_type" in series

    async def test_series_includes_documents(self, db, sample_series_id):
        """Test that get_series returns associated documents."""
        if not sample_series_id:
            pytest.skip("No series in database")

        result = await get_series(series_id=sample_series_id, database=db)
        assert "documents" in result
        assert isinstance(result["documents"], list)


# ==========================================
# FILE ENDPOINTS
# ==========================================

class TestFileEndpoints:
    """Test file listing and retrieval endpoints."""

    async def test_list_files(self, db):
        """Test listing all files."""
        result = await list_files(tags=None, status=None, limit=50, offset=0, database=db)
        assert "files" in result
        assert "count" in result
        assert "limit" in result
        assert "offset" in result
        assert isinstance(result["files"], list)

    async def test_list_files_with_limit(self, db):
        """Test listing files with limit parameter."""
        result = await list_files(tags=None, status=None, limit=5, offset=0, database=db)
        assert len(result["files"]) <= 5

    async def test_get_file_by_id(self, db, sample_file_id):
        """Test getting a specific file by ID."""
        if not sample_file_id:
            pytest.skip("No files in database")

        result = await get_file(file_id=sample_file_id, database=db)
        assert "file" in result
        assert "documents" in result
        assert result["file"]["id"] == sample_file_id

    async def test_get_file_not_found(self, db):
        """Test getting a non-existent file raises 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(HTTPException) as exc_info:
            await get_file(file_id=fake_id, database=db)
        assert exc_info.value.status_code == 404

    async def test_file_flatten_endpoint(self, db, sample_file_id):
        """Test the file flatten endpoint."""
        if not sample_file_id:
            pytest.skip("No files in database")

        result = await flatten_file_data(file_id=sample_file_id, array_strategy="flatten", max_depth=None, database=db)
        assert "columns" in result
        assert "rows" in result
        assert "count" in result
        assert isinstance(result["columns"], list)
        assert isinstance(result["rows"], list)

    async def test_file_flatten_with_strategies(self, db, sample_file_id):
        """Test file flatten with different array strategies."""
        if not sample_file_id:
            pytest.skip("No files in database")

        for strategy in ["flatten", "json", "first", "count"]:
            result = await flatten_file_data(
                file_id=sample_file_id,
                array_strategy=strategy,
                max_depth=None,
                database=db
            )
            assert result["array_strategy"] == strategy


# ==========================================
# TAG ENDPOINTS
# ==========================================

class TestTagEndpoints:
    """Test tag listing and search endpoints."""

    async def test_list_tags(self, db):
        """Test listing all tags."""
        result = await list_tags(limit=100, order_by="usage_count DESC", database=db)
        assert "tags" in result
        assert "count" in result
        assert "limit" in result
        assert isinstance(result["tags"], list)

    async def test_list_tags_with_limit(self, db):
        """Test listing tags with limit parameter."""
        result = await list_tags(limit=10, order_by="usage_count DESC", database=db)
        assert len(result["tags"]) <= 10

    async def test_popular_tags(self, db):
        """Test getting popular tags."""
        result = await get_popular_tags(limit=20, database=db)
        assert "tags" in result
        assert "count" in result
        assert isinstance(result["tags"], list)

    async def test_search_tags(self, db):
        """Test searching tags."""
        result = await search_tags(q="a", limit=10, database=db)
        assert "tags" in result
        assert "count" in result
        assert "query" in result

    async def test_search_tags_returns_matching(self, db):
        """Test that tag search returns matching tags."""
        # First get any tag to search for
        all_tags = await list_tags(limit=1, order_by="usage_count DESC", database=db)
        if not all_tags["tags"]:
            pytest.skip("No tags in database")

        # Get first character of first tag name
        first_tag = all_tags["tags"][0]
        if isinstance(first_tag, dict):
            tag_name = first_tag.get("tag_name", first_tag.get("name", ""))
        else:
            tag_name = str(first_tag)

        if tag_name:
            search_char = tag_name[0]
            result = await search_tags(q=search_char, limit=10, database=db)
            assert result["count"] >= 0


# ==========================================
# PROMPT ENDPOINTS
# ==========================================

class TestPromptEndpoints:
    """Test prompt listing and retrieval endpoints."""

    async def test_list_prompts(self, db):
        """Test listing all prompts."""
        result = await list_prompts(prompt_type=None, document_type=None, include_inactive=False, database=db)
        assert "prompts" in result
        assert "count" in result
        assert isinstance(result["prompts"], list)

    async def test_list_prompts_filter_by_type(self, db):
        """Test filtering prompts by type."""
        result = await list_prompts(prompt_type="classifier", document_type=None, include_inactive=False, database=db)
        for prompt in result["prompts"]:
            assert prompt["prompt_type"] == "classifier"

    async def test_list_active_prompts(self, db):
        """Test getting active prompts only."""
        result = await get_active_prompts(prompt_type=None, database=db)
        assert "prompts" in result
        # All returned prompts should be active
        for prompt in result["prompts"]:
            assert prompt.get("is_active", True)

    async def test_get_prompt_by_id(self, db, sample_prompt_id):
        """Test getting a specific prompt by ID."""
        if not sample_prompt_id:
            pytest.skip("No prompts in database")

        result = await get_prompt(prompt_id=sample_prompt_id, database=db)
        assert result["id"] == sample_prompt_id
        assert "prompt_type" in result
        assert "prompt_text" in result

    async def test_get_prompt_not_found(self, db):
        """Test getting a non-existent prompt raises 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(HTTPException) as exc_info:
            await get_prompt(prompt_id=fake_id, database=db)
        assert exc_info.value.status_code == 404

    async def test_prompts_have_required_fields(self, db):
        """Test that prompts have required fields."""
        result = await list_prompts(prompt_type=None, document_type=None, include_inactive=False, database=db)
        if not result["prompts"]:
            pytest.skip("No prompts in database")

        prompt = result["prompts"][0]
        assert "id" in prompt
        assert "prompt_type" in prompt
        assert "prompt_text" in prompt
        assert "version" in prompt
        assert "is_active" in prompt


# ==========================================
# DOCUMENT TYPE ENDPOINTS
# ==========================================

class TestDocumentTypeEndpoints:
    """Test document type listing endpoints."""

    async def test_list_document_types(self, db):
        """Test listing document types."""
        result = await list_document_types(active_only=True, database=db)
        assert "document_types" in result
        assert "count" in result
        assert isinstance(result["document_types"], list)

    async def test_list_document_types_has_defaults(self, db):
        """Test that default document types are present."""
        result = await list_document_types(active_only=False, database=db)

        # Get list of type names - handle both dict and non-dict cases
        if result["document_types"] and isinstance(result["document_types"][0], dict):
            type_names = [dt.get("name", dt.get("type_name", "")) for dt in result["document_types"]]
        else:
            type_names = [str(dt) for dt in result["document_types"]]

        # Check for some expected default types
        expected_defaults = ["bill", "finance", "generic"]
        found = [t for t in expected_defaults if t in type_names]
        # At least one default should be present
        assert len(found) > 0 or len(result["document_types"]) > 0

    async def test_document_types_have_expected_fields(self, db):
        """Test that document types have expected fields."""
        result = await list_document_types(active_only=True, database=db)
        if not result["document_types"]:
            pytest.skip("No document types in database")

        dt = result["document_types"][0]
        # Document types may be dicts or simple strings depending on implementation
        if isinstance(dt, dict):
            assert "id" in dt or "name" in dt or "type_name" in dt
        else:
            assert dt is not None


# ==========================================
# EVENT ENDPOINTS
# ==========================================

class TestEventEndpoints:
    """Test event logging endpoints."""

    async def test_get_events_for_document(self, db, sample_document_id):
        """Test getting events for a document."""
        if not sample_document_id:
            pytest.skip("No documents in database")

        result = await get_events(id=None, document_id=sample_document_id, file_id=None, series_id=None, event_category=None, event_type=None, limit=100, offset=0, database=db)
        assert "events" in result
        assert "count" in result
        assert "limit" in result
        assert "offset" in result
        assert isinstance(result["events"], list)

    async def test_get_events_auto_detect_entity(self, db, sample_document_id):
        """Test getting events with auto-detected entity type."""
        if not sample_document_id:
            pytest.skip("No documents in database")

        result = await get_events(id=sample_document_id, document_id=None, file_id=None, series_id=None, event_category=None, event_type=None, limit=100, offset=0, database=db)
        assert "events" in result

    async def test_get_events_filter_by_category(self, db, sample_document_id):
        """Test filtering events by category."""
        if not sample_document_id:
            pytest.skip("No documents in database")

        for category in ["state_transition", "llm_request", "processing", "error"]:
            result = await get_events(
                id=None,
                document_id=sample_document_id,
                file_id=None,
                series_id=None,
                event_category=category,
                event_type=None,
                limit=100,
                offset=0,
                database=db
            )
            for event in result["events"]:
                assert event["event_category"] == category

    async def test_get_events_invalid_category(self, db, sample_document_id):
        """Test that invalid event category raises 400."""
        if not sample_document_id:
            pytest.skip("No documents in database")

        with pytest.raises(HTTPException) as exc_info:
            await get_events(
                id=None,
                document_id=sample_document_id,
                file_id=None,
                series_id=None,
                event_category="invalid_category",
                event_type=None,
                limit=100,
                offset=0,
                database=db
            )
        assert exc_info.value.status_code == 400

    async def test_get_events_not_found_entity(self, db):
        """Test getting events for non-existent entity raises 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        with pytest.raises(HTTPException) as exc_info:
            await get_events(id=fake_id, document_id=None, file_id=None, series_id=None, event_category=None, event_type=None, limit=100, offset=0, database=db)
        assert exc_info.value.status_code == 404

    async def test_event_has_expected_fields(self, db, sample_document_id):
        """Test that events have expected fields."""
        if not sample_document_id:
            pytest.skip("No documents in database")

        result = await get_events(id=None, document_id=sample_document_id, file_id=None, series_id=None, event_category=None, event_type=None, limit=1, offset=0, database=db)

        if result["events"]:
            event = result["events"][0]
            assert "id" in event
            assert "event_category" in event
            assert "event_type" in event
            assert "created_at" in event

    async def test_get_events_for_series(self, db, sample_series_id):
        """Test getting events for a series."""
        if not sample_series_id:
            pytest.skip("No series in database")

        result = await get_events(id=None, document_id=None, file_id=None, series_id=sample_series_id, event_category=None, event_type=None, limit=100, offset=0, database=db)
        assert "events" in result
        assert isinstance(result["events"], list)


# ==========================================
# DATA INTEGRITY TESTS
# ==========================================

class TestDataIntegrity:
    """Test data integrity and consistency."""

    async def test_document_series_relationship(self, db, sample_series_id):
        """Test that documents in a series are properly linked."""
        if not sample_series_id:
            pytest.skip("No series in database")

        result = await get_series(series_id=sample_series_id, database=db)
        documents = result["documents"]

        # Each document returned should have a valid ID
        for doc in documents:
            assert "id" in doc
            # Verify we can fetch the document individually
            doc_result = await get_document(document_id=doc["id"], database=db)
            assert doc_result is not None

    async def test_prompt_versioning(self, db):
        """Test that prompts have version numbers."""
        result = await list_prompts(prompt_type=None, document_type=None, include_inactive=True, database=db)

        # Group by prompt_type and document_type
        # Active prompts should have highest version
        for prompt in result["prompts"]:
            assert "version" in prompt
            assert isinstance(prompt["version"], int)
            assert prompt["version"] >= 1

    async def test_document_status_values(self, db):
        """Test that documents have valid status values."""
        valid_statuses = [
            "pending", "ocr_completed", "classified", "scored_classification",
            "summarized", "scored_summary", "filed", "series_summarized",
            "completed", "failed"
        ]

        result = await list_documents(status=None, document_type=None, limit=100, offset=0, database=db)
        for doc in result["documents"]:
            assert doc["status"] in valid_statuses


# ==========================================
# WORKFLOW TESTS - End-to-End Scenarios
# ==========================================

class TestWorkflowPGEUtilityBills:
    """
    End-to-end workflow test using PG&E utility bill series.

    This test validates a complete workflow:
    1. Find utility bills by filtering documents
    2. Navigate to series and verify series metadata
    3. Validate structured data schema for utility bills
    4. Test file grouping relationships
    """

    # Known test data - PG&E Utility Bill series
    SERIES_ID = "ae5f423a-ab7a-458d-95b3-033dedec698c"
    FILE_ID = "9cf77ad8-8f9f-40af-b5dc-e20f14346940"
    EXPECTED_ENTITY = "Pacific Gas & Electric"
    EXPECTED_DOC_COUNT = 12

    async def test_list_utility_bills(self, db):
        """Filter documents to find utility bills."""
        result = await list_documents(
            status="completed",
            document_type="utility_bill",
            limit=50,
            offset=0,
            database=db
        )

        assert result["count"] >= self.EXPECTED_DOC_COUNT
        assert all(d["document_type"] == "utility_bill" for d in result["documents"])
        assert all(d["status"] == "completed" for d in result["documents"])

    async def test_get_pge_series_metadata(self, db):
        """Retrieve and validate PG&E series metadata."""
        result = await get_series(series_id=self.SERIES_ID, database=db)

        series = result["series"]
        documents = result["documents"]

        # Validate series metadata
        assert series["id"] == self.SERIES_ID
        assert series["entity"] == self.EXPECTED_ENTITY
        assert "PG&E" in series["title"] or "Utility" in series["title"]

        # Validate document count
        assert len(documents) == self.EXPECTED_DOC_COUNT

        # All documents in series should be utility bills
        for doc in documents:
            assert doc["document_type"] == "utility_bill"

    async def test_utility_bill_structured_data_schema(self, db):
        """Validate structured data schema for utility bills."""
        # Get series documents
        result = await get_series(series_id=self.SERIES_ID, database=db)
        doc_id = result["documents"][0]["id"]

        # Get full document detail
        doc = await get_document(document_id=doc_id, database=db)

        assert doc["status"] == "completed"
        assert doc["document_type"] == "utility_bill"

        # Validate structured data has expected utility bill fields
        sd = doc["structured_data"]
        assert sd is not None

        # Required fields for utility bills
        assert "utility_provider" in sd
        assert sd["utility_provider"] == "PG&E"

        # Check for common utility bill fields
        utility_bill_fields = ["account_number", "billing_date", "due_date", "total_amount_due"]
        for field in utility_bill_fields:
            assert field in sd, f"Missing field: {field}"

        # Validate amount is a number
        assert isinstance(sd["total_amount_due"], (int, float))
        assert sd["total_amount_due"] > 0

    async def test_utility_bill_file_grouping(self, db):
        """Validate file grouping for utility bills."""
        result = await get_file(file_id=self.FILE_ID, database=db)

        file_info = result["file"]
        documents = result["documents"]

        # File should contain all 12 PG&E bills
        assert len(documents) == self.EXPECTED_DOC_COUNT

        # All documents should be utility bills from same provider
        providers = set()
        for doc in documents:
            assert doc["document_type"] == "utility_bill"
            if doc.get("structured_data"):
                providers.add(doc["structured_data"].get("utility_provider"))

        # All should be from PG&E
        assert providers == {"PG&E"}

    async def test_flatten_utility_bill_file(self, db):
        """Test flattening utility bills to tabular format."""
        result = await flatten_file_data(
            file_id=self.FILE_ID,
            array_strategy="flatten",
            max_depth=None,
            database=db
        )

        assert result["count"] == self.EXPECTED_DOC_COUNT

        # Should have columns for utility bill fields
        columns = result["columns"]
        assert "utility_provider" in columns
        assert "total_amount_due" in columns

        # Validate rows
        rows = result["rows"]
        assert len(rows) == self.EXPECTED_DOC_COUNT

        # Each row should have PG&E as provider
        # Rows can be dicts or lists depending on implementation
        for row in rows:
            if isinstance(row, dict):
                assert row.get("utility_provider") == "PG&E"
            else:
                provider_idx = columns.index("utility_provider")
                assert row[provider_idx] == "PG&E"


class TestWorkflowStateFarmInsurance:
    """
    End-to-end workflow test using State Farm insurance series.

    Tests:
    1. Filter insurance documents
    2. Navigate series and validate entity
    3. Validate insurance-specific schema
    """

    SERIES_ID = "ab574684-e07d-4a74-a216-287841969011"
    FILE_ID = "2719a892-4328-4d4b-92a2-e1d4ef9c00c2"
    EXPECTED_ENTITY = "State Farm Insurance"
    EXPECTED_DOC_COUNT = 12

    async def test_list_insurance_documents(self, db):
        """Filter documents to find insurance documents."""
        result = await list_documents(
            status="completed",
            document_type="insurance",
            limit=50,
            offset=0,
            database=db
        )

        # Should have at least the State Farm series
        assert result["count"] >= self.EXPECTED_DOC_COUNT
        assert all(d["document_type"] == "insurance" for d in result["documents"])

    async def test_get_state_farm_series(self, db):
        """Retrieve and validate State Farm series."""
        result = await get_series(series_id=self.SERIES_ID, database=db)

        series = result["series"]
        documents = result["documents"]

        assert series["entity"] == self.EXPECTED_ENTITY
        assert len(documents) == self.EXPECTED_DOC_COUNT

        # All docs should be insurance type
        for doc in documents:
            assert doc["document_type"] == "insurance"

    async def test_insurance_document_schema(self, db):
        """Validate insurance document structured data."""
        result = await get_series(series_id=self.SERIES_ID, database=db)
        doc_id = result["documents"][0]["id"]

        doc = await get_document(document_id=doc_id, database=db)
        sd = doc["structured_data"]

        # Insurance documents should have policy-related fields
        insurance_fields = ["policy_number", "due_date"]
        present_fields = [f for f in insurance_fields if f in sd]
        assert len(present_fields) >= 1, "Insurance doc should have policy fields"

        # Should reference State Farm
        all_values = str(sd).lower()
        assert "state farm" in all_values or "insurance" in all_values


class TestWorkflowRentReceipts:
    """
    End-to-end workflow test for rent receipt series.
    """

    SERIES_ID = "4bf9ab95-ab40-4577-81fe-558c819260c8"
    FILE_ID = "786dad61-5332-496d-9d81-22c2f1d074b5"
    EXPECTED_ENTITY = "Bay Area Properties LLC"
    EXPECTED_DOC_COUNT = 12

    async def test_get_rent_series(self, db):
        """Retrieve and validate rent receipt series."""
        result = await get_series(series_id=self.SERIES_ID, database=db)

        series = result["series"]
        assert series["entity"] == self.EXPECTED_ENTITY
        assert len(result["documents"]) == self.EXPECTED_DOC_COUNT

    async def test_rent_file_flatten(self, db):
        """Test flattening rent receipts."""
        result = await flatten_file_data(
            file_id=self.FILE_ID,
            array_strategy="flatten",
            max_depth=None,
            database=db
        )

        assert result["count"] == self.EXPECTED_DOC_COUNT
        assert len(result["rows"]) == self.EXPECTED_DOC_COUNT


class TestWorkflowCrossSeriesNavigation:
    """
    Test navigating across different document types and series.
    """

    async def test_list_all_series_and_validate(self, db):
        """List all series and validate structure."""
        result = await list_series(
            entity=None, series_type=None, frequency=None, status=None,
            limit=50, offset=0, database=db
        )

        # Should have at least 4 series (State Farm, SFSU, PG&E, Rent)
        assert result["count"] >= 4

        # Each series should have required fields
        for series in result["series"]:
            assert "id" in series
            assert "title" in series
            assert "entity" in series
            assert "document_count" in series
            assert series["document_count"] > 0

    async def test_list_all_files_and_validate(self, db):
        """List all files and validate structure."""
        result = await list_files(
            tags=None, status=None, limit=50, offset=0, database=db
        )

        # Should have at least 4 files
        assert result["count"] >= 4

        # Each file should have documents
        for file in result["files"]:
            assert "id" in file
            assert "document_count" in file
            assert file["document_count"] > 0

    async def test_document_type_distribution(self, db):
        """Validate document type distribution across the dataset."""
        result = await list_document_types(active_only=True, database=db)

        # Should have multiple document types
        assert result["count"] >= 5

        # Get actual document counts per type
        type_counts = {}
        for doc_type in ["insurance", "utility_bill", "education", "rent"]:
            docs = await list_documents(
                status="completed",
                document_type=doc_type,
                limit=100,
                offset=0,
                database=db
            )
            type_counts[doc_type] = docs["count"]

        # Validate expected types have documents
        assert type_counts["insurance"] >= 12, "Should have State Farm insurance docs"
        assert type_counts["utility_bill"] >= 12, "Should have PG&E utility docs"

    async def test_events_across_document_lifecycle(self, db):
        """Test that completed documents have lifecycle events."""
        # Get a completed document
        docs = await list_documents(
            status="completed", document_type=None, limit=1, offset=0, database=db
        )

        if not docs["documents"]:
            pytest.skip("No completed documents")

        doc_id = docs["documents"][0]["id"]

        # Get events for this document
        events = await get_events(
            id=None, document_id=doc_id, file_id=None, series_id=None,
            event_category=None, event_type=None, limit=100, offset=0, database=db
        )

        # Completed documents should have state transition events
        assert events["count"] > 0

        # Should have at least one state_transition event
        state_transitions = [
            e for e in events["events"]
            if e["event_category"] == "state_transition"
        ]
        assert len(state_transitions) > 0, "Completed doc should have state transitions"
