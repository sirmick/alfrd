"""Main document processing loop."""

import asyncio
from pathlib import Path
from typing import Dict
import sys

# Add parent directories to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.config import Settings
from shared.types import DocumentStatus
from shared.constants import DEBOUNCE_SECONDS

from document_processor.detector import FileDetector
from document_processor.extractors.image_ocr import ClaudeVisionExtractor
from document_processor.extractors.pdf import PDFExtractor
from document_processor.storage import DocumentStorage
from document_processor.events import EventEmitter


async def process_document(file_path: Path, settings: Settings) -> bool:
    """
    Process a single document through the complete pipeline.
    
    Pipeline:
    1. Detect file type
    2. Extract text (OCR or PDF)
    3. Store document + extracted data
    4. Emit event to API server
    
    Args:
        file_path: Path to the document file
        settings: Application settings
        
    Returns:
        True if processing succeeded, False otherwise
    """
    print(f"\n📄 Processing: {file_path.name}")
    
    detector = FileDetector()
    storage = DocumentStorage(settings)
    events = EventEmitter(settings)
    
    doc_id = None
    
    try:
        # Step 1: Detect file type
        print(f"  🔍 Detecting file type...")
        file_type, mime_type = detector.detect_type(file_path)
        
        if not detector.is_supported(file_path):
            print(f"  ✗ Unsupported file type: {file_type}")
            return False
        
        print(f"  ✓ Detected: {file_type} ({mime_type})")
        
        # Step 2: Extract text
        print(f"  📝 Extracting text...")
        
        if file_type == "image":
            extractor = ClaudeVisionExtractor(settings.claude_api_key)
            extracted = await extractor.extract_text(file_path)
        elif file_type == "pdf":
            extractor = PDFExtractor()
            extracted = await extractor.extract_text(file_path)
        else:
            print(f"  ✗ Unknown file type: {file_type}")
            return False
        
        if not extracted.get("extracted_text"):
            print(f"  ✗ No text extracted")
            return False
        
        text_length = len(extracted["extracted_text"])
        confidence = extracted.get("confidence", 0.0)
        print(f"  ✓ Extracted {text_length} characters (confidence: {confidence:.2f})")
        
        # Add file metadata to extracted data
        extracted["file_type"] = file_type
        extracted["mime_type"] = mime_type
        
        # Step 3: Store document
        print(f"  💾 Storing document...")
        doc_id = await storage.store_document(file_path, extracted)
        print(f"  ✓ Stored with ID: {doc_id}")
        
        # Step 4: Emit events
        print(f"  📡 Notifying API server...")
        await events.emit_ocr_completed(doc_id, text_length, confidence)
        await events.emit_document_processed(doc_id, DocumentStatus.COMPLETED)
        
        # Step 5: Move processed file
        processed_dir = settings.inbox_path.parent / "processed"
        processed_dir.mkdir(exist_ok=True, parents=True)
        
        new_path = processed_dir / file_path.name
        file_path.rename(new_path)
        print(f"  ✓ Moved to processed: {new_path}")
        
        # Update status to completed
        await storage.update_document_status(doc_id, DocumentStatus.COMPLETED)
        
        print(f"  ✅ Processing complete!")
        return True
        
    except Exception as e:
        print(f"  ✗ Error processing {file_path}: {e}")
        
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
            file_path.rename(failed_dir / file_path.name)
            print(f"  ⚠️  Moved to failed: {failed_dir / file_path.name}")
        except Exception as move_error:
            print(f"  ⚠️  Could not move failed file: {move_error}")
        
        return False


async def process_inbox(settings: Settings) -> Dict[str, int]:
    """
    Process all documents in the inbox directory.
    
    Args:
        settings: Application settings
        
    Returns:
        Dictionary with processing statistics
    """
    inbox = settings.inbox_path
    
    if not inbox.exists():
        print(f"📁 Inbox directory does not exist: {inbox}")
        inbox.mkdir(parents=True, exist_ok=True)
        print(f"📁 Created inbox directory: {inbox}")
        return {"total": 0, "success": 0, "failed": 0}
    
    # Get all files in inbox
    files = [f for f in inbox.iterdir() if f.is_file()]
    
    if not files:
        print("📭 No files in inbox")
        return {"total": 0, "success": 0, "failed": 0}
    
    print(f"\n📬 Found {len(files)} file(s) to process")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    
    for file_path in files:
        success = await process_document(file_path, settings)
        if success:
            success_count += 1
        else:
            failed_count += 1
        
        # Small delay between files to avoid overwhelming the API
        await asyncio.sleep(DEBOUNCE_SECONDS)
    
    print("\n" + "=" * 60)
    print(f"📊 Processing Summary:")
    print(f"   Total: {len(files)}")
    print(f"   ✅ Success: {success_count}")
    print(f"   ✗ Failed: {failed_count}")
    print("=" * 60)
    
    return {
        "total": len(files),
        "success": success_count,
        "failed": failed_count
    }


async def main():
    """Main entry point for batch document processing."""
    print("\n" + "=" * 60)
    print("🚀 Document Processor - Batch Mode")
    print("=" * 60)
    
    settings = Settings()
    
    print(f"📂 Inbox: {settings.inbox_path}")
    print(f"💾 Database: {settings.database_path}")
    print(f"📁 Documents: {settings.documents_path}")
    
    stats = await process_inbox(settings)
    
    # Exit with appropriate code
    if stats["total"] == 0:
        print("\n👋 No documents to process")
        sys.exit(0)
    elif stats["failed"] == 0:
        print("\n✅ All documents processed successfully")
        sys.exit(0)
    elif stats["success"] == 0:
        print("\n❌ All documents failed to process")
        sys.exit(1)
    else:
        print("\n⚠️  Some documents failed to process")
        sys.exit(0)  # Partial success is still success


if __name__ == "__main__":
    asyncio.run(main())