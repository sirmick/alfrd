# ALFRD - Automated Ledger & Filing Research Database

> Your personal AI-powered document management system that ingests, processes, and summarizes all your documents automatically.

## What is ALFRD?

**ALFRD** (Automated Ledger & Filing Research Database) is a personal document management system that uses AI to automatically process, categorize, and summarize your documents. Create a document folder with metadata and ALFRD will:

- **Extract text** using AWS Textract OCR or plain text ingestion
- **Classify via MCP** using LLM-powered document type detection
- **Extract structured data** (vendor, amount, due date, account numbers)
- **Type-specific summarization** per document category
- **Hierarchical summaries** (weekly → monthly → yearly rollups)
- **Financial tracking** with running totals, trends, CSV exports
- **Full-text search** across all documents in DuckDB
- **Natural language queries** via MCP: "What bills are due this week?"

### Use Cases

- 📱 **Mobile document capture**: Snap photos of bills and receipts on your phone
- 📧 **Email forwarding**: Forward bills/statements to your esec inbox (future)
- 🗂️ **Automatic organization**: Never manually file a document again
- 💰 **Spending tracking**: Automatic categorization and spending analysis
- 📊 **Tax preparation**: All tax-related documents organized and summarized
- ⏰ **Bill reminders**: Track due dates and payment status
- 🔍 **Quick search**: Find any document instantly by content or metadata

## Architecture Overview

```
┌──────────────────┐
│ Document Folder  │
│ /inbox/doc-A/    │
│  ├─ meta.json    │──────► Watched Folder Structure
│  ├─ image.jpg    │
│  └─ page2.jpg    │
└──────────────────┘
         │
         ▼
┌──────────────────────┐
│ Document Processor   │
│ 1. Parse meta.json   │
│ 2. AWS Textract OCR  │
│ 3. Store raw text    │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ API Server + MCP     │
│ 1. Classify document │
│ 2. Extract data      │
│ 3. Type summary      │
│ 4. Update rollups    │
└──────────┬───────────┘
           │
    ┌──────┴───────┐
    ▼              ▼
┌─────────┐   ┌──────────────┐
│ DuckDB  │   │ Hierarchical │
│ Storage │   │ Summaries    │
│         │   │ (W→M→Y)      │
└─────────┘   └──────────────┘
           │
    ┌──────┴────────┐
    ▼               ▼
┌─────────┐   ┌──────────┐
│ Web UI  │   │ CSV/Excel│
│ (React) │   │ Exports  │
└─────────┘   └──────────┘
```

## Key Features

### 🤖 AI-Powered Processing
- **AWS Textract OCR**: Production-quality text extraction from images and scanned documents
- **Plain text support**: Direct ingestion of text documents
- **MCP-based classification**: Automatic document type detection via LLM
- **Structured data extraction**: Parse vendor names, amounts, dates, account numbers
- **Hierarchical summarization**: Weekly → Monthly → Yearly rollups
- **Financial tracking**: Running totals, trend analysis, CSV exports

### 📦 Privacy & Isolation
- **Isolated containers**: Each user gets their own Docker container
- **Local-first**: Data stays in your control
- **No vendor lock-in**: Self-hosted, open-source core

### 🌐 Multi-Platform
- **Web UI**: Access from any browser
- **Mobile apps**: Native iOS/Android (via Capacitor)
- **Claude Desktop**: MCP server integration
- **CLI**: Programmatic access via command line
- **Offline support**: Work without internet, sync when online

### 🔍 Powerful Search & Analytics
- **Full-text search**: Find documents by content or metadata
- **Hierarchical summaries**: Weekly → Monthly → Yearly rollups
- **Spending analytics**: Track spending by category, vendor, time period
- **Bill tracking**: See upcoming bills and overdue payments

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Claude API key (or OpenRouter API key)

### Installation

```bash
# Clone the repository
git clone https://github.com/sirmick/alfrd.git
cd alfrd

# Set up environment variables
cp .env.example .env
# Edit .env and add your API keys

# Start the system
docker-compose up -d

# Check status
curl http://localhost:8000/api/v1/health
```

### First Document

