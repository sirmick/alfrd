#!/usr/bin/env python3
"""
Get series information from the database (without API server).

Usage:
    python scripts/get-series
    python scripts/get-series <series_id>
    python scripts/get-series --entity "PG&E"
    python scripts/get-series --type monthly_bill
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


async def get_series_by_id(db: AlfrdDatabase, series_id: str):
    """Get and display a single series."""
    try:
        series_uuid = UUID(series_id)
    except ValueError:
        # Try partial ID match
        all_series = await db.list_series(limit=1000)
        matches = [s for s in all_series if str(s['id']).startswith(series_id)]
        if not matches:
            print(f"❌ No series found matching: {series_id}")
            return
        series_uuid = matches[0]['id']
    
    series = await db.get_series(series_uuid)
    if not series:
        print(f"❌ Series not found: {series_id}")
        return
    
    # Get documents in series
    documents = await db.get_series_documents(series_uuid)
    
    print("\n" + "=" * 80)
    print(f"📊 SERIES: {series.get('title')}")
    print("=" * 80)
    print()
    
    print("📋 BASIC INFORMATION")
    print("-" * 80)
    print(f"  ID: {series['id']}")
    print(f"  Entity: {series['entity']}")
    print(f"  Type: {series['series_type']}")
    print(f"  Frequency: {series.get('frequency') or '(not set)'}")
    print(f"  Status: {series['status']}")
    print(f"  Documents: {series['document_count']}")
    print(f"  Created: {format_datetime(series.get('created_at'))}")
    print(f"  Updated: {format_datetime(series.get('updated_at'))}")
    print()
    
    if series.get('description'):
        print("📝 DESCRIPTION")
        print("-" * 80)
        print(f"  {series['description']}")
        print()
    
    if series.get('metadata'):
        print("📊 METADATA")
        print("-" * 80)
        data = series['metadata']
        if isinstance(data, str):
            data = json.loads(data)
        print(json.dumps(data, indent=2))
        print()
    
    if documents:
        print(f"📄 DOCUMENTS ({len(documents)})")
        print("-" * 80)
        for doc in documents[:10]:  # Show first 10
            filename = doc.get('filename', 'Unknown')[:40]
            created = format_datetime(doc.get('created_at'))
            print(f"  • {filename:<40} {created}")
        if len(documents) > 10:
            print(f"  ... and {len(documents) - 10} more")
        print()
    
    print("=" * 80)


async def list_series(db: AlfrdDatabase, limit: int = 50, entity: str = None, series_type: str = None, frequency: str = None):
    """List series with optional filtering."""
    series_list = await db.list_series(
        limit=limit,
        entity=entity,
        series_type=series_type,
        frequency=frequency
    )
    
    if not series_list:
        print("📭 No series found")
        return
    
    print("\n" + "=" * 120)
    print(f"📊 SERIES (showing {len(series_list)})")
    print("=" * 120)
    print()
    
    # Header
    print(f"{'ID':<38} {'Entity':<25} {'Type':<20} {'Freq':<10} {'Docs':<6} {'Updated':<20}")
    print("-" * 120)
    
    for series in series_list:
        series_id = str(series['id'])
        entity_str = (series.get('entity') or '-')[:24]
        type_str = (series.get('series_type') or '-')[:19]
        freq = (series.get('frequency') or '-')[:9]
        doc_count = series['document_count']
        updated = format_datetime(series.get('updated_at'))
        
        print(f"{series_id:<38} {entity_str:<25} {type_str:<20} {freq:<10} {doc_count:<6} {updated:<20}")
    
    print()
    print(f"💡 Use: python scripts/get-series <series_id> to view details")
    print()


async def main():
    parser = argparse.ArgumentParser(
        description='Get series information from database (no API server needed)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List all series
  %(prog)s
  
  # Get specific series
  %(prog)s <series_id>
  
  # Filter by entity
  %(prog)s --entity "PG&E"
  
  # Filter by type
  %(prog)s --type monthly_utility_bill
  
  # Filter by frequency
  %(prog)s --frequency monthly
        """
    )
    
    parser.add_argument('series_id', nargs='?', help='Series ID (full or partial)')
    parser.add_argument('--entity', '-e', help='Filter by entity name')
    parser.add_argument('--type', '-t', dest='series_type', help='Filter by series type')
    parser.add_argument('--frequency', '-f', help='Filter by frequency')
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
        if args.series_id:
            await get_series_by_id(db, args.series_id)
        else:
            await list_series(db, args.limit, args.entity, args.series_type, args.frequency)
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())