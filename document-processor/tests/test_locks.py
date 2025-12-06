"""Test PostgreSQL advisory locks."""

import pytest
import asyncio
from uuid import uuid4

from shared.database import AlfrdDatabase
from shared.config import Settings
from document_processor.utils.locks import document_type_lock, _string_to_lock_id


def test_string_to_lock_id():
    """Test consistent lock ID generation."""
    lock_id1 = _string_to_lock_id("bill")
    lock_id2 = _string_to_lock_id("bill")
    assert lock_id1 == lock_id2
    assert lock_id1 > 0  # Positive integer
    
    # Different strings get different IDs
    assert _string_to_lock_id("bill") != _string_to_lock_id("finance")


@pytest.mark.asyncio
async def test_document_type_lock_basic():
    """Test basic lock acquisition and release."""
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    try:
        async with document_type_lock(db, "test_type"):
            # Lock is held
            pass
        
        # Lock should be released
        async with document_type_lock(db, "test_type"):
            # Can acquire again
            pass
    
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_document_type_lock_serialization():
    """Test that locks serialize access."""
    settings = Settings()
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    results = []
    
    async def worker(worker_id: int):
        async with document_type_lock(db, "bill", timeout_seconds=10):
            results.append(f"start-{worker_id}")
            await asyncio.sleep(0.5)  # Simulate work
            results.append(f"end-{worker_id}")
    
    try:
        # Run 3 workers concurrently
        await asyncio.gather(
            worker(1),
            worker(2),
            worker(3)
        )
        
        # Verify no interleaving - each worker completes before next starts
        for i in range(0, len(results), 2):
            worker_id = results[i].split('-')[1]
            assert results[i+1] == f'end-{worker_id}', \
                f"Expected end-{worker_id} at position {i+1}, got {results[i+1]}"
    
    finally:
        await db.close()