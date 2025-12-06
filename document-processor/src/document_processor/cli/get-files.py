#!/usr/bin/env python3
"""
Get file information from the database (without API server).

Usage:
    python scripts/get-files
    python scripts/get-files <file_id>
    python scripts/get-files --tags series:pge
    python scripts/get-files --status generated
"""

import argparse
import sys
from pathlib import Path
import asyncio
import json

# Add project root to path
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from shared.config import Settings
from shared.database import AlfrdDatabase
from uuid import UUID


def format_datetime(dt):
    """Format datetime for display."""
    if dt is None:
        return "(none)"
    return str(dt)[:19]


async def get_file_by_id(db: AlfrdDatabase, file_id: str):
    """Get and display a single file."""
    try:
        file_uuid = UUID(file_id)
    except ValueError:
        # Try partial ID match
        all_files = await db.list_files(limit=1000)
        matches = [f for f in all_files if str(f['id']).startswith(file_id)]
        if not matches:
            print(f"❌ No file found matching: {file_id}")
            return
        file_uuid = matches[0]['id']
    
    file_record = await db.get_file(file_uuid)
    if not file_record:
        print(f"❌ File not found: {file_id}")
        return
    
    # Get documents in file
    documents = await db.get_file_documents(file_uuid)
    
    print("\n" + "=" * 80)
    print(f"📁 FILE: {file_record.get('id')}")
    print("=" * 80)
    print()
    
    print("📋 BASIC INFORMATION")
    print("-" * 80)
    print(f"  ID: {file_record['id']}")
    print(f"  Tags: {', '.join(file_record.get('tags', []))}")
    print(f"  Status: {file_record['status']}")
    print(f"  Documents: {file_record['document_count']}")
    print(f"  Created: {format_datetime(file_record.get('created_at'))}")
    print(f"  Updated: {format_datetime(file_record.get('updated_at'))}")
    if file_record.get('last_generated_at'):
        print(f"  Last Generated: {format_datetime(file_record['last_generated_at'])}")
    print()
    
    if file_record.get('summary_text'):
        print("📝 SUMMARY")
        print("-" * 80)
        summary = file_record['summary_text']
        if len(summary) > 500:
            print(f"  {summary[:500]}...")
        else:
            print(f"  {summary}")
        print()
    
    if file_record.get('summary_metadata'):
        print("📊 METADATA")
        print("-" * 80)
        data = file_record['summary_metadata']
        if isinstance(data, str):
            data = json.loads(data)
        print(json.dumps(data, indent=2))
        print()
    
    if documents:
        print(f"📄 DOCUMENTS ({len(documents)})")
        print("-" * 80)
        for doc in documents[:15]:  # Show first 15
            filename = doc.get('filename', 'Unknown')[:40]
            doc_type = doc.get('document_type', '-')[:15]
            created = format_datetime(doc.get('created_at'))
            print(f"  • {filename:<40} {doc_type:<15} {created}")
        if len(documents) > 15:
            print(f"  ... and {len(documents) - 15} more")
        print()
    
    print("=" * 80)


async def list_files(db: AlfrdDatabase, limit: int = 50, tags: list = None, status: str = None):
    """List files with optional filtering."""
    files = await db.list_files(
        limit=limit,
        tags=tags,
        status=status
    )
    
    if not files:
        print("📭 No files found")
        return
    
    print("\n" + "=" * 120)
    print(f"📁 FILES (showing {len(files)})")
    print("=" * 120)
    print()
    
    # Header
    print(f"{'ID':<38} {'Tags':<30} {'Status':<12} {'Docs':<6} {'Updated':<20}")
    print("-" * 120)
    
    for file_record in files:
        file_id = str(file_record['id'])
        tags_str = (', '.join(file_record.get('tags', [])))[:29]
        status_str = file_record['status'][:11]
        doc_count = file_record.get('document_count', 0)
        updated = format_datetime(file_record.get('updated_at'))
        
        print(f"{file_id:<38} {tags_str:<30} {status_str:<12} {doc_count:<6} {updated:<20}")
    
    print()
    print(f"💡 Use: python scripts/get-files <file_id> to view details")
    print()


async def main():
    parser = argparse.ArgumentParser(
        description='Get file information from database (no API server needed)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all files
  %(prog)s
  
  # Get specific file
  %(prog)s <file_id>
  
  # Filter by tags
  %(prog)s --tags series:pge
  
  # Filter by status
  %(prog)s --status generated
  
  # Combine filters
  %(prog)s --tags series:pge utility --status generated --limit 20
        """
    )
    
    parser.add_argument('file_id', nargs='?', help='File ID (full or partial)')
    parser.add_argument('--tags', '-t', nargs='+', help='Filter by tags')
    parser.add_argument('--status', '-s', help='Filter by status')
    parser.add_argument('--limit', type=int, default=50, help='Maximum results (default: 50)')
    
    args = parser.parse_args()
    
    # Load settings
    try:
        settings = Settings()
    except Exception as e:
        print(f"✗ Error loading settings: {e}")
        sys.exit(1)
    
    # Initialize database
    db = AlfrdDatabase(settings.database_url)
    await db.initialize()
    
    try:
        if args.file_id:
            await get_file_by_id(db, args.file_id)
        else:
            await list_files(db, args.limit, args.tags, args.status)
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())