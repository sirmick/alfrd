# AI Document Secretary - Quick Start Guide

## Initial Setup

### 1. Prerequisites
- Python 3.11+ installed
- Virtual environment at `./venv` (already set up)

### 2. Activate Virtual Environment
```bash
source ./venv/bin/activate
```

### 3. Install Dependencies
```bash
# Install all dependencies
pip install -r requirements.txt

# Install subproject packages in editable mode
pip install -e ./document-processor
pip install -e ./api-server
pip install -e ./mcp-server
```

### 4. Configure Environment
```bash
# Copy the example environment file
cp .env.example .env

# Edit .env and add your API keys
nano .env  # or use your preferred editor
```

**Required settings in .env:**
```bash
CLAUDE_API_KEY=sk-ant-your-actual-key-here
```

**Optional (already set for local development):**
```bash
DATABASE_PATH=./data/esec.db
INBOX_PATH=./data/inbox
DOCUMENTS_PATH=./data/documents
SUMMARIES_PATH=./data/summaries
```

### 5. Initialize Database
```bash
# This creates the ./data directory and DuckDB database
python3 scripts/init-db.py
```

Expected output:
```
Initializing database at ./data/esec.db
✓ Database initialized successfully at ./data/esec.db
  Tables created: documents, summaries, processing_events, analytics
```

## Running the System

### Development Mode (No Docker) - Recommended for Fast Development

**Quick Start - All Servers in Screen Sessions:**
```bash
# Start all servers in separate screen sessions
./scripts/start-dev.sh

# Check status of all servers
./scripts/dev-status.sh

# Stop all servers
./scripts/stop-dev.sh
```

**Screen Session Commands:**
```bash
# View all running screen sessions
screen -list

# Attach to a specific server (to view logs/debug)
screen -r esec-api         # API Server
screen -r esec-mcp         # MCP Server
screen -r esec-processor   # Document Processor

# Detach from screen session (leave it running)
# Press: Ctrl+A then D

# Kill a specific screen session
screen -S esec-api -X quit
```

**Manual Start (if you prefer separate terminals):**

**Terminal 1 - API Server:**
```bash
cd api-server
PYTHONPATH=/home/mick/esec:$PYTHONPATH /home/mick/esec/venv/bin/python3 -m api_server.main
```

**Terminal 2 - MCP Server:**
```bash
cd mcp-server
PYTHONPATH=/home/mick/esec:$PYTHONPATH /home/mick/esec/venv/bin/python3 -m mcp_server.main
```

**Terminal 3 - Document Processor:**
```bash
cd document-processor
PYTHONPATH=/home/mick/esec:$PYTHONPATH /home/mick/esec/venv/bin/python3 -m document_processor.watcher
```

**Why PYTHONPATH?** We set PYTHONPATH to the project root so Python can import the `shared` module without needing pip install. This allows for fast turnaround when making code changes - just restart the screen session, no reinstall needed.

### Docker Mode (Single Container)

```bash
# Build and start all services
docker-compose -f docker/docker-compose.yml up --build

# Or run in background
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop services
docker-compose -f docker/docker-compose.yml down
```

## Testing the System

### 1. Check API Health
```bash
curl http://localhost:8000/api/v1/health
```

### 2. Process a Test Document
```bash
# Drop a document in the inbox
cp test-documents/sample-bill.pdf ./data/inbox/

# Watch the logs in the document processor terminal
# The document will be automatically processed
```

### 3. Query Documents via API
```bash
# List all documents
curl http://localhost:8000/api/v1/documents | jq

# Get specific document
curl http://localhost:8000/api/v1/documents/{document-id} | jq
```

## Project Structure

```
esec/
├── shared/              # Shared configuration and types
├── document-processor/  # Document ingestion and OCR
├── api-server/          # REST API and orchestration
├── mcp-server/          # AI/LLM integration
├── web-ui/              # Web interface (coming soon)
├── data/                # Runtime data (not in git)
│   ├── inbox/          # Drop documents here
│   ├── documents/      # Processed documents
│   ├── summaries/      # Generated summaries
│   └── esec.db         # DuckDB database
└── scripts/             # Utility scripts
```

## Common Issues

### Database initialization fails
```bash
# Make sure you're using python3
python3 scripts/init-db.py

# Check that ./data directory is writable
mkdir -p ./data
chmod 755 ./data
```

### Import errors
```bash
# Make sure packages are installed in editable mode
pip install -e ./document-processor
pip install -e ./api-server
pip install -e ./mcp-server
```

### API key not found
```bash
# Make sure .env file exists and contains your API key
cat .env | grep CLAUDE_API_KEY
```

## Next Steps

1. ✅ Database initialized
2. ⏳ Complete document processor implementation (storage, events, main loop)
3. ⏳ Complete API server implementation
4. ⏳ Build web UI
5. ⏳ Add MCP server AI features

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for detailed system design.
See [`IMPLEMENTATION_PLAN.md`](IMPLEMENTATION_PLAN.md) for commit-by-commit build guide.

## Development Commands

```bash
# Run database initialization
python3 scripts/init-db.py

# Run tests (when implemented)
pytest

# Format code
black .

# Lint code
ruff check .