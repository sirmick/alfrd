#!/usr/bin/env python3
"""Initialize PostgreSQL database with schema and generic prompts.

This script CLEARS ALL EXISTING DATA and creates a fresh database.
"""

import sys
import shutil
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import asyncio

# Add project root to path (go up to esec/)
_script_dir = Path(__file__).resolve()
_project_root = _script_dir.parent.parent.parent.parent.parent  # cli/ -> document_processor/ -> src/ -> document-processor/ -> esec/
sys.path.insert(0, str(_project_root))

import asyncpg
from shared.config import Settings
from shared.types import PromptType


async def init_database():
    """Initialize the database with the schema and default prompts.
    
    WARNING: This deletes all existing data in the filesystem!
    """
    settings = Settings()
    data_dir = Path("./data")
    
    print(f"⚠️  WARNING: This will DELETE all existing data in {data_dir}")
    print()
    
    # Clear everything in data directory (except postgres)
    if data_dir.exists():
        print(f"🗑️  Clearing data directory: {data_dir}")
        for item in data_dir.iterdir():
            if item.name == "postgres":
                continue  # Don't delete PostgreSQL data
            if item.is_dir():
                shutil.rmtree(item)
                print(f"   Deleted directory: {item.name}")
            else:
                item.unlink()
                print(f"   Deleted file: {item.name}")
    
    # Recreate data directory structure
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "inbox").mkdir(exist_ok=True)
    (data_dir / "documents").mkdir(exist_ok=True)
    print()
    
    print(f"Initializing fresh database at {settings.database_url}")
    
    # Connect to PostgreSQL
    try:
        conn = await asyncpg.connect(dsn=settings.database_url)
    except Exception as e:
        print(f"ERROR: Failed to connect to PostgreSQL: {e}")
        print(f"\nMake sure PostgreSQL is running and configured:")
        print(f"  1. Run: ./scripts/configure-postgres-unix-socket.sh")
        print(f"  2. Check DATABASE_URL in .env: {settings.database_url}")
        return 1
    
    # Read schema file
    schema_path = _project_root / "api-server" / "src" / "api_server" / "db" / "schema.sql"
    
    if not schema_path.exists():
        print(f"ERROR: Schema file not found at {schema_path}")
        await conn.close()
        return 1
    
    with open(schema_path) as f:
        schema_sql = f.read()
    
    # Execute schema
    try:
        # Drop all existing tables
        print("Dropping existing tables...")
        await conn.execute("""
            DROP TABLE IF EXISTS classification_suggestions CASCADE;
            DROP TABLE IF EXISTS processing_events CASCADE;
            DROP TABLE IF EXISTS prompts CASCADE;
            DROP TABLE IF EXISTS document_types CASCADE;
            DROP TABLE IF EXISTS analytics CASCADE;
            DROP TABLE IF EXISTS summaries CASCADE;
            DROP TABLE IF EXISTS documents CASCADE;
        """)
        
        # Execute schema (PostgreSQL can handle multi-statement execution)
        await conn.execute(schema_sql)
        
        print(f"✓ Database schema created successfully")
        print(f"  Tables: documents, summaries, processing_events, analytics, prompts, classification_suggestions, document_types")
        
        # Initialize default prompts
        print("\nInitializing default prompts...")
        await _init_default_prompts(conn)
        
        # Initialize default document types
        print("\nInitializing default document types...")
        await _init_default_document_types(conn)
        
        await conn.close()
        print(f"\n✓ Database initialized successfully")
        return 0
        
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}")
        import traceback
        traceback.print_exc()
        await conn.close()
        return 1


