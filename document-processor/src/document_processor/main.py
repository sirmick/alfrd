"""Simple asyncio document processor entry point."""

import asyncio
import argparse
from pathlib import Path
import sys
from uuid import UUID

# Path setup
_script_dir = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(_script_dir))  # Project root for shared
sys.path.insert(0, str(_script_dir / "mcp-server" / "src"))  # MCP server source
sys.path.insert(0, str(Path(__file__).parent.parent))  # document-processor/src

from shared.config import Settings
from document_processor.orchestrator import SimpleOrchestrator




async def main(run_once: bool = False, doc_id: str = None):
    """Main entry point."""
    # Initialize ALFRD logging system
    from shared.logging_config import AlfrdLogger
    AlfrdLogger.setup()
    
    settings = Settings()
    
    # Limit ThreadPoolExecutor threads for blocking I/O operations
    import concurrent.futures
    loop = asyncio.get_event_loop()
    loop.set_default_executor(
        concurrent.futures.ThreadPoolExecutor(max_workers=settings.prefect_max_threads)
    )
    
    print("\n" + "=" * 80)
    print("🚀 ALFRD Document Processor - Simple Asyncio Mode")
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
    
    # Create orchestrator
    orchestrator = SimpleOrchestrator(settings)
    
    # Process single document
    if doc_id:
        print(f"Processing document {doc_id}...")
        await orchestrator.initialize()
        
        try:
            await orchestrator._process_document(UUID(doc_id))
            print(f"✅ Document {doc_id} processed")
        finally:
            await orchestrator.db.close()
        
        return
    
    # Run orchestrator (it will scan inbox periodically)
    print("🔧 Starting simple asyncio orchestrator...")
    await orchestrator.run(run_once=run_once)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="ALFRD Document Processor (Simple Asyncio)"
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