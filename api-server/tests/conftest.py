"""
Pytest fixtures for API tests.

These tests call API endpoint functions DIRECTLY (no HTTP layer).
This approach:
1. Tests the actual business logic
2. Is faster than HTTP-based tests
3. Provides the foundation for CLI wrappers that call the same functions

Tests assume a known dataset has been loaded into the production database.
Tests are READ-ONLY and do not modify any data.
"""

import sys
from pathlib import Path
import pytest
import pytest_asyncio

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from shared.database import AlfrdDatabase
from shared.config import Settings


@pytest_asyncio.fixture
async def db():
    """
    Get a database connection for the test.
    Uses the production database - tests should be READ-ONLY.
    """
    settings = Settings()
    database = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=1,
        pool_max_size=5,
        pool_timeout=30.0
    )
    await database.initialize()
    yield database
    await database.close()


@pytest_asyncio.fixture
async def sample_document_id(db):
    """
    Get a sample document ID from the database.
    Returns None if no documents exist.
    """
    docs = await db.list_documents_api(limit=1)
    if docs:
        return str(docs[0]['id'])
    return None


@pytest_asyncio.fixture
async def sample_series_id(db):
    """
    Get a sample series ID from the database.
    Returns None if no series exist.
    """
    series = await db.list_series(limit=1)
    if series:
        return str(series[0]['id'])
    return None


@pytest_asyncio.fixture
async def sample_file_id(db):
    """
    Get a sample file ID from the database.
    Returns None if no files exist.
    """
    files = await db.list_files(limit=1)
    if files:
        return str(files[0]['id'])
    return None


@pytest_asyncio.fixture
async def completed_document_id(db):
    """
    Get a completed document ID from the database.
    Returns None if no completed documents exist.
    """
    docs = await db.list_documents_api(limit=1, status='completed')
    if docs:
        return str(docs[0]['id'])
    return None


@pytest_asyncio.fixture
async def sample_prompt_id(db):
    """
    Get a sample prompt ID from the database.
    Returns None if no prompts exist.
    """
    prompts = await db.list_prompts()
    if prompts:
        return str(prompts[0]['id'])
    return None
