"""PostgreSQL advisory lock utilities (no Redis needed)."""

import asyncio
import hashlib
import time
from contextlib import asynccontextmanager
import logging
from uuid import UUID
from typing import Optional

from shared.database import AlfrdDatabase
from shared.event_logger import get_event_logger

logger = logging.getLogger(__name__)


def _string_to_lock_id(s: str) -> int:
    """
    Convert string to PostgreSQL advisory lock ID.
    
    PostgreSQL advisory locks use bigint (64-bit integer).
    Hash the string and take lower 63 bits (avoid negative numbers).
    """
    hash_digest = hashlib.md5(s.encode()).digest()
    lock_id = int.from_bytes(hash_digest[:8], 'big') & 0x7FFFFFFFFFFFFFFF
    return lock_id


@asynccontextmanager
async def document_type_lock(
    db: AlfrdDatabase,
    document_type: str,
    timeout_seconds: int = 300
):
    """
    Acquire exclusive PostgreSQL advisory lock for document type.
    
    Ensures only ONE document of type 'bill' is processed at a time
    (critical for prompt evolution).
    
    Uses PostgreSQL pg_advisory_lock() - session-level lock that's
    automatically released on connection close.
    
    CRITICAL: Connection must be held for entire lock duration!
    
    Args:
        db: Database instance
        document_type: Document type to lock (e.g., "bill")
        timeout_seconds: Max time to wait for lock
    
    Example:
        async with document_type_lock(db, "bill"):
            # Only one "bill" document processes here
            await summarize_document(...)
    """
    lock_id = _string_to_lock_id(f"doctype:{document_type}")
    
    logger.info(f"Acquiring PG advisory lock for '{document_type}' (id={lock_id})")
    
    # CRITICAL FIX: Acquire connection OUTSIDE the try block so it's held throughout
    conn = await db.pool.acquire()
    acquired = False
    
    try:
        # Try to acquire lock with timeout
        start = asyncio.get_event_loop().time()
        while True:
            result = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)",
                lock_id
            )
            
            if result:  # Lock acquired
                acquired = True
                logger.info(f"Lock acquired for '{document_type}' - connection held")
                break
            
            # Check timeout
            if asyncio.get_event_loop().time() - start > timeout_seconds:
                raise TimeoutError(
                    f"Failed to acquire lock for '{document_type}' "
                    f"after {timeout_seconds}s"
                )
            
            logger.debug(f"Waiting for lock '{document_type}'...")
            await asyncio.sleep(1)
        
        # Lock held - yield to caller (connection still held!)
        try:
            yield conn  # Optionally yield connection for caller to use same connection
        finally:
            # Release lock
            if acquired:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
                logger.info(f"Lock released for '{document_type}'")
    
    except Exception as e:
        logger.error(f"Error with advisory lock: {e}", exc_info=True)
        if acquired:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
            except Exception as unlock_err:
                logger.error(f"Failed to unlock: {unlock_err}")
        raise
    
    finally:
        # Release connection back to pool AFTER lock is released
        await db.pool.release(conn)
        logger.debug(f"Connection released for lock '{document_type}'")


@asynccontextmanager
async def series_prompt_lock(
    db: AlfrdDatabase,
    series_id: UUID,
    timeout_seconds: int = 300
):
    """
    Acquire exclusive PostgreSQL advisory lock for series prompt creation.

    Ensures only ONE task creates the series prompt at a time.
    Other tasks wait and then reuse the created prompt.

    Uses PostgreSQL pg_advisory_lock() - session-level lock that's
    automatically released on connection close.

    CRITICAL: Connection must be held for entire lock duration!

    Args:
        db: Database instance
        series_id: Series UUID to lock
        timeout_seconds: Max time to wait for lock

    Example:
        async with series_prompt_lock(db, series_id):
            # Only one task creates series prompt here
            series = await db.get_series(series_id)
            if not series.get('active_prompt_id'):
                # Create prompt...
    """
    lock_id = _string_to_lock_id(f"series_prompt:{series_id}")
    event_logger = get_event_logger(db)
    start_time = time.time()
    wait_count = 0

    logger.info(f"🔒 Requesting PG advisory lock for series prompt '{series_id}' (lock_id={lock_id})")

    # Log lock request event
    await event_logger.log_processing_event(
        entity_type='series',
        entity_id=series_id,
        event_type='lock_requested',
        task_name='series_prompt_lock',
        details={'lock_id': lock_id, 'lock_type': 'series_prompt'}
    )

    # CRITICAL: Acquire connection OUTSIDE the try block so it's held throughout
    conn = await db.pool.acquire()
    acquired = False

    try:
        # Try to acquire lock with timeout
        start = asyncio.get_event_loop().time()
        while True:
            result = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)",
                lock_id
            )

            if result:  # Lock acquired
                acquired = True
                wait_ms = int((time.time() - start_time) * 1000)
                logger.info(f"🔒 Lock ACQUIRED for series prompt '{series_id}' (waited {wait_ms}ms, {wait_count} retries)")

                # Log lock acquired event
                await event_logger.log_processing_event(
                    entity_type='series',
                    entity_id=series_id,
                    event_type='lock_acquired',
                    task_name='series_prompt_lock',
                    details={
                        'lock_id': lock_id,
                        'lock_type': 'series_prompt',
                        'wait_ms': wait_ms,
                        'wait_count': wait_count
                    }
                )
                break

            # Check timeout
            if asyncio.get_event_loop().time() - start > timeout_seconds:
                logger.error(f"🔒 Lock TIMEOUT for series prompt '{series_id}' after {timeout_seconds}s")
                await event_logger.log_processing_event(
                    entity_type='series',
                    entity_id=series_id,
                    event_type='lock_timeout',
                    task_name='series_prompt_lock',
                    details={'lock_id': lock_id, 'timeout_seconds': timeout_seconds}
                )
                raise TimeoutError(
                    f"Failed to acquire lock for series prompt '{series_id}' "
                    f"after {timeout_seconds}s"
                )

            wait_count += 1
            logger.info(f"🔒 Waiting for series prompt lock '{series_id}' (attempt {wait_count})...")
            await asyncio.sleep(0.5)  # Shorter sleep for prompt creation

        # Lock held - yield to caller (connection still held!)
        try:
            yield conn  # Optionally yield connection for caller to use same connection
        finally:
            # Release lock
            if acquired:
                hold_ms = int((time.time() - start_time) * 1000)
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
                logger.info(f"🔒 Lock RELEASED for series prompt '{series_id}' (held {hold_ms}ms)")

                # Log lock released event
                await event_logger.log_processing_event(
                    entity_type='series',
                    entity_id=series_id,
                    event_type='lock_released',
                    task_name='series_prompt_lock',
                    details={
                        'lock_id': lock_id,
                        'lock_type': 'series_prompt',
                        'hold_ms': hold_ms
                    }
                )

    except Exception as e:
        logger.error(f"🔒 Lock ERROR for series prompt '{series_id}': {e}", exc_info=True)
        if acquired:
            try:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
            except Exception as unlock_err:
                logger.error(f"Failed to unlock series prompt: {unlock_err}")
        raise

    finally:
        # Release connection back to pool AFTER lock is released
        await db.pool.release(conn)
        logger.debug(f"Connection released for series prompt lock '{series_id}'")