#!/usr/bin/env python3
"""View events for documents, files, or series."""

import sys
from pathlib import Path
import json
from datetime import datetime
import asyncio

# Add project root to path (go up to esec/)
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent  # cli/ -> document_processor/ -> src/ -> document-processor/ -> esec/
sys.path.insert(0, str(_project_root))

from shared.config import Settings
from shared.database import AlfrdDatabase


def format_timestamp(ts) -> str:
    """Format timestamp for display."""
    if ts is None:
        return "N/A"
    if isinstance(ts, str):
        return ts
    return ts.strftime("%Y-%m-%d %H:%M:%S")


def truncate_text(text: str, max_length: int = 100) -> str:
    """Truncate text for display."""
    if text is None:
        return ""
    if len(text) <= max_length:
        return text
    return text[:max_length] + "..."


def format_event_category_icon(category: str) -> str:
    """Get icon for event category."""
    icons = {
        'state_transition': '🔄',
        'llm_request': '🤖',
        'processing': '⚙️',
        'error': '❌',
        'user_action': '👤'
    }
    return icons.get(category, '📝')


async def view_events(
    entity_id: str = None,
    document_id: str = None,
    file_id: str = None,
    series_id: str = None,
    event_category: str = None,
    event_type: str = None,
    limit: int = 50,
    show_full: bool = False,
    show_json: bool = False
):
    """
    Display events from database.

    Args:
        entity_id: Any entity UUID (auto-detects document/file/series)
        document_id: Filter by document UUID
        file_id: Filter by file UUID
        series_id: Filter by series UUID
        event_category: Filter by category
        event_type: Filter by event type
        limit: Maximum events to show
        show_full: Show full prompt/response text
        show_json: Output as JSON
    """
    settings = Settings()
    db = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=1,
        pool_max_size=3,
        pool_timeout=30.0
    )
    await db.initialize()

    try:
        # Parse UUIDs if provided
        from uuid import UUID
        doc_uuid = None
        file_uuid = None
        series_uuid = None
        detected_type = None

        # Handle generic entity_id - auto-detect type
        if entity_id:
            entity_uuid = UUID(entity_id)

            # Check which table contains this UUID
            doc = await db.get_document(entity_uuid)
            if doc:
                doc_uuid = entity_uuid
                detected_type = "document"
            else:
                file_record = await db.get_file(entity_uuid)
                if file_record:
                    file_uuid = entity_uuid
                    detected_type = "file"
                else:
                    series_record = await db.get_series(entity_uuid)
                    if series_record:
                        series_uuid = entity_uuid
                        detected_type = "series"
                    else:
                        print(f"\n❌ No document, file, or series found with ID: {entity_id}\n")
                        return

            if not show_json:
                print(f"\n✅ Auto-detected entity type: {detected_type}")

        # Handle explicit parameters (override auto-detected)
        if document_id:
            doc_uuid = UUID(document_id)
        if file_id:
            file_uuid = UUID(file_id)
        if series_id:
            series_uuid = UUID(series_id)

        # Get events
        events = await db.get_events(
            document_id=doc_uuid,
            file_id=file_uuid,
            series_id=series_uuid,
            event_category=event_category,
            event_type=event_type,
            limit=limit
        )

        if show_json:
            # Output as JSON
            output = []
            for event in events:
                evt = dict(event)
                # Convert UUIDs to strings
                for key in ['id', 'document_id', 'file_id', 'series_id']:
                    if evt.get(key):
                        evt[key] = str(evt[key])
                # Convert datetime
                if evt.get('created_at'):
                    evt['created_at'] = evt['created_at'].isoformat()
                output.append(evt)
            print(json.dumps(output, indent=2))
            return

        if not events:
            print("\n❌ No events found.")
            if document_id:
                print(f"   Document ID: {document_id}")
            if file_id:
                print(f"   File ID: {file_id}")
            if series_id:
                print(f"   Series ID: {series_id}")
            print("\n💡 Events are logged during document processing.")
            print("   Process a document to see events here.\n")
            return

        # Determine entity type for header
        entity_type = "All"
        entity_id = None
        if document_id:
            entity_type = "Document"
            entity_id = document_id
        elif file_id:
            entity_type = "File"
            entity_id = file_id
        elif series_id:
            entity_type = "Series"
            entity_id = series_id

        print("\n" + "=" * 120)
        print(f"📋 EVENT LOG - {entity_type.upper()}" + (f": {entity_id}" if entity_id else ""))
        print("=" * 120)

        # Summary by category
        category_counts = {}
        for event in events:
            cat = event['event_category']
            category_counts[cat] = category_counts.get(cat, 0) + 1

        print(f"\n📊 Summary ({len(events)} events):")
        for cat, count in sorted(category_counts.items()):
            icon = format_event_category_icon(cat)
            print(f"   {icon} {cat}: {count}")

        print("\n" + "-" * 120)

        # Display events in chronological order (oldest first for timeline view)
        events_chronological = list(reversed(events))

        for i, event in enumerate(events_chronological, 1):
            icon = format_event_category_icon(event['event_category'])
            timestamp = format_timestamp(event['created_at'])

            print(f"\n{icon} [{i}] {event['event_type'].upper()}")
            print(f"   Time: {timestamp}")
            print(f"   Category: {event['event_category']}")

            if event.get('task_name'):
                print(f"   Task: {event['task_name']}")

            # State transition details
            if event['event_category'] == 'state_transition':
                old_status = event.get('old_status', 'N/A')
                new_status = event.get('new_status', 'N/A')
                print(f"   Transition: {old_status} → {new_status}")

            # LLM request details
            if event['event_category'] == 'llm_request':
                if event.get('llm_model'):
                    print(f"   Model: {event['llm_model']}")
                if event.get('llm_latency_ms'):
                    print(f"   Latency: {event['llm_latency_ms']}ms")
                if event.get('llm_request_tokens') or event.get('llm_response_tokens'):
                    req_tokens = event.get('llm_request_tokens', 'N/A')
                    resp_tokens = event.get('llm_response_tokens', 'N/A')
                    print(f"   Tokens: {req_tokens} in / {resp_tokens} out")
                if event.get('llm_cost_usd'):
                    print(f"   Cost: ${event['llm_cost_usd']:.6f}")

                if show_full:
                    if event.get('llm_prompt_text'):
                        print(f"\n   Prompt:\n   {'=' * 50}")
                        for line in event['llm_prompt_text'].split('\n')[:30]:
                            print(f"   {line}")
                        if len(event['llm_prompt_text'].split('\n')) > 30:
                            print(f"   ... [{len(event['llm_prompt_text'])} chars total]")

                    if event.get('llm_response_text'):
                        print(f"\n   Response:\n   {'=' * 50}")
                        resp = event['llm_response_text']
                        for line in resp.split('\n')[:20]:
                            print(f"   {line}")
                        if len(resp.split('\n')) > 20:
                            print(f"   ... [{len(resp)} chars total]")
                else:
                    if event.get('llm_prompt_text'):
                        print(f"   Prompt: {truncate_text(event['llm_prompt_text'], 80)}")
                    if event.get('llm_response_text'):
                        print(f"   Response: {truncate_text(event['llm_response_text'], 80)}")

            # Error details
            if event['event_category'] == 'error':
                if event.get('error_message'):
                    print(f"   Error: {event['error_message']}")

            # Details JSONB
            if event.get('details'):
                details = event['details']
                if isinstance(details, str):
                    try:
                        details = json.loads(details)
                    except:
                        pass
                if details:
                    if show_full:
                        print(f"   Details: {json.dumps(details, indent=13)}")
                    else:
                        # Show compact details
                        compact = json.dumps(details)
                        if len(compact) > 100:
                            compact = compact[:100] + "..."
                        print(f"   Details: {compact}")

            # Entity references
            refs = []
            if event.get('document_id') and not document_id:
                refs.append(f"doc:{event['document_id']}")
            if event.get('file_id') and not file_id:
                refs.append(f"file:{event['file_id']}")
            if event.get('series_id') and not series_id:
                refs.append(f"series:{event['series_id']}")
            if refs:
                print(f"   Refs: {', '.join(str(r) for r in refs)}")

        print("\n" + "=" * 120)

        print(f"\n📈 Showing {len(events)} events (limit: {limit})")
        print("\n💡 Tips:")
        print("   - Use --document <uuid> to filter by document")
        print("   - Use --file <uuid> to filter by file")
        print("   - Use --series <uuid> to filter by series")
        print("   - Use --category llm_request to see LLM calls only")
        print("   - Use --full to see complete prompt/response text")
        print("   - Use --json for machine-readable output")
        print("   - Use --limit <n> to see more events")
        print()

    finally:
        await db.close()