```bash
# Create a document folder
mkdir -p data/inbox/my-bill

# Create metadata
cat > data/inbox/my-bill/meta.json << EOF
{
  "id": "$(uuidgen)",
  "created_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "documents": [
    {"file": "bill.jpg", "type": "image", "order": 1}
  ],
  "metadata": {
    "source": "manual",
    "tags": ["bill"]
  }
}
EOF

# Add your document
cp ~/Downloads/electric-bill.jpg data/inbox/my-bill/bill.jpg

# Wait for processing...

# Check results
curl http://localhost:8000/api/v1/documents | jq
```

### Using Claude Desktop

Add to your Claude Desktop MCP configuration:

```json
{
  "mcpServers": {
    "alfrd": {
      "command": "docker",
      "args": ["exec", "alfrd-dev", "python", "-m", "mcp_server.main"],
      "env": {}
    }
  }
}
```

Now ask Claude: "What documents do I have?" or "What bills are due this week?"

## Project Structure

```
alfrd/
├── document-processor/    # Watches inbox, OCR, text extraction
├── api-server/           # REST API + MCP orchestration
├── mcp-server/           # MCP tools for classification/summarization
├── web-ui/               # React web interface
├── docker/               # Docker configuration
├── shared/               # Shared utilities and types
└── data/                 # Runtime data (not in git)
    ├── inbox/           # Document folders with meta.json
    │   └── doc-A/
    │       ├── meta.json
    │       └── image.jpg
    ├── documents/       # Processed documents + extracted text
    ├── summaries/       # Hierarchical summaries (weekly/monthly/yearly)
    │   ├── weekly/
    │   ├── monthly/
    │   └── yearly/
    ├── exports/         # CSV/Excel financial exports
    └── alfrd.db          # DuckDB database
```

## API Examples

### List Documents

```bash
curl http://localhost:8000/api/v1/documents?category=bill&limit=10
```

### Search Documents

```bash
curl http://localhost:8000/api/v1/search?q=electric+utility
```

### Get Weekly Summary

```bash
curl "http://localhost:8000/api/v1/summaries?period_type=weekly&start_date=2024-01-01"
```

### Natural Language Query

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{"query": "How much did I spend on groceries this month?"}'
```

### Spending Analytics

```bash
curl "http://localhost:8000/api/v1/analytics/spending?groupBy=category&date_range=2024-01"
```

## Configuration

### Environment Variables

```bash
# Required
CLAUDE_API_KEY=sk-ant-...           # Claude API key
OPENROUTER_API_KEY=sk-or-...        # OpenRouter API key (optional)

# Paths
DATABASE_PATH=/data/alfrd.db
INBOX_PATH=/data/inbox
DOCUMENTS_PATH=/data/documents
SUMMARIES_PATH=/data/summaries

# API Configuration
API_HOST=0.0.0.0
API_PORT=8000
MCP_PORT=3000

# Logging
LOG_LEVEL=INFO                      # DEBUG, INFO, WARNING, ERROR

# Environment
ENV=development                     # development, production
```

## Development

### Local Development (without Docker)

```bash
# Set up Python environment
python -m venv .venv
source .venv/bin/activate
pip install poetry

# Install dependencies
poetry install

# Initialize database
python scripts/init-db.py

# Run services in separate terminals
cd api-server && python -m api_server.main
cd mcp-server && python -m mcp_server.main
cd document-processor && python -m document_processor.watcher
cd web-ui && npm run dev
```

### Running Tests

```bash
# Unit tests
pytest document-processor/tests/
pytest api-server/tests/
pytest mcp-server/tests/

# Integration tests
pytest tests/integration/

# E2E tests (Web UI)
cd web-ui && npm run test:e2e

# Load testing
locust -f tests/load/locustfile.py
```

## Deployment

### Single-User Deployment (Recommended for MVP)

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down
```

### Multi-User Production Deployment

See [`ARCHITECTURE.md`](ARCHITECTURE.md) for detailed multi-user deployment architecture with:
- Separate Web UI server
- Per-user isolated containers
- Container orchestration (Kubernetes/Docker Swarm)
- API gateway for routing
- User authentication and authorization

