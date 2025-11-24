"""Event emitter for notifying API server of document processing events."""

import httpx
from datetime import datetime
from uuid import uuid4
from typing import Dict
import sys
from pathlib import Path

# Add parent directories to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.config import Settings


class EventEmitter:
    """Emit events to the API server via HTTP."""
    
    def __init__(self, settings: Settings):
        """
        Initialize the event emitter.
        
        Args:
            settings: Application settings
        """
        self.api_url = f"http://localhost:{settings.api_port}"
        self.timeout = 10.0
    
    async def emit_document_processed(
        self, 
        document_id: str, 
        status: str, 
        error: str = None
    ) -> bool:
        """
        Emit a document_processed event to the API server.
        
        Args:
            document_id: ID of the processed document
            status: Processing status (completed, failed)
            error: Error message if failed
            
        Returns:
            True if event was successfully sent, False otherwise
        """
        event = {
            "event_type": "document_processed",
            "event_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "document_id": document_id,
                "status": status,
                "error": error
            }
        }
        
        return await self._send_event(event)
    
    async def emit_ocr_started(self, document_id: str, file_type: str) -> bool:
        """
        Emit an ocr_started event.
        
        Args:
            document_id: ID of the document
            file_type: Type of file (image, pdf)
            
        Returns:
            True if successful
        """
        event = {
            "event_type": "ocr_started",
            "event_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "document_id": document_id,
                "file_type": file_type
            }
        }
        
        return await self._send_event(event)
    
    async def emit_ocr_completed(
        self, 
        document_id: str, 
        text_length: int,
        confidence: float
    ) -> bool:
        """
        Emit an ocr_completed event.
        
        Args:
            document_id: ID of the document
            text_length: Length of extracted text
            confidence: OCR confidence score
            
        Returns:
            True if successful
        """
        event = {
            "event_type": "ocr_completed",
            "event_id": str(uuid4()),
            "timestamp": datetime.utcnow().isoformat(),
            "data": {
                "document_id": document_id,
                "text_length": text_length,
                "confidence": confidence
            }
        }
        
        return await self._send_event(event)
    
    async def _send_event(self, event: Dict) -> bool:
        """
        Send event to API server.
        
        Args:
            event: Event payload
            
        Returns:
            True if successful, False otherwise
        """
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.api_url}/api/v1/events/document-processed",
                    json=event,
                    timeout=self.timeout
                )
                response.raise_for_status()
                print(f"✓ Event sent: {event['event_type']} for document {event['data'].get('document_id', 'N/A')}")
                return True
            except httpx.HTTPError as e:
                print(f"✗ Failed to send event: {e}")
                # Don't fail document processing if event fails
                return False
            except Exception as e:
                print(f"✗ Unexpected error sending event: {e}")
                return False