def main():
    """Parse arguments and display events."""
    import argparse

    parser = argparse.ArgumentParser(
        description="View events for documents, files, or series",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  ./scripts/view-events <uuid>                        # Events for any entity (auto-detects type)
  ./scripts/view-events --id <uuid>                   # Same as above (explicit flag)
  ./scripts/view-events --document <uuid>             # Events for a specific document
  ./scripts/view-events --file <uuid>                 # Events for a specific file
  ./scripts/view-events --series <uuid>               # Events for a specific series
  ./scripts/view-events <uuid> --category llm_request # Only LLM request events
  ./scripts/view-events <uuid> --category error       # Only error events
  ./scripts/view-events <uuid> --full                 # Show full prompt/response text
  ./scripts/view-events <uuid> --json                 # JSON output
        """
    )

    parser.add_argument(
        "entity_id",
        nargs="?",
        metavar="UUID",
        help="Entity UUID (auto-detects document/file/series)"
    )

    parser.add_argument(
        "--id", "-i",
        metavar="UUID",
        help="Entity UUID (auto-detects type) - alternative to positional arg"
    )

    parser.add_argument(
        "--document", "-d",
        metavar="UUID",
        help="Filter by document UUID (explicit)"
    )

    parser.add_argument(
        "--file", "-f",
        metavar="UUID",
        help="Filter by file UUID (explicit)"
    )

    parser.add_argument(
        "--series", "-s",
        metavar="UUID",
        help="Filter by series UUID (explicit)"
    )

    parser.add_argument(
        "--category", "-c",
        choices=["state_transition", "llm_request", "processing", "error", "user_action"],
        help="Filter by event category"
    )

    parser.add_argument(
        "--type", "-t",
        metavar="TYPE",
        help="Filter by event type (e.g., llm_classify, status_change)"
    )

    parser.add_argument(
        "--limit", "-n",
        type=int,
        default=50,
        help="Maximum number of events to show (default: 50)"
    )

    parser.add_argument(
        "--full",
        action="store_true",
        help="Show full prompt/response text without truncation"
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    # Determine entity_id from positional arg or --id flag
    entity_id = args.entity_id or args.id

    # Require at least one filter for clarity
    if not any([entity_id, args.document, args.file, args.series, args.category, args.type]):
        print("\n⚠️  No filters specified. Showing most recent events across all entities.\n")

    try:
        asyncio.run(view_events(
            entity_id=entity_id,
            document_id=args.document,
            file_id=args.file,
            series_id=args.series,
            event_category=args.category,
            event_type=args.type,
            limit=args.limit,
            show_full=args.full,
            show_json=args.json
        ))
    except ValueError as e:
        print(f"\n❌ Invalid UUID format: {e}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Error: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
