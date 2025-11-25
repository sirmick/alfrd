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
    
    async def store_document_folder(
        self,
        folder_path: Path,
        doc_id: str,
        meta: Dict,
        extracted_documents: list,
        llm_formatted: Dict
    ) -> str:
        """
        Store document folder with extracted data in LLM-optimized format.
        
        Args:
            folder_path: Path to the document folder
            doc_id: Document ID from meta.json
            meta: Metadata from meta.json
            extracted_documents: List of extracted document data
            llm_formatted: LLM-optimized combined data
            
        Returns:
            Document ID
        """
        now = datetime.utcnow()
        year_month = now.strftime("%Y/%m")
        
        # Create storage paths
        base_path = self.settings.documents_path / year_month
        raw_path = base_path / "raw" / doc_id
        text_path = base_path / "text"
        meta_path = base_path / "meta"
        
        # Create directories
        for path in [raw_path, text_path, meta_path]:
            path.mkdir(parents=True, exist_ok=True)
        
        # Copy entire folder to raw storage
        shutil.copytree(folder_path, raw_path, dirs_exist_ok=True)
        
        # Save combined text for full-text search
        text_file = text_path / f"{doc_id}.txt"
        text_file.write_text(llm_formatted['full_text'])
        
        # Save LLM-formatted data for AI processing
        llm_file = text_path / f"{doc_id}_llm.json"
        llm_file.write_text(json.dumps(llm_formatted, indent=2))
        
        # Save detailed metadata including blocks
        detailed_meta = {
            'original_meta': meta,
            'extracted_documents': extracted_documents,
            'llm_formatted_summary': {
                'document_count': llm_formatted['document_count'],
                'total_chars': llm_formatted['total_chars'],
                'avg_confidence': llm_formatted['avg_confidence']
            },
            'processed_at': now.isoformat()
        }
        meta_file = meta_path / f"{doc_id}.json"
        meta_file.write_text(json.dumps(detailed_meta, indent=2))
        
        # Calculate total file size
        total_size = sum(f.stat().st_size for f in folder_path.rglob('*') if f.is_file())
        
        # Insert into database with PENDING status for worker processing
        conn = duckdb.connect(str(self.db_path))
        try:
            conn.execute("""
                INSERT INTO documents (
                    id, filename, original_path, file_type, file_size,
                    status, raw_document_path, extracted_text_path,
                    metadata_path, folder_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, [
                doc_id,
                folder_path.name,
                str(folder_path),
                'folder',  # Indicate this is a multi-document folder
                total_size,
                DocumentStatus.PENDING,  # Start in PENDING for OCR worker
                str(raw_path),
                str(text_file),
                str(meta_file),
                str(folder_path),  # Save original folder path for worker
                now
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