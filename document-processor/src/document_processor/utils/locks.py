"""PostgreSQL advisory lock utilities (no Redis needed)."""

import asyncio
import hashlib
from contextlib import asynccontextmanager
import logging

from shared.database import AlfrdDatabase

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
    
    acquired = False
    async with db.pool.acquire() as conn:
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
                    logger.info(f"Lock acquired for '{document_type}'")
                    break
                
                # Check timeout
                if asyncio.get_event_loop().time() - start > timeout_seconds:
                    raise TimeoutError(
                        f"Failed to acquire lock for '{document_type}' "
                        f"after {timeout_seconds}s"
                    )
                
                await asyncio.sleep(1)
            
            # Lock held - yield to caller
            try:
                yield
            finally:
                # Release lock
                if acquired:
                    await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
                    logger.info(f"Lock released for '{document_type}'")
        
        except Exception as e:
            logger.error(f"Error with advisory lock: {e}")
            if acquired:
                await conn.execute("SELECT pg_advisory_unlock($1)", lock_id)
            raise