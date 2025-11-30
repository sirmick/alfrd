"""Comprehensive unit tests for shared database layer.

Tests all database operations used across ALFRD:
- Document CRUD operations
- Prompt management
- Document type operations
- Classification suggestions
- Search functionality
- Connection pooling
"""

import pytest
import asyncpg
from uuid import uuid4, UUID
from datetime import datetime
from pathlib import Path
import sys

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.types import DocumentStatus, PromptType


# Test database URL (uses template database for testing)
TEST_DB_URL = "postgresql://mick@/alfrd_test?host=/var/run/postgresql"


@pytest.fixture
async def test_db():
    """Create test database with schema for each test."""
    # Create test database
    conn = await asyncpg.connect("postgresql://mick@/postgres?host=/var/run/postgresql")
    
    # Drop and recreate test database
    await conn.execute("DROP DATABASE IF EXISTS alfrd_test")
    await conn.execute("CREATE DATABASE alfrd_test OWNER mick")
    await conn.close()
    
    # Connect to test database and load schema
    conn = await asyncpg.connect(TEST_DB_URL)
    
    # Read and execute schema
    schema_path = Path(__file__).parent.parent.parent / "api-server" / "src" / "api_server" / "db" / "schema.sql"
    with open(schema_path) as f:
        schema_sql = f.read()
    
    await conn.execute(schema_sql)
    await conn.close()
    
    # Create database instance
    db = AlfrdDatabase(TEST_DB_URL, pool_min_size=1, pool_max_size=5)
    await db.initialize()
    
    yield db
    
    # Cleanup
    await db.close()


class TestDocumentOperations:
    """Test document CRUD operations."""
    
    async def test_create_document(self, test_db):
        """Test creating a new document."""
        doc_id = uuid4()
        
        created_id = await test_db.create_document(
            doc_id=doc_id,
            filename="test.jpg",
            original_path="/data/inbox/test",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING,
            folder_path="/data/inbox/test"
        )
        
        assert created_id == doc_id
        
        # Verify it was created
        doc = await test_db.get_document(doc_id)
        assert doc is not None
        assert doc['filename'] == "test.jpg"
        assert doc['status'] == DocumentStatus.PENDING
        assert doc['file_size'] == 1024
    
    async def test_get_document_not_found(self, test_db):
        """Test getting non-existent document."""
        doc = await test_db.get_document(uuid4())
        assert doc is None
    
    async def test_update_document(self, test_db):
        """Test updating document fields."""
        doc_id = uuid4()
        
        await test_db.create_document(
            doc_id=doc_id,
            filename="test.jpg",
            original_path="/data/inbox/test",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING
        )
        
        # Update status and add classification
        await test_db.update_document(
            doc_id,
            status=DocumentStatus.CLASSIFIED,
            document_type="bill",
            classification_confidence=0.95,
            classification_reasoning="Looks like a utility bill"
        )
        
        # Verify updates
        doc = await test_db.get_document(doc_id)
        assert doc['status'] == DocumentStatus.CLASSIFIED
        assert doc['document_type'] == "bill"
        assert doc['classification_confidence'] == 0.95
    
    async def test_get_documents_by_status(self, test_db):
        """Test filtering documents by status."""
        # Create documents with different statuses
        pending_id = uuid4()
        completed_id = uuid4()
        
        await test_db.create_document(
            doc_id=pending_id,
            filename="pending.jpg",
            original_path="/data/inbox/pending",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING
        )
        
        await test_db.create_document(
            doc_id=completed_id,
            filename="completed.jpg",
            original_path="/data/inbox/completed",
            file_type="image",
            file_size=2048,
            status=DocumentStatus.COMPLETED
        )
        
        # Get pending documents
        pending_docs = await test_db.get_documents_by_status(DocumentStatus.PENDING, limit=10)
        assert len(pending_docs) == 1
        assert pending_docs[0]['id'] == pending_id
        
        # Get completed documents
        completed_docs = await test_db.get_documents_by_status(DocumentStatus.COMPLETED, limit=10)
        assert len(completed_docs) == 1
        assert completed_docs[0]['id'] == completed_id
    
    async def test_list_documents(self, test_db):
        """Test listing documents with pagination."""
        # Create multiple documents
        for i in range(5):
            await test_db.create_document(
                doc_id=uuid4(),
                filename=f"doc{i}.jpg",
                original_path=f"/data/inbox/doc{i}",
                file_type="image",
                file_size=1024 * i,
                status=DocumentStatus.PENDING
            )
        
        # List all
        docs = await test_db.list_documents(limit=10, offset=0)
        assert len(docs) == 5
        
        # List with pagination
        page1 = await test_db.list_documents(limit=2, offset=0)
        assert len(page1) == 2
        
        page2 = await test_db.list_documents(limit=2, offset=2)
        assert len(page2) == 2
    
    async def test_delete_document(self, test_db):
        """Test deleting a document."""
        doc_id = uuid4()
        
        await test_db.create_document(
            doc_id=doc_id,
            filename="test.jpg",
            original_path="/data/inbox/test",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING
        )
        
        # Delete it
        await test_db.delete_document(doc_id)
        
        # Verify it's gone
        doc = await test_db.get_document(doc_id)
        assert doc is None


