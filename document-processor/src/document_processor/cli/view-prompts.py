#!/usr/bin/env python3
"""View and analyze prompt evolution history."""

import sys
from pathlib import Path
import duckdb
import json
from datetime import datetime

# Add project root to path (go up to esec/)
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent  # cli/ -> document_processor/ -> src/ -> document-processor/ -> esec/
sys.path.insert(0, str(_project_root))

from shared.config import Settings


def format_prompt_text(text: str, max_length: int = 80) -> str:
    """Truncate prompt text for display."""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def view_prompts(prompt_type: str = None, show_inactive: bool = False):
    """
    Display prompts from database.
    
    Args:
        prompt_type: Filter by 'classifier' or 'summarizer'
        show_inactive: Include inactive (old) versions
    """
    settings = Settings()
    conn = duckdb.connect(str(settings.database_path))
    
    try:
        # Build query
        query = """
            SELECT 
                prompt_type,
                document_type,
                version,
                performance_score,
                is_active,
                created_at,
                updated_at,
                prompt_text,
                performance_metrics
            FROM prompts
        """
        
        conditions = []
        params = []
        
        if prompt_type:
            conditions.append("prompt_type = ?")
            params.append(prompt_type)
        
        if not show_inactive:
            conditions.append("is_active = true")
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY prompt_type, document_type NULLS FIRST, version DESC"
        
        results = conn.execute(query, params).fetchall()
        
        if not results:
            print("\n❌ No prompts found in database.")
            print("   Run `./scripts/init-db` to initialize default prompts.\n")
            return
        
        # Group by prompt type and document type
        current_group = None
        
        print("\n" + "=" * 100)
        print("📝 PROMPT EVOLUTION HISTORY")
        print("=" * 100)
        
        for row in results:
            p_type, doc_type, version, score, active, created, updated, text, metrics = row
            
            # Group header
            group_key = (p_type, doc_type)
            if group_key != current_group:
                current_group = group_key
                
                print("\n" + "-" * 100)
                if p_type == "classifier":
                    print(f"🏷️  CLASSIFIER PROMPT")
                else:
                    doc_type_display = doc_type or "generic"
                    print(f"📄 SUMMARIZER PROMPT: {doc_type_display.upper()}")
                print("-" * 100)
            
            # Version info
            status = "✅ ACTIVE" if active else "📦 ARCHIVED"
            score_display = f"{score:.2f}" if score else "N/A"
            
            print(f"\n  Version {version} {status}")
            print(f"  Score: {score_display}")
            print(f"  Created: {created}")
            print(f"  Updated: {updated}")
            
            # Show metrics if available
            if metrics:
                try:
                    metrics_obj = json.loads(metrics)
                    if metrics_obj:
                        print(f"  Metrics: {json.dumps(metrics_obj, indent=10)}")
                except:
                    pass
            
            # Show prompt text (truncated or full based on flag)
            print(f"\n  Prompt Text ({len(text.split())} words):")
            if len(text) > 200:
                print(f"  {text[:200]}...")
                print(f"  [truncated - {len(text)} chars total]")
            else:
                print(f"  {text}")
        
        print("\n" + "=" * 100)
        
        # Summary statistics
        active_count = sum(1 for r in results if r[4])
        total_count = len(results)
        
        print(f"\n📊 Summary:")
        print(f"   Active prompts: {active_count}")
        print(f"   Total versions: {total_count}")
        print(f"   Show archived: {show_inactive}")
        
        print("\n💡 Tips:")
        print("   - Use --all to see archived versions")
        print("   - Use --type classifier or --type summarizer to filter")
        print("   - Prompts evolve when performance improves by 0.05 or drops below 0.7")
        print()
        
    finally:
        conn.close()


def main():
    """Parse arguments and display prompts."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="View prompt evolution history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./scripts/view-prompts                    # Show active prompts only
  ./scripts/view-prompts --all              # Show all versions including archived
  ./scripts/view-prompts --type classifier  # Show only classifier prompts
  ./scripts/view-prompts --type summarizer  # Show only summarizer prompts
        """
    )
    
    parser.add_argument(
        "--type",
        choices=["classifier", "summarizer"],
        help="Filter by prompt type"
    )
    
    parser.add_argument(
        "--all",
        action="store_true",
        help="Show all versions including archived"
    )
    
    args = parser.parse_args()
    
    try:
        view_prompts(
            prompt_type=args.type,
            show_inactive=args.all
        )
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()