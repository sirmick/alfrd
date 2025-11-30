# Document Processor Tests

## Status

The legacy DuckDB-based tests have been removed as part of the PostgreSQL migration.

## Current Tests

The database layer is tested via:
- `shared/tests/test_database.py` - Comprehensive PostgreSQL database tests (20 tests)

## Running Tests

```bash
# Run database tests
cd /home/mick/esec
pytest shared/tests/test_database.py -v

# Run all tests
pytest -v
```

## Test Database

Tests use a separate PostgreSQL test database (`alfrd_test`) that is created and destroyed automatically.

## Future Work

Integration tests for workers and end-to-end pipeline testing should be added using:
- pytest fixtures for test database setup
- Mock LLM responses for classifier/summarizer tests
- Sample documents in fixtures directory