"""Event logging utilities for ALFRD.

This module provides easy-to-use functions for logging events during document processing.
It wraps the database event logging methods and provides additional functionality like
automatic state transition logging via context managers.
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Optional, Dict, Any
from uuid import UUID

from shared.database import AlfrdDatabase

logger = logging.getLogger(__name__)


class EventLogger:
    """Helper class for logging events during document processing."""

    def __init__(self, db: AlfrdDatabase):
        """Initialize event logger with database connection.

        Args:
            db: AlfrdDatabase instance
        """
        self.db = db

    async def log_state_change(
        self,
        entity_type: str,
        entity_id: UUID,
        old_status: str,
        new_status: str,
        task_name: str = None,
        details: dict = None
    ):
        """Log a state transition event.

        Args:
            entity_type: 'document', 'file', or 'series'
            entity_id: UUID of the entity
            old_status: Previous status
            new_status: New status
            task_name: Name of the task
            details: Additional context
        """
        try:
            await self.db.log_state_transition(
                entity_type=entity_type,
                entity_id=entity_id,
                old_status=old_status,
                new_status=new_status,
                task_name=task_name,
                details=details
            )
            logger.debug(
                f"Logged state transition: {entity_type}/{entity_id} "
                f"{old_status} -> {new_status}"
            )
        except Exception as e:
            # Don't let logging failures break processing
            logger.warning(f"Failed to log state transition: {e}")

    async def log_llm_call(
        self,
        entity_type: str,
        entity_id: UUID,
        event_type: str,
        model: str,
        prompt: str,
        response: str,
        request_tokens: int = None,
        response_tokens: int = None,
        latency_ms: int = None,
        cost_usd: float = None,
        task_name: str = None,
        details: dict = None
    ):
        """Log an LLM request event.

        Args:
            entity_type: 'document', 'file', or 'series'
            entity_id: UUID of the entity
            event_type: Specific type (e.g., 'llm_classify', 'llm_summarize')
            model: Model used
            prompt: Prompt sent
            response: Response received
            request_tokens: Input tokens
            response_tokens: Output tokens
            latency_ms: Latency in ms
            cost_usd: Cost in USD
            task_name: Task name
            details: Additional context
        """
        try:
            await self.db.log_llm_request(
                entity_type=entity_type,
                entity_id=entity_id,
                event_type=event_type,
                llm_model=model,
                llm_prompt_text=prompt,
                llm_response_text=response,
                llm_request_tokens=request_tokens,
                llm_response_tokens=response_tokens,
                llm_latency_ms=latency_ms,
                llm_cost_usd=cost_usd,
                task_name=task_name,
                details=details
            )
            logger.debug(
                f"Logged LLM call: {entity_type}/{entity_id} "
                f"type={event_type} model={model}"
            )
        except Exception as e:
            # Don't let logging failures break processing
            logger.warning(f"Failed to log LLM call: {e}")

    async def log_processing_event(
        self,
        entity_type: str,
        entity_id: UUID,
        event_type: str,
        task_name: str = None,
        details: dict = None
    ):
        """Log a processing event.

        Args:
            entity_type: 'document', 'file', or 'series'
            entity_id: UUID of the entity
            event_type: Specific type (e.g., 'ocr_complete', 'file_generated')
            task_name: Task name
            details: Additional context
        """
        try:
            document_id = entity_id if entity_type == 'document' else None
            file_id = entity_id if entity_type == 'file' else None
            series_id = entity_id if entity_type == 'series' else None

            await self.db.log_event(
                event_category='processing',
                event_type=event_type,
                document_id=document_id,
                file_id=file_id,
                series_id=series_id,
                task_name=task_name,
                details=details
            )
            logger.debug(
                f"Logged processing event: {entity_type}/{entity_id} "
                f"type={event_type}"
            )
        except Exception as e:
            logger.warning(f"Failed to log processing event: {e}")

    async def log_error_event(
        self,
        entity_type: str,
        entity_id: UUID,
        error_message: str,
        task_name: str = None,
        details: dict = None
    ):
        """Log an error event.

        Args:
            entity_type: 'document', 'file', or 'series'
            entity_id: UUID of the entity
            error_message: Error message
            task_name: Task name
            details: Additional context
        """
        try:
            await self.db.log_error(
                entity_type=entity_type,
                entity_id=entity_id,
                error_message=error_message,
                task_name=task_name,
                details=details
            )
            logger.debug(
                f"Logged error: {entity_type}/{entity_id} "
                f"task={task_name} error={error_message[:50]}..."
            )
        except Exception as e:
            logger.warning(f"Failed to log error event: {e}")

    @asynccontextmanager
    async def track_llm_call(
        self,
        entity_type: str,
        entity_id: UUID,
        event_type: str,
        model: str,
        prompt: str,
        task_name: str = None
    ):
        """Context manager to track LLM calls with timing.

        Usage:
            async with event_logger.track_llm_call(
                'document', doc_id, 'llm_classify', 'nova-lite', prompt, 'classify_step'
            ) as tracker:
                response = await call_llm(prompt)
                tracker.set_response(response, tokens_in=100, tokens_out=50)

        Args:
            entity_type: 'document', 'file', or 'series'
            entity_id: UUID of the entity
            event_type: Type of LLM call
            model: Model being used
            prompt: Prompt being sent
            task_name: Task name
        """

        class LLMCallTracker:
            def __init__(self, logger_instance):
                self.logger_instance = logger_instance
                self.start_time = time.time()
                self.response = None
                self.request_tokens = None
                self.response_tokens = None
                self.cost_usd = None
                self.details = None

            def set_response(
                self,
                response: str,
                tokens_in: int = None,
                tokens_out: int = None,
                cost: float = None,
                details: dict = None
            ):
                self.response = response
                self.request_tokens = tokens_in
                self.response_tokens = tokens_out
                self.cost_usd = cost
                self.details = details

        tracker = LLMCallTracker(self)
        try:
            yield tracker
        finally:
            latency_ms = int((time.time() - tracker.start_time) * 1000)
            if tracker.response is not None:
                await self.log_llm_call(
                    entity_type=entity_type,
                    entity_id=entity_id,
                    event_type=event_type,
                    model=model,
                    prompt=prompt,
                    response=tracker.response,
                    request_tokens=tracker.request_tokens,
                    response_tokens=tracker.response_tokens,
                    latency_ms=latency_ms,
                    cost_usd=tracker.cost_usd,
                    task_name=task_name,
                    details=tracker.details
                )


# Global event logger instance (initialized when needed)
_event_logger: Optional[EventLogger] = None


def get_event_logger(db: AlfrdDatabase) -> EventLogger:
    """Get or create event logger instance.

    Args:
        db: AlfrdDatabase instance

    Returns:
        EventLogger instance
    """
    global _event_logger
    if _event_logger is None or _event_logger.db != db:
        _event_logger = EventLogger(db)
    return _event_logger