## Roadmap

### Phase 1: MVP (Current)
- ✅ Document processing pipeline
- ✅ AI categorization and extraction
- ✅ Basic web UI
- ✅ MCP server integration
- ✅ Full-text search
- ⏳ Weekly/monthly summaries

### Phase 2: Enhanced Features
- ⏳ Advanced analytics dashboard
- ⏳ Offline mobile app
- ⏳ Email forwarding integration
- ⏳ OCR quality improvements
- ⏳ Custom categorization rules
- ⏳ Bill payment reminders

### Phase 3: Multi-User & Production
- ⏳ User authentication
- ⏳ Multi-tenant architecture
- ⏳ Backup and restore
- ⏳ Admin dashboard
- ⏳ Usage analytics
- ⏳ API rate limiting

### Phase 4: Advanced Features
- ⏳ Document editing/annotation
- ⏳ Workflow automation
- ⏳ Third-party integrations (QuickBooks, Mint, etc.)
- ⏳ Machine learning for custom extraction
- ⏳ Document templates
- ⏳ Collaborative features

## Technical Details

### Technologies

**Backend:**
- **Python 3.11+**: Core language
- **FastAPI**: REST API framework
- **DuckDB**: Embedded analytical database with FTS5
- **MCP SDK**: Model Context Protocol for AI integration
- **Anthropic SDK**: Claude API client
- **Watchdog**: Filesystem monitoring

**Frontend:**
- **React 18**: UI framework
- **Vite**: Build tool
- **Capacitor**: Native mobile wrapper
- **Dexie**: IndexedDB wrapper for offline storage
- **Recharts**: Data visualization

**Infrastructure:**
- **Docker**: Containerization
- **Alpine Linux**: Lightweight base image
- **Supervisord**: Process management
- **Nginx**: Reverse proxy (production)

### Database Schema

Key tables:
- `documents`: Core document metadata, extracted data, categorization
- `summaries`: Generated summaries by period and category
- `processing_events`: Event log for document pipeline
- `analytics`: Pre-computed metrics and trends

See [`ARCHITECTURE.md`](ARCHITECTURE.md#database-schema-duckdb) for complete schema.

### Security Considerations

- **API Keys**: Stored in environment variables, never in code
- **File isolation**: Each user container has isolated filesystem
- **Input validation**: All API inputs validated with Pydantic
- **SQL injection**: Protected via parameterized queries
- **XSS**: React automatically escapes output
- **Authentication**: JWT tokens for multi-user deployment

## Troubleshooting

### Document not processing

```bash
# Check processor logs
docker-compose logs document-processor

# Check file permissions
ls -la data/inbox/

# Manually trigger processing
docker-compose exec esec python -m document_processor.main
```

### API not responding

```bash
# Check API server status
curl http://localhost:8000/api/v1/health

# Check logs
docker-compose logs api-server

# Restart services
docker-compose restart
```

### Database issues

```bash
# Reinitialize database
docker-compose exec esec python scripts/init-db.py

# Backup database
cp data/alfrd.db data/alfrd.db.backup
```

## Contributing

We welcome contributions! Please see [`CONTRIBUTING.md`](CONTRIBUTING.md) for guidelines.

### Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Make your changes
4. Run tests: `pytest && npm test`
5. Commit: `git commit -m 'Add amazing feature'`
6. Push: `git push origin feature/amazing-feature`
7. Open a Pull Request

## License

This project is licensed under the MIT License - see [`LICENSE`](LICENSE) file for details.

## Support

- 📖 **Documentation**: [`ARCHITECTURE.md`](ARCHITECTURE.md)
- 🐛 **Issues**: [GitHub Issues](https://github.com/sirmick/alfrd/issues)
- 💬 **Discussions**: [GitHub Discussions](https://github.com/sirmick/alfrd/discussions)
- 📧 **Email**: support@example.com

## Acknowledgments

- Built with [Claude](https://anthropic.com) by Anthropic
- Inspired by personal frustration with document management
- MCP protocol by Anthropic
- Thanks to all contributors!

---

**⚡ Start managing your documents smarter, not harder.**
