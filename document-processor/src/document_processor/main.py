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




async def main(run_once: bool = False, doc_id: str = None):
    """Main entry point."""
    # Initialize ALFRD logging system
    from shared.logging_config import AlfrdLogger
    AlfrdLogger.setup()
    
    # Configure Prefect server to listen on 0.0.0.0 for Docker
    os.environ.setdefault("PREFECT_SERVER_API_HOST", "0.0.0.0")
    os.environ.setdefault("PREFECT_API_URL", "http://0.0.0.0:4200/api")
    
    # Disable concurrency limit warnings - limits are advisory only in local mode
    os.environ["PREFECT_LOGGING_LEVEL"] = "INFO"
    
    settings = Settings()
    
    # Limit ThreadPoolExecutor threads for blocking I/O operations
    import concurrent.futures
    loop = asyncio.get_event_loop()
    loop.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=settings.prefect_max_threads)
    )
    
    print("\n" + "=" * 80)
    print("🚀 ALFRD Document Processor - Prefect Mode")
    if run_once:
        print("   Mode: Run once and exit")
    if doc_id:
        print(f"   Processing single document: {doc_id}")
    print("=" * 80)
    print()
    
    print(f"📊 Concurrency Limits:")
    print(f"   Max Threads: {settings.prefect_max_threads}")
    print(f"   Document Flows: {settings.prefect_max_document_flows} concurrent")
    print(f"   File Flows: {settings.prefect_max_file_flows} concurrent")
    print(f"   Textract Tasks: {settings.prefect_textract_workers} concurrent")
    print(f"   Bedrock Tasks: {settings.prefect_bedrock_workers} concurrent")
    print(f"   File Generation Tasks: {settings.prefect_file_generation_workers} concurrent")
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
    
    # Run orchestrator (it will scan inbox periodically)
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