async def _init_default_prompts(conn):
    """Initialize default classifier and summarizer prompts."""
    now = datetime.utcnow()
    
    # Default classifier prompt (under 300 words)
    classifier_prompt = """You are a document classifier. Analyze the document and classify it into one of the known types.

Known document types will be provided. You may also suggest a NEW type if none of the existing types fit well.

For each document:
1. Choose the most appropriate type from the known types, OR suggest a new type
2. Provide a confidence score (0.0 to 1.0)
3. Give clear reasoning for your classification
4. Optionally add secondary tags (e.g., "tax", "university", "utility", "insurance")

Guidelines:
- Be specific and accurate
- Use high confidence (>0.8) only when very certain
- Suggest new types sparingly - only when document clearly doesn't fit existing categories
- Secondary tags help with organization and search

Return JSON format:
{
    "document_type": "chosen_type_from_list",
    "confidence": 0.95,
    "reasoning": "why this classification is correct",
    "suggested_type": "new_type_name",  // OPTIONAL: only if suggesting new type
    "suggestion_reasoning": "why new type is needed",  // OPTIONAL
    "secondary_tags": ["tag1", "tag2"]  // OPTIONAL: additional classification tags
}"""
    
    classifier_id = uuid4()
    await conn.execute("""
        INSERT INTO prompts
        (id, prompt_type, document_type, prompt_text, version, is_active, created_at, updated_at)
        VALUES ($1, $2, NULL, $3, 1, true, $4, $5)
    """, classifier_id, PromptType.CLASSIFIER.value, classifier_prompt, now, now)
    print(f"  ✓ Classifier prompt (v1, {len(classifier_prompt.split())} words)")
    
    # Default summarizer prompts for each document type
    summarizer_prompts = {
        "bill": """Extract structured data from this bill document.

Focus on:
- Vendor/company name
- Total amount due
- Due date
- Issue/statement date
- Account number
- Service period
- Line items (if applicable)
- Payment instructions

Return JSON with all available fields.""",
        
        "finance": """Extract structured financial data from this document.

Focus on:
- Institution name
- Account number
- Statement period
- Beginning/ending balance
- Transactions (summary)
- Interest earned
- Fees charged
- Account type

Return JSON with all available fields.""",
        
        "school": """Extract structured data from this school document.

Focus on:
- School/institution name
- Student name
- Document type (report card, transcript, permission slip, etc.)
- Date/academic period
- Grades or key information
- Important deadlines
- Contact information

Return JSON with all available fields.""",
        
        "event": """Extract structured data from this event document.

Focus on:
- Event name
- Date and time
- Location/venue
- Organizer
- Cost/tickets
- Registration deadline
- Contact information
- Important notes

Return JSON with all available fields.""",
        
        "advertising": """Extract structured data from this advertising/promotional document.

Focus on:
- Company/brand name
- Promotional offers
- Products/services featured
- Validity/expiration dates
- Contact information
- Location/hours (if applicable)

Return JSON with all available fields.""",
        
        "junk": """This is spam or unwanted promotional content.

Extract only:
- Sender/company
- Type of content
- Any expiration dates

Return minimal JSON.""",
        
        "generic": """Extract key information from this document.

Identify and extract:
- Document type/purpose
- Main parties involved
- Important dates
- Key amounts or values
- Critical information

Return JSON with all relevant fields."""
    }
    
    for doc_type, prompt_text in summarizer_prompts.items():
        summarizer_id = uuid4()
        await conn.execute("""
            INSERT INTO prompts
            (id, prompt_type, document_type, prompt_text, version, is_active, created_at, updated_at)
            VALUES ($1, $2, $3, $4, 1, true, $5, $6)
        """, summarizer_id, PromptType.SUMMARIZER.value, doc_type, prompt_text, now, now)
        print(f"  ✓ Summarizer prompt for '{doc_type}' (v1)")


async def _init_default_document_types(conn):
    """Initialize default known document types."""
    now = datetime.utcnow()
    
    default_types = [
        ("bill", "Utility bills, service invoices, recurring charges"),
        ("finance", "Bank statements, investment documents, tax forms"),
        ("advertising", "Marketing materials with offers, promotions, and expiration dates"),
        ("junk", "Spam, unwanted promotional materials"),
        ("school", "Report cards, transcripts, school notices"),
        ("event", "Invitations, tickets, event information"),
    ]
    
    for type_name, description in default_types:
        type_id = uuid4()
        await conn.execute("""
            INSERT INTO document_types
            (id, type_name, description, is_active, usage_count, created_at)
            VALUES ($1, $2, $3, true, 0, $4)
        """, type_id, type_name, description, now)
        print(f"  ✓ Document type: {type_name}")


def main():
    """Run the async init_database function."""
    return asyncio.run(init_database())


if __name__ == "__main__":
    sys.exit(main())