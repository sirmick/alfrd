#!/usr/bin/env python3
"""Initialize DuckDB database with schema."""

import sys
from pathlib import Path

# Add parent directory to path to import shared module
sys.path.insert(0, str(Path(__file__).parent.parent))

import duckdb
from shared.config import Settings


def init_database():
    """Initialize the database with the schema."""
    settings = Settings()
    db_path = settings.database_path
    
    # Ensure parent directory exists
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Initializing database at {db_path}")
    
    # Create database connection
    conn = duckdb.connect(str(db_path))
    
    # Read schema file
    schema_path = Path(__file__).parent.parent / "api-server" / "src" / "api_server" / "db" / "schema.sql"
    
    if not schema_path.exists():
        print(f"ERROR: Schema file not found at {schema_path}")
        return 1
    
    with open(schema_path) as f:
        schema_sql = f.read()
    
    # Execute schema
    try:
        # Split by semicolon and execute each statement
        statements = [s.strip() for s in schema_sql.split(';') if s.strip()]
        for statement in statements:
            conn.execute(statement)
        
        conn.close()
        print(f"✓ Database initialized successfully at {db_path}")
        print(f"  Tables created: documents, summaries, processing_events, analytics")
        return 0
        
    except Exception as e:
        print(f"ERROR: Failed to initialize database: {e}")
        conn.close()
        return 1


if __name__ == "__main__":
    sys.exit(init_database())