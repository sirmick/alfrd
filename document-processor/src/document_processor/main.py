"""Main document processing loop."""

import asyncio
from pathlib import Path
from typing import Dict, List
import sys
import json
import logging

# Standalone PYTHONPATH setup - add both project root and src directory
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root for shared
sys.path.insert(0, str(Path(__file__).parent.parent))  # src for document_processor

from shared.config import Settings
from shared.types import DocumentStatus
from shared.constants import DEBOUNCE_SECONDS, META_JSON_FILENAME

from document_processor.detector import FileDetector
from document_processor.extractors.aws_textract import TextractExtractor
from document_processor.extractors.text import TextExtractor
from document_processor.storage import DocumentStorage
from document_processor.events import EventEmitter

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def process_document_folder(folder_path: Path, settings: Settings) -> bool:
    """
    Process a document folder through the complete pipeline.
    
    Pipeline:
    1. Read meta.json for document structure
    2. Process each file (OCR or text extraction)
    3. Combine into LLM-optimized format
    4. Store document + extracted data
    5. Emit event to API server
    
    Args:
        folder_path: Path to the document folder
        settings: Application settings
        
    Returns:
        True if processing succeeded, False otherwise
    """
    print(f"\n📁 Processing folder: {folder_path.name}")
    logger.info(f"Starting processing for folder: {folder_path}")
    
    detector = FileDetector()
    storage = DocumentStorage(settings)
    events = EventEmitter(settings)
    
    doc_id = None
    
    try:
        # Step 1: Read meta.json
        meta_file = folder_path / META_JSON_FILENAME
        if not meta_file.exists():
            print(f"  ✗ No {META_JSON_FILENAME} found in folder")
            logger.warning(f"Missing {META_JSON_FILENAME} in {folder_path}")
            return False
        
        with open(meta_file, 'r') as f:
            meta = json.load(f)
        
        doc_id = meta.get('id')
        documents = meta.get('documents', [])
        
        if not documents:
            print(f"  ✗ No documents listed in {META_JSON_FILENAME}")
            logger.warning(f"Empty documents list in {meta_file}")
            return False
        
        print(f"  ✓ Found {len(documents)} document(s) to process")
        logger.info(f"Processing {len(documents)} documents from meta.json")
        
        # Step 2: Process each document file
        all_extracted = []
        combined_text = []
        combined_blocks = []
        total_confidence = 0
        
        for doc_item in sorted(documents, key=lambda x: x.get('order', 0)):
            file_name = doc_item['file']
            file_type = doc_item['type']
            file_path = folder_path / file_name
            
            if not file_path.exists():
                print(f"  ⚠️  File not found: {file_name}, skipping")
                logger.warning(f"File not found: {file_path}")
                continue
            
            print(f"  📄 Processing: {file_name} (type: {file_type})")
            logger.info(f"Extracting text from {file_name} (type: {file_type})")
            
            # Extract based on type
            if file_type == 'image':
                extractor = TextractExtractor()
                extracted = await extractor.extract_text(file_path)
            elif file_type == 'text':
                extractor = TextExtractor()
                extracted = await extractor.extract_text(file_path)
            else:
                print(f"  ⚠️  Unknown type: {file_type}, skipping")
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
            
            text_len = len(extracted['extracted_text'])
            conf = extracted['confidence']
            print(f"    ✓ Extracted {text_len} chars (confidence: {conf:.2%})")
            logger.info(f"Extracted {text_len} characters from {file_name} with {conf:.2%} confidence")
        
        if not all_extracted:
            print(f"  ✗ No documents were successfully extracted")
            logger.error(f"Failed to extract any documents from {folder_path}")
            return False
        
        # Step 3: Create LLM-optimized format
        avg_confidence = total_confidence / len(all_extracted)
        full_text = '\n'.join(combined_text).strip()
        
        llm_formatted = {
            'full_text': full_text,
            'blocks_by_document': combined_blocks if combined_blocks else None,
            'document_count': len(all_extracted),
            'total_chars': len(full_text),
            'avg_confidence': avg_confidence
        }
        
        print(f"  ✓ Combined {len(all_extracted)} documents: {len(full_text)} total chars")
        print(f"    Average confidence: {avg_confidence:.2%}")
        logger.info(f"Combined extraction: {len(full_text)} chars, {avg_confidence:.2%} confidence")
        
        # Step 4: Store document
        print(f"  💾 Storing document...")
        logger.info(f"Storing document folder {folder_path.name}")
        stored_id = await storage.store_document_folder(
            folder_path=folder_path,
            doc_id=doc_id,
            meta=meta,
            extracted_documents=all_extracted,
            llm_formatted=llm_formatted
        )
        print(f"  ✓ Stored with ID: {stored_id}")
        logger.info(f"Stored document with ID: {stored_id}")
        
        # Step 5: Emit events
        print(f"  📡 Notifying API server...")
        await events.emit_ocr_completed(stored_id, len(full_text), avg_confidence)
        await events.emit_document_processed(stored_id, DocumentStatus.COMPLETED)
        logger.info(f"Events emitted for document {stored_id}")
        
        # Step 6: Move processed folder
        processed_dir = settings.inbox_path.parent / "processed"
        processed_dir.mkdir(exist_ok=True, parents=True)
        
        new_path = processed_dir / folder_path.name
        # Use rename if possible, otherwise copy and delete
        try:
            folder_path.rename(new_path)
        except:
            import shutil
            shutil.copytree(folder_path, new_path)
            shutil.rmtree(folder_path)
        
        print(f"  ✓ Moved to processed: {new_path}")
        logger.info(f"Moved folder to {new_path}")
        
        # Update status
        await storage.update_document_status(stored_id, DocumentStatus.COMPLETED)
        
        print(f"  ✅ Processing complete!")
        logger.info(f"Successfully processed document {stored_id}")
        return True
        
    except Exception as e:
        print(f"  ✗ Error processing folder {folder_path}: {e}")
        logger.error(f"Error processing {folder_path}: {e}", exc_info=True)
        
        # Update document status if we have an ID
        if doc_id:
            await storage.update_document_status(
                doc_id, 
                DocumentStatus.FAILED, 
                str(e)
            )
            await events.emit_document_processed(
                doc_id, 
                DocumentStatus.FAILED, 
                str(e)
            )
        
        # Move to failed directory
        try:
            failed_dir = settings.inbox_path.parent / "failed"
            failed_dir.mkdir(exist_ok=True, parents=True)
            new_path = failed_dir / folder_path.name
            try:
                folder_path.rename(new_path)
            except:
                import shutil
                shutil.copytree(folder_path, new_path)
                shutil.rmtree(folder_path)
            print(f"  ⚠️  Moved to failed: {new_path}")
            logger.info(f"Moved failed folder to {new_path}")
        except Exception as move_error:
            print(f"  ⚠️  Could not move failed folder: {move_error}")
            logger.error(f"Failed to move folder: {move_error}")
        
        return False


