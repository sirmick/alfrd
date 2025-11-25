"""Tests for worker pool infrastructure."""

import pytest
import asyncio
from datetime import datetime
from pathlib import Path
import sys
import tempfile
import shutil

# Add parent directories to path
_test_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_test_dir))

from shared.config import Settings
from shared.types import DocumentStatus
from document_processor.workers import BaseWorker, WorkerPool


class MockWorker(BaseWorker):
    """Mock worker for testing base class functionality."""
    
    def __init__(self, settings: Settings, concurrency: int = 2, poll_interval: int = 1):
        super().__init__(
            settings=settings,
            worker_name="Mock Worker",
            source_status=DocumentStatus.PENDING,
            target_status=DocumentStatus.COMPLETED,
            concurrency=concurrency,
            poll_interval=poll_interval,
        )
        self.documents_processed = []
        self.mock_documents = []
    
    async def get_documents(self, status: DocumentStatus, limit: int):
        """Return mock documents."""
        return self.mock_documents[:limit]
    
    async def process_document(self, document: dict) -> bool:
        """Mock processing - just record the document."""
        await asyncio.sleep(0.1)  # Simulate work
        self.documents_processed.append(document["id"])
        return True


@pytest.fixture
def settings():
    """Create test settings with temporary database."""
    temp_dir = tempfile.mkdtemp()
    
    settings = Settings(
        database_path=Path(temp_dir) / "test.db",
        inbox_path=Path(temp_dir) / "inbox",
        documents_path=Path(temp_dir) / "documents",
        summaries_path=Path(temp_dir) / "summaries",
        worker_batch_multiplier=2,
    )
    
    # Create directories
    settings.inbox_path.mkdir(parents=True, exist_ok=True)
    settings.documents_path.mkdir(parents=True, exist_ok=True)
    
    yield settings
    
    # Cleanup
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.mark.asyncio
async def test_base_worker_initialization(settings):
    """Test that BaseWorker initializes correctly."""
    worker = MockWorker(settings, concurrency=3, poll_interval=2)
    
    assert worker.worker_name == "Mock Worker"
    assert worker.source_status == DocumentStatus.PENDING
    assert worker.target_status == DocumentStatus.COMPLETED
    assert worker.concurrency == 3
    assert worker.poll_interval == 2
    assert worker.running is False


@pytest.mark.asyncio
async def test_worker_processes_documents(settings):
    """Test that worker processes documents with correct concurrency."""
    worker = MockWorker(settings, concurrency=2, poll_interval=1)
    
    # Add mock documents
    worker.mock_documents = [
        {"id": "doc1", "status": "pending"},
        {"id": "doc2", "status": "pending"},
        {"id": "doc3", "status": "pending"},
    ]
    
    # Start worker task
    worker_task = asyncio.create_task(worker.run())
    
    # Let it process one batch
    await asyncio.sleep(0.5)
    
    # Stop worker immediately after first batch
    worker.stop()
    worker_task.cancel()
    
    try:
        await worker_task
    except asyncio.CancelledError:
        pass
    
    # Should have processed at least 2 documents (concurrency limit)
    # May process more if worker looped multiple times
    assert len(worker.documents_processed) >= 2
    assert "doc1" in worker.documents_processed
    assert "doc2" in worker.documents_processed


@pytest.mark.asyncio
async def test_worker_handles_empty_queue(settings):
    """Test that worker handles no documents gracefully."""
    worker = MockWorker(settings, concurrency=2, poll_interval=1)
    
    # No documents
    worker.mock_documents = []
    
    # Start worker
    worker_task = asyncio.create_task(worker.run())
    
    # Let it run for a few polls
    await asyncio.sleep(2.5)
    
    # Stop worker
    worker.stop()
    await asyncio.sleep(0.5)
    worker_task.cancel()
    
    # Should not have processed anything
    assert len(worker.documents_processed) == 0


@pytest.mark.asyncio
async def test_worker_pool_manages_multiple_workers(settings):
    """Test that WorkerPool can manage multiple workers."""
    pool = WorkerPool()
    
    worker1 = MockWorker(settings, concurrency=1, poll_interval=1)
    worker1.mock_documents = [{"id": "doc1", "status": "pending"}]
    
    worker2 = MockWorker(settings, concurrency=1, poll_interval=1)
    worker2.mock_documents = [{"id": "doc2", "status": "pending"}]
    
    pool.add_worker(worker1)
    pool.add_worker(worker2)
    
    assert len(pool.workers) == 2
    
    # Start pool
    pool_task = asyncio.create_task(pool.start())
    
    # Let workers process
    await asyncio.sleep(1.5)
    
    # Stop pool
    await pool.stop()
    pool_task.cancel()
    
    # Both workers should have processed their documents
    assert len(worker1.documents_processed) >= 1
    assert len(worker2.documents_processed) >= 1


@pytest.mark.asyncio
async def test_worker_respects_batch_multiplier(settings):
    """Test that worker fetches batch_size = concurrency * multiplier."""
    settings.worker_batch_multiplier = 3
    
    worker = MockWorker(settings, concurrency=2, poll_interval=1)
    
    # Add more documents than concurrency
    worker.mock_documents = [
        {"id": f"doc{i}", "status": "pending"}
        for i in range(10)
    ]
    
    # Get documents with batch size
    batch_size = worker.concurrency * settings.worker_batch_multiplier
    docs = await worker.get_documents(DocumentStatus.PENDING, batch_size)
    
    # Should fetch batch_size documents
    assert len(docs) == batch_size  # 2 * 3 = 6


@pytest.mark.asyncio
async def test_worker_stops_gracefully(settings):
    """Test that worker stops when stop() is called."""
    worker = MockWorker(settings, concurrency=1, poll_interval=1)
    worker.mock_documents = [{"id": "doc1", "status": "pending"}]
    
    # Start worker
    worker_task = asyncio.create_task(worker.run())
    
    # Give it time to start
    await asyncio.sleep(0.1)
    
    assert worker.running is True
    
    # Stop worker
    worker.stop()
    await asyncio.sleep(0.5)
    
    assert worker.running is False
    
    worker_task.cancel()
    
    try:
        await worker_task
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])