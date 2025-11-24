#!/usr/bin/env python3
"""Initialize the DuckDB database with schema."""

import duckdb
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from shared.config import Settings


def init_database():
    """Initialize DuckDB database with schema."""
    settings = Settings()
    db_path = settings.database_path
    
    print(f"Initializing database at {db_path}...")
    
    # Create parent directory if it doesn't exist
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Connect to database (creates if doesn't exist)
    conn = duckdb.connect(str(db_path))
    
    # Read and execute schema
    schema_path = Path(__file__).parent.parent / "api-server" / "src" / "api_server" / "db" / "schema.sql"
    
    if not schema_path.exists():
        print(f"❌ Schema file not found: {schema_path}")
        sys.exit(1)
    
    print(f"Loading schema from {schema_path}...")
    
    with open(schema_path) as f:
        schema_sql = f.read()
    
    try:
        # Execute schema (DuckDB doesn't have executescript, so we split by statement)
        for statement in schema_sql.split(';'):
            statement = statement.strip()
            if statement:
                conn.execute(statement)
        
        print("✅ Database schema created successfully")
        
        # Verify tables were created
        tables = conn.execute("SHOW TABLES").fetchall()
        print(f"\n📊 Created tables:")
        for table in tables:
            print(f"  - {table[0]}")
        
        # Create data directories
        for directory in [settings.inbox_path, settings.documents_path, settings.summaries_path]:
            directory.mkdir(parents=True, exist_ok=True)
            print(f"✅ Created directory: {directory}")
        
    except Exception as e:
        print(f"❌ Error creating schema: {e}")
        sys.exit(1)
    finally:
        conn.close()
    
    print(f"\n🎉 Database initialization complete!")
    print(f"   Database: {db_path}")
    print(f"   Inbox: {settings.inbox_path}")
    print(f"   Documents: {settings.documents_path}")
    print(f"   Summaries: {settings.summaries_path}")


if __name__ == "__main__":
    init_database()