class TestPromptOperations:
    """Test prompt management operations."""
    
    async def test_create_and_get_prompt(self, test_db):
        """Test creating and retrieving prompts."""
        prompt_id = uuid4()
        prompt_text = "You are a document classifier..."
        
        created_id = await test_db.create_prompt(
            prompt_id=prompt_id,
            prompt_type=PromptType.CLASSIFIER.value,
            prompt_text=prompt_text,
            version=1
        )
        
        assert created_id == prompt_id
        
        # Get active prompt
        prompt = await test_db.get_active_prompt(PromptType.CLASSIFIER.value)
        assert prompt is not None
        assert prompt['prompt_text'] == prompt_text
        assert prompt['version'] == 1
    
    async def test_prompt_versioning(self, test_db):
        """Test prompt version management."""
        # Create version 1
        await test_db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.CLASSIFIER.value,
            prompt_text="Version 1",
            version=1,
            performance_score=0.8
        )
        
        # Deactivate old versions
        await test_db.deactivate_old_prompts(PromptType.CLASSIFIER.value)
        
        # Create version 2
        await test_db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.CLASSIFIER.value,
            prompt_text="Version 2 - improved",
            version=2,
            performance_score=0.9
        )
        
        # Should get version 2 as active
        prompt = await test_db.get_active_prompt(PromptType.CLASSIFIER.value)
        assert prompt['version'] == 2
        assert prompt['prompt_text'] == "Version 2 - improved"
        assert prompt['performance_score'] == 0.9
    
    async def test_summarizer_prompts_by_type(self, test_db):
        """Test document-type-specific summarizer prompts."""
        # Create bill summarizer
        await test_db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.SUMMARIZER.value,
            document_type="bill",
            prompt_text="Extract bill data...",
            version=1
        )
        
        # Create finance summarizer
        await test_db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.SUMMARIZER.value,
            document_type="finance",
            prompt_text="Extract financial data...",
            version=1
        )
        
        # Get bill summarizer
        bill_prompt = await test_db.get_active_prompt(PromptType.SUMMARIZER.value, "bill")
        assert bill_prompt is not None
        assert bill_prompt['document_type'] == "bill"
        
        # Get finance summarizer
        finance_prompt = await test_db.get_active_prompt(PromptType.SUMMARIZER.value, "finance")
        assert finance_prompt is not None
        assert finance_prompt['document_type'] == "finance"
    
    async def test_list_prompts(self, test_db):
        """Test listing prompts with filters."""
        # Create multiple prompts
        await test_db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.CLASSIFIER.value,
            prompt_text="Classifier v1",
            version=1
        )
        
        await test_db.create_prompt(
            prompt_id=uuid4(),
            prompt_type=PromptType.SUMMARIZER.value,
            document_type="bill",
            prompt_text="Bill summarizer v1",
            version=1
        )
        
        # List all prompts
        all_prompts = await test_db.list_prompts()
        assert len(all_prompts) == 2
        
        # List only classifiers
        classifiers = await test_db.list_prompts(prompt_type=PromptType.CLASSIFIER.value)
        assert len(classifiers) == 1
        assert classifiers[0]['prompt_type'] == PromptType.CLASSIFIER.value
        
        # List only bill summarizers
        bill_prompts = await test_db.list_prompts(
            prompt_type=PromptType.SUMMARIZER.value,
            document_type="bill"
        )
        assert len(bill_prompts) == 1
        assert bill_prompts[0]['document_type'] == "bill"


class TestDocumentTypeOperations:
    """Test document type management."""
    
    async def test_create_and_get_document_types(self, test_db):
        """Test creating and retrieving document types."""
        type_id = uuid4()
        
        created_id = await test_db.create_document_type(
            type_id=type_id,
            type_name="bill",
            description="Utility bills and invoices"
        )
        
        assert created_id == type_id
        
        # Get all types
        types = await test_db.get_document_types()
        assert len(types) == 1
        assert types[0]['type_name'] == "bill"
        assert types[0]['description'] == "Utility bills and invoices"
        assert types[0]['usage_count'] == 0
    
    async def test_increment_type_usage(self, test_db):
        """Test incrementing type usage count."""
        await test_db.create_document_type(
            type_id=uuid4(),
            type_name="bill",
            description="Bills"
        )
        
        # Increment usage
        await test_db.increment_type_usage("bill")
        await test_db.increment_type_usage("bill")
        
        # Verify count
        types = await test_db.get_document_types()
        assert types[0]['usage_count'] == 2


