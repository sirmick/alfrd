#!/usr/bin/env python3
"""
Get document information from the database (without API server).

Usage:
    python scripts/get-document <document_id>
    python scripts/get-document --list [--limit N]
    python scripts/get-document --search "query text"
    python scripts/get-document --status pending
    python scripts/get-document --type bill
    python scripts/get-document --stats
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


async def get_document_by_id(db: AlfrdDatabase, doc_id: str):
    """Get and display a single document."""
    try:
        doc_uuid = UUID(doc_id)
    except ValueError:
        # Try partial ID match
        docs = await db.list_documents(limit=1000)
        matches = [d for d in docs if str(d['id']).startswith(doc_id)]
        if not matches:
            print(f"❌ No document found matching: {doc_id}")
            return
        doc_uuid = matches[0]['id']
    
    doc = await db.get_document_full(doc_uuid)
    if not doc:
        print(f"❌ Document not found: {doc_id}")
        return
    
    # Get tags
    tags = await db.get_document_tags(doc_uuid)
    
    print("\n" + "=" * 80)
    print(f"📄 DOCUMENT: {doc.get('id')}")
    print("=" * 80)
    print()
    
    print("📋 BASIC INFORMATION")
    print("-" * 80)
    print(f"  ID: {doc['id']}")
    print(f"  Status: {doc['status']}")
    print(f"  Type: {doc.get('document_type') or '(not classified)'}")
    print(f"  Created: {format_datetime(doc.get('created_at'))}")
    print(f"  Updated: {format_datetime(doc.get('updated_at'))}")
    if tags:
        print(f"  Tags: {', '.join(tags)}")
    print()
    
    if doc.get('classification_confidence'):
        print("🏷️  CLASSIFICATION")
        print("-" * 80)
        print(f"  Confidence: {doc['classification_confidence']:.1%}")
        if doc.get('classification_reasoning'):
            print(f"  Reasoning: {doc['classification_reasoning'][:200]}...")
        print()
    
    if doc.get('summary'):
        print("📝 SUMMARY")
        print("-" * 80)
        print(f"  {doc['summary'][:500]}...")
        print()
    
    if doc.get('structured_data'):
        print("📊 STRUCTURED DATA")
        print("-" * 80)
        data = doc['structured_data']
        if isinstance(data, str):
            data = json.loads(data)
        print(json.dumps(data, indent=2))
        print()
    
    if doc.get('extracted_text'):
        text_len = len(doc['extracted_text'])
        print("📄 EXTRACTED TEXT")
        print("-" * 80)
        print(f"  Length: {text_len} characters")
        print(f"  Preview: {doc['extracted_text'][:200]}...")
        print()
    
    print("=" * 80)


async def list_documents(db: AlfrdDatabase, limit: int = 50, status: str = None, document_type: str = None):
    """List documents with optional filtering."""
    docs = await db.list_documents_api(
        limit=limit,
        status=status,
        document_type=document_type
    )
    
    if not docs:
        print("📭 No documents found")
        return
    
    print("\n" + "=" * 120)
    print(f"📚 DOCUMENTS (showing {len(docs)})")
    print("=" * 120)
    print()
    
    # Header
    print(f"{'ID':<38} {'Type':<15} {'Status':<15} {'Confidence':<12} {'Created':<20}")
    print("-" * 120)
    
    for doc in docs:
        doc_id = str(doc['id'])
        doc_type = (doc.get('document_type') or '-')[:14]
        status_str = doc['status'][:14]
        conf = f"{doc.get('classification_confidence', 0):.1%}" if doc.get('classification_confidence') else '-'
        created = format_datetime(doc.get('created_at'))
        
        print(f"{doc_id:<38} {doc_type:<15} {status_str:<15} {conf:<12} {created:<20}")
    
    print()
    print(f"💡 Use: python scripts/get-document <document_id> to view details")
    print()


async def search_documents(db: AlfrdDatabase, query: str, limit: int = 50):
    """Full-text search for documents."""
    results = await db.search_documents(query, limit=limit)
    
    if not results:
        print(f"🔍 No documents found matching: {query}")
        return
    
    print("\n" + "=" * 120)
    print(f"🔍 SEARCH RESULTS for '{query}' (showing {len(results)})")
    print("=" * 120)
    print()
    
    # Header
    print(f"{'ID':<38} {'Type':<15} {'Vendor':<20} {'Rank':<8} {'Created':<20}")
    print("-" * 120)
    
    for doc in results:
        doc_id = str(doc['id'])
        doc_type = (doc.get('document_type') or '-')[:14]
        vendor = (doc.get('vendor') or '-')[:19]
        rank = f"{doc.get('rank', 0):.3f}"
        created = format_datetime(doc.get('created_at'))
        
        print(f"{doc_id:<38} {doc_type:<15} {vendor:<20} {rank:<8} {created:<20}")
    
    print()


async def show_stats(db: AlfrdDatabase):
    """Show database statistics."""
    stats = await db.get_stats()
    
    print("\n" + "=" * 80)
    print("📊 DATABASE STATISTICS")
    print("=" * 80)
    print()
    
    print(f"Total Documents: {stats['total_documents']}")
    print()
    
    if stats.get('by_status'):
        print("Documents by Status:")
        print("-" * 40)
        for status, count in sorted(stats['by_status'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {status:<20} {count:>5}")
        print()
    
    if stats.get('by_type'):
        print("Documents by Type:")
        print("-" * 40)
        for doc_type, count in sorted(stats['by_type'].items(), key=lambda x: x[1], reverse=True):
            print(f"  {doc_type:<20} {count:>5}")
        print()
    
    if stats.get('total_files'):
        print(f"Total Files: {stats['total_files']}")
        if stats.get('files_by_status'):
            print("Files by Status:")
            print("-" * 40)
            for status, count in sorted(stats['files_by_status'].items(), key=lambda x: x[1], reverse=True):
                print(f"  {status:<20} {count:>5}")
        print()
    
    print("=" * 80)


async def main():
    parser = argparse.ArgumentParser(
        description='Get document information from database (no API server needed)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Get specific document
  %(prog)s bceb501e-9c3a-481e-9b1e-9ed07497281d
  
  # Get with partial ID
  %(prog)s bceb501e
  
  # List recent documents
  %(prog)s --list
  
  # List by status
  %(prog)s --list --status pending
  
  # List by type
  %(prog)s --list --type bill --limit 20
  
  # Search documents
  %(prog)s --search "PG&E electricity"
  
  # Show statistics
  %(prog)s --stats
        """
    )
    
    parser.add_argument('document_id', nargs='?', help='Document ID (full or partial)')
    parser.add_argument('--list', '-l', action='store_true', help='List documents')
    parser.add_argument('--search', '-s', metavar='QUERY', help='Search documents')
    parser.add_argument('--status', help='Filter by status')
    parser.add_argument('--type', dest='document_type', help='Filter by document type')
    parser.add_argument('--limit', type=int, default=50, help='Maximum results (default: 50)')
    parser.add_argument('--stats', action='store_true', help='Show statistics')
    
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
        if args.stats:
            await show_stats(db)
        elif args.search:
            await search_documents(db, args.search, args.limit)
        elif args.list:
            await list_documents(db, args.limit, args.status, args.document_type)
        elif args.document_id:
            await get_document_by_id(db, args.document_id)
        else:
            # Default: list recent
            await list_documents(db, args.limit)
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())