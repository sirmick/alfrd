"""Centralized logging configuration for ALFRD.

Provides separate log channels for:
- State transitions (document/file/series status changes)
- AWS API usage (Textract, Bedrock calls with costs)
- Exceptions (all errors with full context)
- Cache operations (hits/misses/errors)

All logs include entity IDs (document_id, file_id, series_id) for tracing.
"""

import logging
import json
from pathlib import Path
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID


class AlfrdLogger:
    """Centralized logging configuration for ALFRD."""
    
    _initialized = False
    
    @classmethod
    def setup(cls, log_dir: Path = None) -> None:
        """Initialize all ALFRD log channels.
        
        Args:
            log_dir: Directory for log files (default: ./logs)
        """
        if cls._initialized:
            return
        
        if log_dir is None:
            log_dir = Path("./logs")
        
        log_dir.mkdir(exist_ok=True, parents=True)
        
        # Disable propagation to root logger (prevents Prefect interference)
        alfrd_root = logging.getLogger("alfrd")
        alfrd_root.propagate = False
        
        # 1. STATE TRANSITIONS LOG
        cls._setup_logger(
            "alfrd.state",
            log_dir / "state_transitions.log",
            logging.INFO,
            max_bytes=20*1024*1024,  # 20MB
            backup_count=10
        )
        
        # 2. AWS API USAGE LOG
        cls._setup_logger(
            "alfrd.aws",
            log_dir / "aws_usage.log",
            logging.INFO,
            max_bytes=10*1024*1024,
            backup_count=5
        )
        
        # 3. EXCEPTIONS LOG
        cls._setup_logger(
            "alfrd.exceptions",
            log_dir / "exceptions.log",
            logging.ERROR,
            max_bytes=20*1024*1024,
            backup_count=10
        )
        
        # 4. CACHE OPERATIONS LOG
        cls._setup_logger(
            "alfrd.cache",
            log_dir / "cache.log",
            logging.DEBUG,
            max_bytes=10*1024*1024,
            backup_count=3
        )
        
        # 5. RETRY ATTEMPTS LOG
        cls._setup_logger(
            "alfrd.retry",
            log_dir / "retries.log",
            logging.WARNING,
            max_bytes=5*1024*1024,
            backup_count=3
        )
        
        cls._initialized = True
        
        # Log initialization
        state_log = logging.getLogger("alfrd.state")
        state_log.info(json.dumps({
            "event": "logging_initialized",
            "log_dir": str(log_dir),
            "timestamp": datetime.utcnow().isoformat()
        }))
    
    @staticmethod
    def _setup_logger(
        name: str,
        log_file: Path,
        level: int,
        max_bytes: int,
        backup_count: int
    ) -> None:
        """Setup individual logger with rotating file handler."""
        logger = logging.getLogger(name)
        logger.setLevel(level)
        
        # Clear existing handlers
        logger.handlers = []
        
        # File handler
        handler = RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s | %(levelname)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)
        
        # Also log to console (for visibility)
        console = logging.StreamHandler()
        console.setFormatter(logging.Formatter(
            '%(levelname)s | %(message)s'
        ))
        logger.addHandler(console)


# ============================================================================
# LOGGING HELPERS
# ============================================================================

