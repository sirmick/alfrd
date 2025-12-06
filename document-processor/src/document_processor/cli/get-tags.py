#!/usr/bin/env python3
"""
Get tags from the database (without API server).

Usage:
    python scripts/get-tags
    python scripts/get-tags --popular 20
    python scripts/get-tags --search "util"
    python scripts/get-tags --all
"""

import argparse
import sys
from pathlib import Path
import asyncio

# Add project root to path
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent
sys.path.insert(0, str(_project_root))

from shared.config import Settings
from shared.database import AlfrdDatabase


async def list_all_tags(db: AlfrdDatabase, limit: int = 100, order_by: str = "usage_count DESC"):
    """List all tags with statistics."""
    tags = await db.get_all_tags(limit=limit, order_by=order_by)
    
    if not tags:
        print("📭 No tags found in database")
        return
    
    print("\n" + "=" * 100)
    print(f"🏷️  ALL TAGS (showing {len(tags)})")
    print("=" * 100)
    print()
    
    # Header
    print(f"{'Tag':<30} {'Usage':<10} {'Created By':<15} {'Last Used':<20}")
    print("-" * 100)
    
    for tag in tags:
        tag_name = tag['tag_name'][:29]
        usage = tag['usage_count']
        created_by = tag.get('created_by', '-')[:14]
        last_used = str(tag.get('last_used', '-'))[:19]
        
        print(f"{tag_name:<30} {usage:<10} {created_by:<15} {last_used:<20}")
    
    print()


async def get_popular_tags(db: AlfrdDatabase, limit: int = 20):
    """Get most popular tags."""
    tags = await db.get_popular_tags(limit=limit)
    
    if not tags:
        print("📭 No tags found")
        return
    
    print("\n" + "=" * 80)
    print(f"🔥 POPULAR TAGS (top {len(tags)})")
    print("=" * 80)
    print()
    
    for i, tag in enumerate(tags, 1):
        print(f"  {i:2d}. {tag}")
    
    print()


async def search_tags(db: AlfrdDatabase, query: str, limit: int = 20):
    """Search for tags matching query."""
    tags = await db.search_tags(query=query, limit=limit)
    
    if not tags:
        print(f"🔍 No tags found matching: {query}")
        return
    
    print("\n" + "=" * 80)
    print(f"🔍 TAG SEARCH RESULTS for '{query}' (showing {len(tags)})")
    print("=" * 80)
    print()
    
    for i, tag in enumerate(tags, 1):
        print(f"  {i:2d}. {tag}")
    
    print()


async def main():
    parser = argparse.ArgumentParser(
        description='Get tags from database (no API server needed)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List popular tags
  %(prog)s
  
  # List top 50 tags
  %(prog)s --popular 50
  
  # Search for tags
  %(prog)s --search "util"
  
  # List all tags with details
  %(prog)s --all --limit 200
        """
    )
    
    parser.add_argument('--popular', '-p', type=int, metavar='N', help='Show N most popular tags')
    parser.add_argument('--search', '-s', metavar='QUERY', help='Search for tags')
    parser.add_argument('--all', '-a', action='store_true', help='List all tags with details')
    parser.add_argument('--limit', type=int, default=100, help='Maximum results (default: 100)')
    parser.add_argument('--order-by', choices=['usage', 'name', 'date'], default='usage',
                       help='Sort order (default: usage)')
    
    args = parser.parse_args()
    
    # Map order-by to SQL
    order_map = {
        'usage': 'usage_count DESC',
        'name': 'tag_name ASC',
        'date': 'last_used DESC'
    }
    order_by = order_map[args.order_by]
    
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
        if args.search:
            await search_tags(db, args.search, args.limit)
        elif args.all:
            await list_all_tags(db, args.limit, order_by)
        elif args.popular is not None:
            await get_popular_tags(db, args.popular)
        else:
            # Default: show popular tags
            await get_popular_tags(db, 20)
    
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())