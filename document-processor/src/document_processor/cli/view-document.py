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

# Add project root to path (go up to esec/)
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent  # cli/ -> document_processor/ -> src/ -> document-processor/ -> esec/
sys.path.insert(0, str(_project_root))

from shared.config import Settings
import duckdb


def format_field(label: str, value, width: int = 20):
    """Format a field for display."""
    if value is None:
        return f"{label:>{width}}: (none)"
    return f"{label:>{width}}: {value}"


def view_document(doc_id: str, settings: Settings):
    """View detailed information about a document."""
    conn = duckdb.connect(str(settings.database_path))
    
    try:
        # Get document info
        result = conn.execute("""
            SELECT
                id, filename, status, document_type,
                classification_confidence, classification_reasoning,
                suggested_type, secondary_tags,
                vendor, amount, due_date,
                created_at, updated_at, processed_at,
                extracted_text, extracted_text_path,
                folder_path, error_message, structured_data,
                tags, folder_metadata
            FROM documents
            WHERE id = ? OR id LIKE ?
        """, [doc_id, f"{doc_id}%"]).fetchone()
        
        if not result:
            print(f"❌ Document not found: {doc_id}")
            return
        
        # Unpack results
        (id, filename, status, doc_type, confidence, reasoning,
         suggested_type, secondary_tags,
         vendor, amount, due_date, created, updated, processed,
         text, text_path, folder, error, structured_data,
         tags, folder_metadata) = result
        
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
        conn.close()


def list_documents(settings: Settings, limit: int = 10):
    """List recent documents."""
    conn = duckdb.connect(str(settings.database_path))
    
    try:
        results = conn.execute("""
            SELECT id, filename, status, document_type, created_at
            FROM documents
            ORDER BY created_at DESC
            LIMIT ?
        """, [limit]).fetchall()
        
        if not results:
            print("📭 No documents found in database")
            return
        
        print("\n" + "=" * 80)
        print(f"📚 RECENT DOCUMENTS (showing {len(results)})")
        print("=" * 80)
        print()
        
        # Header
        print(f"{'ID':<38} {'Filename':<30} {'Status':<15} {'Type':<10} {'Created':<20}")
        print("-" * 115)
        
        for row in results:
            doc_id = row[0]  # Show full UUID
            filename = row[1][:28] + "..." if len(row[1]) > 28 else row[1]
            status = row[2]
            doc_type = row[3] if row[3] else "-"
            created = str(row[4])[:19]
            
            print(f"{doc_id:<38} {filename:<30} {status:<15} {doc_type:<10} {created:<20}")
        
        print()
        print("💡 Use: python scripts/view-document.py <document_id> to view details")
        print()
        
    finally:
        conn.close()


def show_stats(settings: Settings):
    """Show document statistics."""
    conn = duckdb.connect(str(settings.database_path))
    
    try:
        # Status counts
        status_counts = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM documents
            GROUP BY status
            ORDER BY count DESC
        """).fetchall()
        
        # Type counts
        type_counts = conn.execute("""
            SELECT document_type, COUNT(*) as count
            FROM documents
            WHERE document_type IS NOT NULL
            GROUP BY document_type
            ORDER BY count DESC
        """).fetchall()
        
        print("\n" + "=" * 80)
        print("📊 DOCUMENT STATISTICS")
        print("=" * 80)
        print()
        
        if status_counts:
            print("Documents by Status:")
            print("-" * 40)
            for status, count in status_counts:
                print(f"  {status:<20} {count:>5} documents")
            print()
        
        if type_counts:
            print("Documents by Type:")
            print("-" * 40)
            for doc_type, count in type_counts:
                print(f"  {doc_type:<20} {count:>5} documents")
            print()
        
        print("=" * 80)
        print()
        
    finally:
        conn.close()


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
    
    # Check database exists
    if not settings.database_path.exists():
        print(f"✗ Database not found: {settings.database_path}")
        print("  Run: python3 scripts/init-db.py")
        sys.exit(1)
    
    # Execute command
    try:
        if args.stats:
            show_stats(settings)
        elif args.list:
            list_documents(settings)
        elif args.recent:
            list_documents(settings, args.recent)
        elif args.document_id:
            view_document(args.document_id, settings)
        else:
            # Default: list recent documents
            list_documents(settings)
    
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()