def log_state_transition(
    entity_type: str,  # "document", "file", "series"
    entity_id: UUID,
    old_status: Optional[str],
    new_status: str,
    filename: Optional[str] = None,
    document_type: Optional[str] = None,
    retry_count: int = 0,
    extra: Optional[Dict[str, Any]] = None
) -> None:
    """Log a state transition for any entity.
    
    Args:
        entity_type: Type of entity (document/file/series)
        entity_id: UUID of entity
        old_status: Previous status
        new_status: New status
        filename: Optional filename
        document_type: Optional document type
        retry_count: Number of retries
        extra: Additional context data
    """
    logger = logging.getLogger("alfrd.state")
    
    log_data = {
        "event": "state_transition",
        "entity_type": entity_type,
        f"{entity_type}_id": str(entity_id),
        "old_status": old_status,
        "new_status": new_status,
        "retry_count": retry_count,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if filename:
        log_data["filename"] = filename
    if document_type:
        log_data["document_type"] = document_type
    if extra:
        log_data.update(extra)  # Merge extra fields at top level

    logger.info(json.dumps(log_data))


def log_aws_usage(
    api: str,  # "textract", "bedrock"
    entity_type: str,
    entity_id: UUID,
    cached: bool,
    details: Dict[str, Any]
) -> None:
    """Log AWS API usage.
    
    Args:
        api: API name (textract/bedrock)
        entity_type: Entity type (document/file)
        entity_id: Entity UUID
        cached: Whether response was from cache
        details: API-specific details (tokens, pages, confidence, etc.)
    """
    logger = logging.getLogger("alfrd.aws")
    
    log_data = {
        "event": f"aws_{api}_call",
        "api": api,
        "entity_type": entity_type,
        f"{entity_type}_id": str(entity_id),
        "cached": cached,
        "timestamp": datetime.utcnow().isoformat(),
        **details
    }
    
    logger.info(json.dumps(log_data))


def log_exception(
    exception: Exception,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    task_name: Optional[str] = None,
    context: Optional[Dict[str, Any]] = None
) -> None:
    """Log an exception with full context.
    
    Args:
        exception: The exception that occurred
        entity_type: Type of entity (document/file/series)
        entity_id: UUID of entity
        task_name: Name of task/operation
        context: Additional context data
    """
    logger = logging.getLogger("alfrd.exceptions")
    
    log_data = {
        "event": "exception",
        "exception_type": type(exception).__name__,
        "exception_message": str(exception),
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if entity_type and entity_id:
        log_data["entity_type"] = entity_type
        log_data[f"{entity_type}_id"] = str(entity_id)
    
    if task_name:
        log_data["task_name"] = task_name
    
    if context:
        log_data["context"] = context
    
    logger.error(json.dumps(log_data), exc_info=True)


def log_cache_operation(
    operation: str,  # "hit", "miss", "save", "error"
    request_type: str,  # "textract", "bedrock"
    cache_key: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[UUID] = None,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """Log cache operation.
    
    Args:
        operation: Operation type (hit/miss/save/error)
        request_type: Type of request (textract/bedrock)
        cache_key: Cache key hash
        entity_type: Entity type
        entity_id: Entity UUID
        details: Additional details
    """
    logger = logging.getLogger("alfrd.cache")
    
    log_data = {
        "event": f"cache_{operation}",
        "request_type": request_type,
        "cache_key": cache_key[:16],  # First 16 chars
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if entity_type and entity_id:
        log_data["entity_type"] = entity_type
        log_data[f"{entity_type}_id"] = str(entity_id)
    
    if details:
        log_data.update(details)
    
    if operation == "error":
        logger.error(json.dumps(log_data))
    else:
        logger.info(json.dumps(log_data))


def log_retry_attempt(
    task_name: str,
    entity_type: str,
    entity_id: UUID,
    retry_count: int,
    max_retries: int,
    error_message: Optional[str] = None
) -> None:
    """Log a retry attempt.
    
    Args:
        task_name: Name of task being retried
        entity_type: Entity type
        entity_id: Entity UUID
        retry_count: Current retry count
        max_retries: Maximum retries allowed
        error_message: Error that triggered retry
    """
    logger = logging.getLogger("alfrd.retry")
    
    log_data = {
        "event": "retry_attempt",
        "task_name": task_name,
        "entity_type": entity_type,
        f"{entity_type}_id": str(entity_id),
        "retry_count": retry_count,
        "max_retries": max_retries,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if error_message:
        log_data["error_message"] = error_message
    
    logger.warning(json.dumps(log_data))