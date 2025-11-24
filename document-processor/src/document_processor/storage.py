"""Document storage module for filesystem and database persistence."""

from pathlib import Path
from datetime import datetime
import shutil
import json
from uuid import uuid4
import duckdb
from typing import Dict
import sys

# Add parent directories to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.config import Settings
from shared.types import DocumentStatus


class DocumentStorage:
    """Store documents in filesystem and database."""
    
    def __init__(self, settings: Settings):
        """
        Initialize document storage.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.db_path = settings.database_path
    
    async def store_document(self, source_path: Path, extracted_data: Dict) -> str:
        """
        Store document and extracted data.
        
        Args:
            source_path: Path to the original document
            extracted_data: Dictionary with extracted text and metadata
            
        Returns:
            Document ID (UUID)
        """
        doc_id = str(uuid4())
        now = datetime.utcnow()
        year_month = now.strftime("%Y/%m")
        
        # Create storage paths
        base_path = self.settings.documents_path / year_month
        raw_path = base_path / "raw"
        text_path = base_path / "text"
        meta_path = base_path / "meta"
        
        # Create directories
        for path in [raw_path, text_path, meta_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        # Copy original file
        dest_file = raw_path / f"{doc_id}{source_path.suffix}"
        shutil.copy2(source_path, dest_file)
        
        # Save extracted text
        text_file = text_path / f"{doc_id}.txt"
        text_file.write_text(extracted_data["extracted_text"])
        
        # Save metadata
        meta_file = meta_path / f"{doc_id}.json"
        meta_file.write_text(json.dumps(extracted_data["metadata"], indent=2))
        
        # Insert into database
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT INTO documents (
                    id, filename, original_path, file_type, file_size,
                    status, raw_document_path, extracted_text_path,
                    metadata_path, extracted_text, created_at, mime_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                doc_id,
                source_path.name,
                str(source_path),
                extracted_data.get("file_type", "unknown"),
                source_path.stat().st_size,
                DocumentStatus.PROCESSING,
                str(dest_file),
                str(text_file),
                str(meta_file),
                extracted_data["extracted_text"],
                now,
                extracted_data.get("mime_type", "")
            ])
        finally:
            conn.close()
        
        return doc_id
    
    async def update_document_status(self, doc_id: str, status: DocumentStatus, error: str = None):
        """
        Update document processing status.
        
        Args:
            doc_id: Document ID
            status: New status
            error: Error message if failed
        """
        conn = duckdb.connect(str(self.db_path))
        try:
            if error:
                conn.execute("""
                    UPDATE documents 
                    SET status = ?, error_message = ?, updated_at = ?
                    WHERE id = ?
                """, [status, error, datetime.utcnow(), doc_id])
            else:
                conn.execute("""
                    UPDATE documents 
                    SET status = ?, processed_at = ?, updated_at = ?
                    WHERE id = ?
                """, [status, datetime.utcnow(), datetime.utcnow(), doc_id])
        finally:
            conn.close()
    
    async def get_document(self, doc_id: str) -> Dict:
        """
        Retrieve document metadata from database.
        
        Args:
            doc_id: Document ID
            
        Returns:
            Dictionary with document metadata
        """
        conn = duckdb.connect(str(self.db_path))
        try:
            result = conn.execute("""
                SELECT id, filename, file_type, status, category, vendor, 
                       amount, due_date, created_at, extracted_text
                FROM documents 
                WHERE id = ?
            """, [doc_id]).fetchone()
            
            if not result:
                return None
            
            return {
                "id": result[0],
                "filename": result[1],
                "file_type": result[2],
                "status": result[3],
                "category": result[4],
                "vendor": result[5],
                "amount": result[6],
                "due_date": result[7],
                "created_at": result[8],
                "extracted_text": result[9]
            }
        finally:
            conn.close()