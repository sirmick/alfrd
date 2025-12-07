"""Prefect-based document processor entry point."""

import asyncio
import argparse
from pathlib import Path
import sys
import os
from uuid import UUID

# Path setup
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root for shared
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))  # MCP server source
sys.path.insert(0, str(Path(__file__).parent.parent))  # document-processor/src

from shared.config import Settings
from shared.database import AlfrdDatabase
from shared.types import DocumentStatus
from mcp_server.llm.bedrock import BedrockClient
from document_processor.flows.orchestrator import main_orchestrator_flow
from document_processor.flows import process_document_flow


async def scan_inbox_and_create_pending(settings: Settings):
    """
    Scan inbox for new folders and create pending database entries.
    
    (Existing logic from old main.py - unchanged)
    """
    from document_processor.detector import FileDetector
    from shared.constants import META_JSON_FILENAME
    from datetime import datetime, timezone
    import json
    import shutil
    
    detector = FileDetector()
    inbox = settings.inbox_path
    
    if not inbox.exists():
        inbox.mkdir(parents=True, exist_ok=True)
        return
    
    folders = [f for f in inbox.iterdir() if f.is_dir()]
    if not folders:
        return
    
    # Get existing document IDs
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    try:
        all_docs = await db.list_documents(limit=10000)
        existing_ids = set(doc['id'] for doc in all_docs)
        
        new_count = 0
        for folder_path in folders:
            is_valid, error, meta = detector.validate_document_folder(folder_path)
            
            if not is_valid:
                continue
            
            doc_id = UUID(meta.get('id'))
            
            if doc_id in existing_ids:
                continue
            
            # Create storage paths
            now = datetime.now(timezone.utc)
            year_month = now.strftime("%Y/%m")
            base_path = settings.documents_path / year_month
            raw_path = base_path / "raw" / str(doc_id)
            text_path = base_path / "text"
            meta_path = base_path / "meta"
            
            for path in [raw_path, text_path, meta_path]:
                path.mkdir(parents=True, exist_ok=True)
            
            # Copy folder
            shutil.copytree(folder_path, raw_path, dirs_exist_ok=True)
            
            # Create empty text file
            text_file = text_path / f"{doc_id}.txt"
            text_file.write_text("")
            
            # Save metadata
            detailed_meta = {
                'original_meta': meta,
                'processed_at': now.isoformat()
            }
            meta_file = meta_path / f"{doc_id}.json"
            meta_file.write_text(json.dumps(detailed_meta, indent=2))
            
            # Calculate size
            total_size = sum(
                f.stat().st_size
                for f in folder_path.rglob('*')
                if f.is_file()
            )
            
            # Create document record
            await db.create_document(
                doc_id=doc_id,
                filename=folder_path.name,
                original_path=str(folder_path),
                file_type='folder',
                file_size=total_size,
                status=DocumentStatus.PENDING,
                raw_document_path=str(raw_path),
                extracted_text_path=str(text_file),
                metadata_path=str(meta_file),
                folder_path=str(folder_path)
            )
            
            new_count += 1
        
        if new_count > 0:
            print(f"✅ Registered {new_count} new document(s)")
    
    finally:
        await db.close()


async def main(run_once: bool = False, doc_id: str = None):
    """Main entry point."""
    # Configure Prefect server to listen on 0.0.0.0 for Docker
    os.environ.setdefault("PREFECT_SERVER_API_HOST", "0.0.0.0")
    os.environ.setdefault("PREFECT_API_URL", "http://0.0.0.0:4200/api")
    
    # Disable concurrency limit warnings - limits are advisory only in local mode
    os.environ["PREFECT_LOGGING_LEVEL"] = "INFO"
    
    settings = Settings()
    
    print("\n" + "=" * 80)
    print("🚀 ALFRD Document Processor - Prefect Mode")
    if run_once:
        print("   Mode: Run once and exit")
    if doc_id:
        print(f"   Processing single document: {doc_id}")
    print("=" * 80)
    print()
    
    print("📊 Concurrency Limits: aws-textract=3, aws-bedrock=5, file-generation=2")
    print("   (Advisory only - enforced in production Prefect Server)")
    print()
    
    # Process single document
    if doc_id:
        print(f"Processing document {doc_id}...")
        
        db = AlfrdDatabase(settings.database_url)
        await db.initialize()
        
        bedrock_client = BedrockClient(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            aws_region=settings.aws_region
        )
        
        try:
            await process_document_flow(UUID(doc_id), db, bedrock_client)
            print(f"✅ Document {doc_id} processed")
        finally:
            await db.close()
        
        return
    
    # Scan inbox first
    print("📂 Scanning inbox for new documents...")
    await scan_inbox_and_create_pending(settings)
    print()
    
    # Run orchestrator
    print("🔧 Starting Prefect orchestrator...")
    await main_orchestrator_flow(settings, run_once=run_once)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ALFRD Document Processor (Prefect)"
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process all pending documents and exit"
    )
    parser.add_argument(
        "--doc-id",
        help="Process single document by ID"
    )
    args = parser.parse_args()
    
    asyncio.run(main(run_once=args.once, doc_id=args.doc_id))