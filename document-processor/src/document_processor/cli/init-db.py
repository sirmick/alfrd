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
import yaml

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
    
    # Clear everything in data directory (except postgres and cache)
    if data_dir.exists():
        print(f"🗑️  Clearing data directory: {data_dir}")
        for item in data_dir.iterdir():
            if item.name in ("postgres", "cache"):
                continue  # Don't delete PostgreSQL data or cache
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
    (data_dir / "cache").mkdir(exist_ok=True)
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
        # Drop all existing tables in correct order (respecting foreign keys)
        print("Dropping existing tables...")
        await conn.execute("""
            DROP TABLE IF EXISTS file_tags CASCADE;
            DROP TABLE IF EXISTS file_documents CASCADE;
            DROP TABLE IF EXISTS document_series CASCADE;
            DROP TABLE IF EXISTS document_tags CASCADE;
            DROP TABLE IF EXISTS classification_suggestions CASCADE;
            DROP TABLE IF EXISTS processing_events CASCADE;
            DROP TABLE IF EXISTS prompts CASCADE;
            DROP TABLE IF EXISTS document_types CASCADE;
            DROP TABLE IF EXISTS analytics CASCADE;
            DROP TABLE IF EXISTS summaries CASCADE;
            DROP TABLE IF EXISTS series CASCADE;
            DROP TABLE IF EXISTS files CASCADE;
            DROP TABLE IF EXISTS tags CASCADE;
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
    """Initialize default classifier and summarizer prompts from YAML files."""
    now = datetime.utcnow()
    prompts_dir = _project_root / "prompts"
    
    # Load classifier prompt
    classifier_file = prompts_dir / "classifier.yaml"
    if not classifier_file.exists():
        print(f"  ⚠️  Classifier prompt file not found: {classifier_file}")
        print(f"      Skipping classifier prompt initialization")
    else:
        with open(classifier_file) as f:
            classifier_config = yaml.safe_load(f)
        
        classifier_id = uuid4()
        classifier_prompt = classifier_config['prompt_text'].strip()
        await conn.execute("""
            INSERT INTO prompts
            (id, prompt_type, document_type, prompt_text, version, is_active, created_at, updated_at)
            VALUES ($1, $2, NULL, $3, 1, true, $4, $5)
        """, classifier_id, PromptType.CLASSIFIER.value, classifier_prompt, now, now)
        print(f"  ✓ Classifier prompt (v{classifier_config['version']}, {len(classifier_prompt.split())} words)")
    
    # Load summarizer prompts
    summarizers_dir = prompts_dir / "summarizers"
    if not summarizers_dir.exists():
        print(f"  ⚠️  Summarizers directory not found: {summarizers_dir}")
        print(f"      Skipping summarizer prompts initialization")
    else:
        for yaml_file in sorted(summarizers_dir.glob("*.yaml")):
            with open(yaml_file) as f:
                config = yaml.safe_load(f)
            
            doc_type = config['document_type']
            prompt_text = config['prompt_text'].strip()
            
            summarizer_id = uuid4()
            await conn.execute("""
                INSERT INTO prompts
                (id, prompt_type, document_type, prompt_text, version, is_active, created_at, updated_at)
                VALUES ($1, $2, $3, $4, 1, true, $5, $6)
            """, summarizer_id, PromptType.SUMMARIZER.value, doc_type, prompt_text, now, now)
            print(f"  ✓ Summarizer prompt for '{doc_type}' (v{config['version']})")


async def _init_default_document_types(conn):
    """Initialize default known document types from YAML file."""
    now = datetime.utcnow()
    types_file = _project_root / "prompts" / "document_types.yaml"
    
    if not types_file.exists():
        print(f"  ⚠️  Document types file not found: {types_file}")
        print(f"      Skipping document types initialization")
        return
    
    with open(types_file) as f:
        config = yaml.safe_load(f)
    
    for doc_type in config['document_types']:
        type_id = uuid4()
        await conn.execute("""
            INSERT INTO document_types
            (id, type_name, description, is_active, usage_count, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
        """, type_id, doc_type['type_name'], doc_type['description'],
             doc_type['is_active'], doc_type['usage_count'], now)
        print(f"  ✓ Document type: {doc_type['type_name']}")


def main():
    """Run the async init_database function."""
    return asyncio.run(init_database())


if __name__ == "__main__":
    sys.exit(main())