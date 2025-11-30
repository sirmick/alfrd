"""OCR Worker - Processes documents in 'pending' status with AWS Textract."""

import asyncio
import logging
from pathlib import Path
from typing import List
import sys
import json

# Add parent directories to path
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))

from shared.config import Settings
from shared.types import DocumentStatus
from shared.constants import META_JSON_FILENAME
from shared.database import AlfrdDatabase
from document_processor.workers import BaseWorker
from document_processor.detector import FileDetector
from document_processor.extractors.aws_textract import TextractExtractor
from document_processor.extractors.text import TextExtractor

logger = logging.getLogger(__name__)


class OCRWorker(BaseWorker):
    """Worker that processes documents in 'pending' status with OCR."""
    
    def __init__(self, settings: Settings, db: AlfrdDatabase):
        """
        Initialize OCR worker.
        
        Args:
            settings: Application settings
            db: Shared AlfrdDatabase instance
        """
        super().__init__(
            settings=settings,
            db=db,
            worker_name="OCR Worker",
            source_status=DocumentStatus.PENDING,
            target_status=DocumentStatus.OCR_COMPLETED,
            concurrency=settings.ocr_workers,
            poll_interval=settings.ocr_poll_interval,
        )
    
    async def get_documents(self, status: DocumentStatus, limit: int) -> List[dict]:
        """
        Query database for documents in 'pending' status.
        
        Args:
            status: Document status to query (DocumentStatus.PENDING)
            limit: Maximum number of documents to return
            
        Returns:
            List of document dictionaries
        """
        return await self.db.get_documents_by_status(status, limit)
    
    async def process_document(self, document: dict) -> bool:
        """
        Process a single document: extract text with OCR.
        
        This extracts the core OCR logic from main.py's process_document_folder().
        
        Args:
            document: Document dictionary with id, folder_path, etc.
            
        Returns:
            True if OCR succeeded
            
        Raises:
            Exception: If OCR fails
        """
        doc_id = document["id"]
        folder_path = Path(document["folder_path"]) if document["folder_path"] else Path(document["original_path"])
        
        logger.info(f"OCR processing document {doc_id} from {folder_path}")
        
        try:
            # Update status to ocr_started
            await self.update_status(doc_id, DocumentStatus.OCR_STARTED)
            
            # Read meta.json
            meta_file = folder_path / META_JSON_FILENAME
            if not meta_file.exists():
                raise FileNotFoundError(f"No {META_JSON_FILENAME} found in {folder_path}")
            
            with open(meta_file, 'r') as f:
                meta = json.load(f)
            
            documents_list = meta.get('documents', [])
            if not documents_list:
                raise ValueError("No documents listed in meta.json")
            
            # Process each file
            all_extracted = []
            combined_text = []
            combined_blocks = []
            total_confidence = 0
            
            for doc_item in sorted(documents_list, key=lambda x: x.get('order', 0)):
                file_name = doc_item['file']
                file_type = doc_item['type']
                file_path = folder_path / file_name
                
                if not file_path.exists():
                    logger.warning(f"File not found: {file_path}, skipping")
                    continue
                
                # Extract based on type
                if file_type == 'image':
                    extractor = TextractExtractor()
                    extracted = await extractor.extract_text(file_path)
                elif file_type == 'text':
                    extractor = TextExtractor()
                    extracted = await extractor.extract_text(file_path)
                else:
                    logger.warning(f"Unknown file type '{file_type}' for {file_name}")
                    continue
                
                # Add to combined data
                all_extracted.append({
                    'file': file_name,
                    'type': file_type,
                    'order': doc_item.get('order', 0),
                    'extracted_text': extracted['extracted_text'],
                    'confidence': extracted['confidence'],
                    'metadata': extracted['metadata']
                })
                
                # Build combined text
                combined_text.append(f"--- Document: {file_name} ---")
                combined_text.append(extracted['extracted_text'])
                combined_text.append("")  # Blank line separator
                
                # Add blocks if available (from Textract)
                if 'blocks' in extracted:
                    combined_blocks.append({
                        'file': file_name,
                        'blocks': extracted['blocks']
                    })
                
                total_confidence += extracted['confidence']
                
                logger.info(
                    f"Extracted {len(extracted['extracted_text'])} chars from {file_name} "
                    f"with {extracted['confidence']:.2%} confidence"
                )
            
            if not all_extracted:
                raise ValueError("No documents were successfully extracted")
            
            # Create LLM-optimized format
            avg_confidence = total_confidence / len(all_extracted)
            full_text = '\n'.join(combined_text).strip()
            
            llm_formatted = {
                'full_text': full_text,
                'blocks_by_document': combined_blocks if combined_blocks else None,
                'document_count': len(all_extracted),
                'total_chars': len(full_text),
                'avg_confidence': avg_confidence
            }
            
            # Store extracted data in database
            from shared.database import utc_now
            now = utc_now()
            year_month = now.strftime("%Y/%m")
            base_path = self.settings.documents_path / year_month
            text_path = base_path / "text"
            text_path.mkdir(parents=True, exist_ok=True)
            
            # Save LLM-formatted data
            llm_file = text_path / f"{doc_id}_llm.json"
            llm_file.write_text(json.dumps(llm_formatted, indent=2))
            
            # Save full text
            text_file = text_path / f"{doc_id}.txt"
            text_file.write_text(full_text)
            
            # Update database with extracted text
            await self.db.update_document(
                doc_id=doc_id,
                extracted_text=full_text,
                extracted_text_path=str(text_file)
            )
            
            logger.info(
                f"OCR complete for {doc_id}: {len(full_text)} chars, "
                f"{avg_confidence:.2%} confidence"
            )
            
            # Update status to ocr_completed
            await self.update_status(doc_id, DocumentStatus.OCR_COMPLETED)
            
            return True
            
        except Exception as e:
            logger.error(f"OCR failed for {doc_id}: {e}", exc_info=True)
            await self.update_status(doc_id, DocumentStatus.FAILED, str(e))
            raise