class TestClassificationSuggestions:
    """Test classification suggestion operations."""
    
    async def test_record_suggestion(self, test_db):
        """Test recording LLM classification suggestions."""
        doc_id = uuid4()
        suggestion_id = uuid4()
        
        # Create document first
        await test_db.create_document(
            doc_id=doc_id,
            filename="test.jpg",
            original_path="/data/inbox/test",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING
        )
        
        # Record suggestion
        created_id = await test_db.record_classification_suggestion(
            suggestion_id=suggestion_id,
            suggested_type="medical_bill",
            document_id=doc_id,
            confidence=0.92,
            reasoning="Contains medical terminology and billing codes"
        )
        
        assert created_id == suggestion_id


class TestSearchOperations:
    """Test search functionality."""
    
    async def test_search_documents(self, test_db):
        """Test full-text search."""
        # Create documents with text
        doc1_id = uuid4()
        doc2_id = uuid4()
        
        await test_db.create_document(
            doc_id=doc1_id,
            filename="utility_bill.jpg",
            original_path="/data/inbox/bill",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.COMPLETED
        )
        
        # Update with extracted text (this would be done by OCR worker)
        await test_db.update_document(
            doc1_id,
            extracted_text="PG&E Utility Bill - Electric service for November"
        )
        
        await test_db.create_document(
            doc_id=doc2_id,
            filename="receipt.jpg",
            original_path="/data/inbox/receipt",
            file_type="image",
            file_size=2048,
            status=DocumentStatus.COMPLETED
        )
        
        await test_db.update_document(
            doc2_id,
            extracted_text="Amazon receipt for office supplies"
        )
        
        # Search for "utility"
        results = await test_db.search_documents("utility", limit=10)
        assert len(results) >= 1
        # Note: Full-text search requires the trigger to populate extracted_text_tsv


class TestStats:
    """Test statistics operations."""
    
    async def test_get_stats(self, test_db):
        """Test getting database statistics."""
        # Create documents with different statuses
        await test_db.create_document(
            doc_id=uuid4(),
            filename="doc1.jpg",
            original_path="/data/inbox/doc1",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING
        )
        
        await test_db.create_document(
            doc_id=uuid4(),
            filename="doc2.jpg",
            original_path="/data/inbox/doc2",
            file_type="image",
            file_size=2048,
            status=DocumentStatus.COMPLETED
        )
        
        await test_db.update_document(
            await test_db.create_document(
                doc_id=uuid4(),
                filename="doc3.jpg",
                original_path="/data/inbox/doc3",
                file_type="image",
                file_size=3072,
                status=DocumentStatus.PENDING
            ),
            document_type="bill"
        )
        
        # Get stats
        stats = await test_db.get_stats()
        
        assert stats['total_documents'] == 3
        assert stats['by_status'][DocumentStatus.PENDING] == 2
        assert stats['by_status'][DocumentStatus.COMPLETED] == 1
        assert 'bill' in stats['by_type']


class TestConnectionPooling:
    """Test connection pool behavior."""
    
    async def test_concurrent_operations(self, test_db):
        """Test multiple concurrent database operations."""
        import asyncio
        
        async def create_doc(i):
            await test_db.create_document(
                doc_id=uuid4(),
                filename=f"doc{i}.jpg",
                original_path=f"/data/inbox/doc{i}",
                file_type="image",
                file_size=1024 * i,
                status=DocumentStatus.PENDING
            )
        
        # Create 10 documents concurrently
        await asyncio.gather(*[create_doc(i) for i in range(10)])
        
        # Verify all were created
        docs = await test_db.list_documents(limit=20)
        assert len(docs) == 10
    
    async def test_pool_reuse(self, test_db):
        """Test that pool is reused across operations."""
        # First operation
        doc1_id = uuid4()
        await test_db.create_document(
            doc_id=doc1_id,
            filename="doc1.jpg",
            original_path="/data/inbox/doc1",
            file_type="image",
            file_size=1024,
            status=DocumentStatus.PENDING
        )
        
        # Second operation (should reuse pool)
        doc1 = await test_db.get_document(doc1_id)
        assert doc1 is not None
        
        # Pool should still be active
        assert test_db.pool is not None


# Run tests with: pytest shared/tests/test_database.py -v
if __name__ == "__main__":
    pytest.main([__file__, "-v"])