"""Worker pool infrastructure for parallel document processing.

This module implements a state-machine-driven worker architecture where:
- Each worker polls the database for documents in a specific state
- Workers process documents in parallel with configurable concurrency
- State transitions are tracked in the database for observability and recovery
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import sys

# Add parent directories to path for shared imports
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

from shared.config import Settings
from shared.types import DocumentStatus

logger = logging.getLogger(__name__)


class BaseWorker(ABC):
    """Base class for all document processing workers.
    
    Workers poll the database for documents in a specific state,
    process them with configurable concurrency, and update their status.
    """
    
    def __init__(
        self,
        settings: Settings,
        worker_name: str,
        source_status: DocumentStatus,
        target_status: DocumentStatus,
        concurrency: int,
        poll_interval: int,
    ):
        """
        Initialize a worker.
        
        Args:
            settings: Application settings
            worker_name: Name for logging (e.g., "OCR Worker")
            source_status: Status to query for (e.g., DocumentStatus.PENDING)
            target_status: Status to set on success (e.g., DocumentStatus.OCR_COMPLETED)
            concurrency: Number of parallel tasks
            poll_interval: Seconds between database polls
        """
        self.settings = settings
        self.worker_name = worker_name
        self.source_status = source_status
        self.target_status = target_status
        self.concurrency = concurrency
        self.poll_interval = poll_interval
        self.running = False
        
        logger.info(
            f"{self.worker_name} initialized: "
            f"{source_status.value} → {target_status.value}, "
            f"concurrency={concurrency}, poll_interval={poll_interval}s"
        )
    
    async def run(self):
        """
        Main worker loop: poll database, process documents, repeat.
        
        This method runs indefinitely until stopped. It:
        1. Queries DB for documents in source_status
        2. Processes up to `concurrency` documents in parallel
        3. Sleeps for poll_interval
        4. Repeats
        """
        self.running = True
        logger.info(f"{self.worker_name} started")
        
        while self.running:
            try:
                # Get batch of documents to process
                batch_size = self.concurrency * self.settings.worker_batch_multiplier
                documents = await self.get_documents(
                    status=self.source_status,
                    limit=batch_size
                )
                
                if not documents:
                    # No work available, sleep and continue
                    await asyncio.sleep(self.poll_interval)
                    continue
                
                logger.info(
                    f"{self.worker_name} found {len(documents)} documents, "
                    f"processing {min(len(documents), self.concurrency)} in parallel"
                )
                
                # Process documents in parallel (up to concurrency limit)
                tasks = [
                    self.process_document(doc)
                    for doc in documents[:self.concurrency]
                ]
                
                results = await asyncio.gather(*tasks, return_exceptions=True)
                
                # Log results
                successes = sum(1 for r in results if r is True)
                failures = sum(1 for r in results if isinstance(r, Exception))
                
                logger.info(
                    f"{self.worker_name} batch complete: "
                    f"{successes} succeeded, {failures} failed"
                )
                
            except Exception as e:
                logger.error(f"{self.worker_name} error in main loop: {e}", exc_info=True)
            
            # Sleep before next poll
            await asyncio.sleep(self.poll_interval)
    
    def stop(self):
        """Stop the worker gracefully."""
        logger.info(f"{self.worker_name} stopping...")
        self.running = False
    
    @abstractmethod
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in given status.
        
        Args:
            status: Document status to query
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries with at least {id, status, ...}
        """
        pass
    
    @abstractmethod
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document.
        
        This method should:
        1. Perform the worker-specific processing
        2. Update document status in database
        3. Return True on success, raise exception on failure
        
        Args:
            document: Document dictionary from get_documents()
            
        Returns:
            True if processing succeeded
            
        Raises:
            Exception: If processing fails
        """
        pass
    
    async def update_status(
        self,
        doc_id: str,
        status: DocumentStatus,
        error: Optional[str] = None
    ) -> None:
        """
        Update document status in database.
        
        Args:
            doc_id: Document ID
            status: New status
            error: Error message if status is FAILED
        """
        import duckdb
        
        conn = duckdb.connect(str(self.settings.database_path))
        try:
            if error:
                conn.execute("""
                    UPDATE documents 
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE id = ?
                """, [status.value, error, datetime.utcnow(), doc_id])
            else:
                # Clear any previous error message
                conn.execute("""
                    UPDATE documents 
                    SET status = ?, error_message = NULL, updated_at = ?
                    WHERE id = ?
                """, [status.value, datetime.utcnow(), doc_id])
            
            logger.debug(f"Updated document {doc_id} status to {status.value}")
        finally:
            conn.close()


class WorkerPool:
    """Manages multiple workers running concurrently."""
    
    def __init__(self):
        self.workers: List[BaseWorker] = []
        self.tasks: List[asyncio.Task] = []
    
    def add_worker(self, worker: BaseWorker):
        """Add a worker to the pool."""
        self.workers.append(worker)
        logger.info(f"Added {worker.worker_name} to pool")
    
    async def start(self):
        """Start all workers concurrently."""
        logger.info(f"Starting worker pool with {len(self.workers)} workers")
        
        self.tasks = [
            asyncio.create_task(worker.run())
            for worker in self.workers
        ]
        
        # Wait for all workers (runs indefinitely)
        await asyncio.gather(*self.tasks, return_exceptions=True)
    
    async def stop(self):
        """Stop all workers gracefully."""
        logger.info("Stopping worker pool...")
        
        for worker in self.workers:
            worker.stop()
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        # Wait for cancellation
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        logger.info("Worker pool stopped")