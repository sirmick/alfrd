#!/usr/bin/env python3
"""
View document information from the database.

Usage:
    python scripts/view-document.py [document_id]
    python scripts/view-document.py --list
    python scripts/view-document.py --recent [N]
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime
import asyncio

# Add project root to path (go up to esec/)
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent  # cli/ -> document_processor/ -> src/ -> document-processor/ -> esec/
sys.path.insert(0, str(_project_root))

from shared.config import Settings
from shared.database import AlfrdDatabase


def format_field(label: str, value, width: int = 20):
    """Format a field for display."""
    if value is None:
        return f"{label:>{width}}: (none)"
    return f"{label:>{width}}: {value}"


async def view_document(doc_id: str, settings: Settings):
    """View detailed information about a document."""
    db = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=1,
        pool_max_size=3,
        pool_timeout=30.0
    )
    await db.initialize()
    
    try:
        # Get document info - try full ID first
        doc = await db.get_document(doc_id)
        
        # If not found, try searching by partial ID
        if not doc:
            all_docs = await db.list_documents(limit=1000)
            matching = [d for d in all_docs if d['id'].startswith(doc_id)]
            if matching:
                doc = matching[0]
        
        if not doc:
            print(f"❌ Document not found: {doc_id}")
            return
        
        # Extract fields
        id = doc['id']
        filename = doc['filename']
        status = doc['status']
        doc_type = doc.get('document_type')
        confidence = doc.get('classification_confidence')
        reasoning = doc.get('classification_reasoning')
        suggested_type = doc.get('suggested_type')
        secondary_tags = doc.get('secondary_tags')
        vendor = doc.get('vendor')
        amount = doc.get('amount')
        due_date = doc.get('due_date')
        created = doc['created_at']
        updated = doc['updated_at']
        processed = doc.get('processed_at')
        text = doc.get('extracted_text')
        text_path = doc.get('extracted_text_path')
        folder = doc.get('folder_path')
        error = doc.get('error_message')
        structured_data = doc.get('structured_data')
        tags = doc.get('tags')
        folder_metadata = doc.get('folder_metadata')
        
        # Display header
        print("\n" + "=" * 80)
        print(f"📄 DOCUMENT: {filename}")
        print("=" * 80)
        print()
        
        # Basic info
        print("📋 BASIC INFORMATION")
        print("-" * 80)
        print(format_field("ID", id[:16] + "..."))
        print(format_field("Filename", filename))
        print(format_field("Status", status))
        print(format_field("Created", created))
        print(format_field("Updated", updated))
        if processed:
            print(format_field("Processed", processed))
        print()
        
        # Classification
        if doc_type or confidence or reasoning or suggested_type or secondary_tags:
            print("🏷️  CLASSIFICATION")
            print("-" * 80)
            if doc_type:
                print(format_field("Type", doc_type.upper()))
            if confidence:
                print(format_field("Confidence", f"{confidence:.1%}"))
            if suggested_type:
                print(format_field("Suggested Type", suggested_type.upper()))
            if secondary_tags:
                import json
                try:
                    if isinstance(secondary_tags, str):
                        tags_list = json.loads(secondary_tags)
                    else:
                        tags_list = secondary_tags
                    if tags_list:
                        print(format_field("Secondary Tags", ", ".join(tags_list)))
                except (json.JSONDecodeError, TypeError):
                    pass
            if tags:
                import json
                try:
                    if isinstance(tags, str):
                        tags_list = json.loads(tags)
                    else:
                        tags_list = tags
                    if tags_list:
                        print(format_field("User Tags", ", ".join(tags_list)))
                except (json.JSONDecodeError, TypeError):
                    pass
            if reasoning:
                print(format_field("Reasoning", ""))
                # Word wrap reasoning
                words = reasoning.split()
                line = "  "
                for word in words:
                    if len(line) + len(word) + 1 > 78:
                        print(line)
                        line = "  " + word
                    else:
                        line += " " + word
                if line.strip():
                    print(line)
            print()
        
        # Extracted data
        if vendor or amount or due_date:
            print("💰 EXTRACTED DATA")
            print("-" * 80)
            if vendor:
                print(format_field("Vendor", vendor))
            if amount:
                print(format_field("Amount", f"${amount:.2f}"))
            if due_date:
                print(format_field("Due Date", due_date))
            print()
        
        # Structured data (bill summarization, etc.)
        if structured_data:
            import json
            print("📊 STRUCTURED DATA")
            print("-" * 80)
            try:
                if isinstance(structured_data, str):
                    data = json.loads(structured_data)
                else:
                    data = structured_data
                
                # Pretty print JSON with indentation
                formatted_json = json.dumps(data, indent=2)
                for line in formatted_json.split('\n'):
                    print(f"  {line}")
            except (json.JSONDecodeError, TypeError) as e:
                print(f"  Error parsing structured data: {e}")
            print()
        
        # Error
        if error:
            print("⚠️  ERROR")
            print("-" * 80)
            print(f"  {error}")
            print()
        
        # File paths
        print("📂 FILE LOCATIONS")
        print("-" * 80)
        if folder:
            print(format_field("Folder", folder))
        if text_path:
            print(format_field("Text Path", text_path))
        print()
        
        # Extracted text
        if text:
            print("📝 EXTRACTED TEXT")
            print("-" * 80)
            # Show first 500 chars
            preview = text[:500]
            if len(text) > 500:
                preview += "..."
            print(preview)
            print()
            print(format_field("Total Length", f"{len(text)} characters"))
            print()
        
        print("=" * 80)
        
    finally:
        await db.close()


async def list_documents(settings: Settings, limit: int = 10):
    """List recent documents."""
    db = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=1,
        pool_max_size=3,
        pool_timeout=30.0
    )
    await db.initialize()
    
    try:
        docs = await db.list_documents(limit=limit)
        
        if not docs:
            print("📭 No documents found in database")
            return
        
        print("\n" + "=" * 80)
        print(f"📚 RECENT DOCUMENTS (showing {len(docs)})")
        print("=" * 80)
        print()
        
        # Header
        print(f"{'ID':<38} {'Filename':<30} {'Status':<15} {'Type':<10} {'Created':<20}")
        print("-" * 115)
        
        for doc in docs:
            doc_id = doc['id']
            filename = doc['filename'][:28] + "..." if len(doc['filename']) > 28 else doc['filename']
            status = doc['status']
            doc_type = doc.get('document_type') or "-"
            created = str(doc['created_at'])[:19]
            
            print(f"{doc_id:<38} {filename:<30} {status:<15} {doc_type:<10} {created:<20}")
        
        print()
        print("💡 Use: python scripts/view-document.py <document_id> to view details")
        print()
        
    finally:
        await db.close()


async def show_stats(settings: Settings):
    """Show document statistics."""
    db = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=1,
        pool_max_size=3,
        pool_timeout=30.0
    )
    await db.initialize()
    
    try:
        stats = await db.get_stats()
        
        print("\n" + "=" * 80)
        print("📊 DOCUMENT STATISTICS")
        print("=" * 80)
        print()
        
        # Status counts
        if stats.get('by_status'):
            print("Documents by Status:")
            print("-" * 40)
            # Sort by count DESC
            sorted_status = sorted(stats['by_status'].items(), key=lambda x: x[1], reverse=True)
            for status, count in sorted_status:
                print(f"  {status:<20} {count:>5} documents")
            print()
        
        # Type counts
        if stats.get('by_type'):
            print("Documents by Type:")
            print("-" * 40)
            # Sort by count DESC
            sorted_types = sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True)
            for doc_type, count in sorted_types:
                print(f"  {doc_type:<20} {count:>5} documents")
            print()
        
        print("=" * 80)
        print()
        
    finally:
        await db.close()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='View document information from database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # View specific document
  %(prog)s bceb501e-9c3a-481e-9b1e-9ed07497281d
  
  # View with partial ID
  %(prog)s bceb501e
  
  # List recent documents
  %(prog)s --list
  
  # List last 20 documents
  %(prog)s --recent 20
  
  # Show statistics
  %(prog)s --stats
        """
    )
    
    parser.add_argument(
        'document_id',
        nargs='?',
        help='Document ID (full or partial)'
    )
    
    parser.add_argument(
        '--list', '-l',
        action='store_true',
        help='List recent documents'
    )
    
    parser.add_argument(
        '--recent', '-r',
        type=int,
        metavar='N',
        help='Show N most recent documents'
    )
    
    parser.add_argument(
        '--stats', '-s',
        action='store_true',
        help='Show document statistics'
    )
    
    args = parser.parse_args()
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"✗ Error loading settings: {e}")
        print("  Make sure .env file exists and is configured")
        sys.exit(1)
    
    # Execute command (async)
    async def run_command():
        try:
            if args.stats:
                await show_stats(settings)
            elif args.list:
                await list_documents(settings)
            elif args.recent:
                await list_documents(settings, args.recent)
            elif args.document_id:
                await view_document(args.document_id, settings)
            else:
                # Default: list recent documents
                await list_documents(settings)
        except Exception as e:
            print(f"\n✗ Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    
    asyncio.run(run_command())


if __name__ == "__main__":
    main()