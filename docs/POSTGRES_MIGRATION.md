# ALFRD - PostgreSQL Migration Guide

**Date:** 2025-11-30
**Status:** In Progress
**Reason:** DuckDB lock conflicts with multi-process architecture (API server + workers)

---

## Why PostgreSQL?

### Problems with DuckDB
- ❌ Single-writer limitation (only one process can write at a time)
- ❌ Lock conflicts between API server and worker processes
- ❌ Not designed for high-concurrency OLTP workloads

### Benefits of PostgreSQL
- ✅ True multi-process concurrency (MVCC)
- ✅ Connection pooling for efficient resource management
- ✅ Production-grade reliability and ACID guarantees
- ✅ Full-text search with `tsvector` and GIN indexes
- ✅ Native JSONB support for structured data
- ✅ Multi-user ready for scaling
- ✅ Excellent tooling (pgAdmin, monitoring, backups)

---

## Migration Steps

### 1. Install PostgreSQL Locally

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib libpq-dev
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
```

**Verify Installation:**
```bash
psql --version
# Should show: psql (PostgreSQL) 15.x
```

**Create Database and User:**
```bash
# Switch to postgres user
sudo -u postgres psql

# In psql shell:
CREATE DATABASE alfrd;
CREATE USER alfrd_user WITH PASSWORD 'alfrd_dev_password';
GRANT ALL PRIVILEGES ON DATABASE alfrd TO alfrd_user;
\q
```

### 2. Update Docker Compose

Add PostgreSQL service to `docker/docker-compose.yml`:

```yaml
services:
  postgres:
    image: postgres:15-alpine
    container_name: alfrd-postgres
    environment:
      POSTGRES_DB: alfrd
      POSTGRES_USER: alfrd_user
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-alfrd_dev_password}
    ports:
      - "5432:5432"
    volumes:
      - ./data/postgres:/var/lib/postgresql/data
      - ./api-server/src/api_server/db/schema.sql:/docker-entrypoint-initdb.d/schema.sql
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U alfrd_user -d alfrd"]
      interval: 10s
      timeout: 5s
      retries: 5

  alfrd:
    depends_on:
      postgres:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://alfrd_user:${POSTGRES_PASSWORD:-alfrd_dev_password}@postgres:5432/alfrd
```

### 3. Schema Migration (DuckDB → PostgreSQL)

**Key Differences:**

| DuckDB | PostgreSQL |
|--------|------------|
| `UUID` type with `uuid()` | `UUID` type with `gen_random_uuid()` |
| `BIGINT` | `BIGINT` |
| `VARCHAR` | `VARCHAR` or `TEXT` |
| `JSON` | `JSONB` (binary, faster) |
| `TIMESTAMP` | `TIMESTAMP WITH TIME ZONE` |
| Full-text search N/A | `tsvector` + GIN index |

### 4. Connection Management

**Use `asyncpg` for async operations:**
```python
import asyncpg

# Create connection pool
pool = await asyncpg.create_pool(
    host='localhost',
    port=5432,
    user='alfrd_user',
    password='alfrd_dev_password',
    database='alfrd',
    min_size=5,
    max_size=20
)

# Use in workers/API
async with pool.acquire() as conn:
    await conn.execute("UPDATE documents SET status=$1 WHERE id=$2", status, doc_id)
```

### 5. Python Dependencies

Add to `requirements.txt`:
```
asyncpg==0.29.0          # Async PostgreSQL driver
psycopg2-binary==2.9.9   # Sync driver (for migrations/scripts)
sqlalchemy==2.0.23       # Optional: ORM support
```

---

## Migration Checklist

- [ ] Install PostgreSQL locally
- [ ] Update `docker/docker-compose.yml` with PostgreSQL service
- [ ] Port `schema.sql` from DuckDB to PostgreSQL syntax
- [ ] Update `shared/config.py` with PostgreSQL connection settings
- [ ] Update `storage.py` to use `asyncpg` with connection pooling
- [ ] Update worker classes to use new PostgreSQL storage layer
- [ ] Update API server to use PostgreSQL connections
- [ ] Update test fixtures for PostgreSQL
- [ ] Create data migration script (DuckDB → PostgreSQL)
- [ ] Update documentation (START_HERE.md, README.md, ARCHITECTURE.md)

---

## Testing Strategy

1. **Local Testing:**
   - Run PostgreSQL locally
   - Test workers with shared connection pool
   - Test API server concurrent requests
   - Verify no lock conflicts

2. **Docker Testing:**
   - `docker-compose up` with PostgreSQL service
   - Test multi-container setup
   - Verify health checks

3. **Load Testing:**
   - Multiple workers processing simultaneously
   - API server handling concurrent uploads
   - Verify connection pool efficiency

---

## Rollback Plan

If migration fails, revert to DuckDB with read-only API server:
- API server uses `read_only=True` connections
- Workers run in single process with shared connection
- Uploads go to inbox folder (no direct DB writes from API)

---

## Next Steps

1. Install PostgreSQL locally
2. Update docker-compose.yml
3. Port schema.sql
4. Update configuration and storage layer