async def process_inbox(settings: Settings) -> Dict[str, int]:
    """
    Process all document folders in the inbox directory.
    
    Args:
        settings: Application settings
        
    Returns:
        Dictionary with processing statistics
    """
    inbox = settings.inbox_path
    
    if not inbox.exists():
        print(f"📁 Inbox directory does not exist: {inbox}")
        logger.warning(f"Inbox directory does not exist: {inbox}")
        inbox.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created inbox directory: {inbox}")
        logger.info(f"Created inbox directory: {inbox}")
        return {"total": 0, "success": 0, "failed": 0}
    
    # Get all folders in inbox (each folder is a document)
    # Skip files like .gitkeep
    folders = [f for f in inbox.iterdir() if f.is_dir()]
    
    if not folders:
        print("📭 No document folders in inbox")
        logger.info("No document folders found in inbox")
        return {"total": 0, "success": 0, "failed": 0}
    
    print(f"\n📬 Found {len(folders)} document folder(s) to process")
    logger.info(f"Found {len(folders)} document folders to process")
    print("=" * 80)
    
    success_count = 0
    failed_count = 0
    
    for folder_path in folders:
        success = await process_document_folder(folder_path, settings)
        if success:
            success_count += 1
        else:
            failed_count += 1
        
        # Small delay between folders to avoid overwhelming the API
        await asyncio.sleep(DEBOUNCE_SECONDS)
    
    print("\n" + "=" * 80)
    print(f"📊 Processing Summary:")
    print(f"   Total: {len(folders)}")
    print(f"   ✅ Success: {success_count}")
    print(f"   ✗ Failed: {failed_count}")
    print("=" * 80)
    
    logger.info(f"Processing complete: {success_count} success, {failed_count} failed")
    
    return {
        "total": len(folders),
        "success": success_count,
        "failed": failed_count
    }


async def main():
    """Main entry point for batch document processing."""
    print("\n" + "=" * 80)
    print("🚀 Document Processor - Batch Mode")
    print("=" * 80)
    
    logger.info("Starting document processor in batch mode")
    
    settings = Settings()
    
    print(f"📂 Inbox: {settings.inbox_path}")
    print(f"💾 Database: {settings.database_path}")
    print(f"📁 Documents: {settings.documents_path}")
    
    logger.info(f"Inbox: {settings.inbox_path}")
    logger.info(f"Database: {settings.database_path}")
    logger.info(f"Documents: {settings.documents_path}")
    
    stats = await process_inbox(settings)
    
    # Exit with appropriate code
    if stats["total"] == 0:
        print("\n👋 No documents to process")
        logger.info("No documents to process")
        sys.exit(0)
    elif stats["failed"] == 0:
        print("\n✅ All documents processed successfully")
        logger.info("All documents processed successfully")
        sys.exit(0)
    elif stats["success"] == 0:
        print("\n❌ All documents failed to process")
        logger.error("All documents failed to process")
        sys.exit(1)
    else:
        print("\n⚠️  Some documents failed to process")
        logger.warning("Some documents failed to process")
        sys.exit(0)  # Partial success is still success


if __name__ == "__main__":
    asyncio.run(main())