# ALFRD Scripts

Command-line utilities for ALFRD document management system.

## Features

- 🔧 Work from any directory
- 🐍 Automatically activate venv if it exists
- 📝 No `.sh` extension - clean command names
- 🚀 Simple and consistent interface

## Available Commands

### Database Management

```bash
# Initialize ALFRD database (required first time)
./scripts/init-db
```

### Document Management

```bash
# Add a document to inbox
./scripts/add-document photo.jpg --tags bill utilities

# Add multiple pages as one document
./scripts/add-document page1.jpg page2.jpg --tags invoice

# View documents (no API server needed)
./scripts/get-document                          # List all documents
./scripts/get-document <doc-id>                 # View specific document
./scripts/get-document --search "PG&E"          # Search documents
./scripts/get-document --status processed       # Filter by status
./scripts/get-document --type utility_bill      # Filter by type
./scripts/get-document --stats                  # Show statistics

# View tags (no API server needed)
./scripts/get-tags                              # List all tags
./scripts/get-tags --popular                    # Show popular tags
./scripts/get-tags --search "pge"               # Search tags

# View series (no API server needed)
./scripts/get-series                            # List all series
./scripts/get-series <series-id>                # View specific series
./scripts/get-series --entity "PG&E"            # Filter by entity
./scripts/get-series --type utility             # Filter by type

# View files (no API server needed)
./scripts/get-files                             # List all files
./scripts/get-files <file-id>                   # View specific file
./scripts/get-files --tags series:pge           # Filter by tags
./scripts/get-files --status generated          # Filter by status

# View prompts (no API server needed)
./scripts/view-prompts                          # View all prompts
./scripts/view-prompts --type classifier        # View classifier prompts
./scripts/view-prompts --all                    # Include archived versions
```

### AWS Utilities

```bash
# Get current AWS billing information
./scripts/get-aws-bill              # Current month summary
./scripts/get-aws-bill --daily      # Include daily trend
./scripts/get-aws-bill --json       # Raw JSON output
```

### Service Management

```bash
# Start API server (port 8000)
./scripts/start-api

# Start document processor workers
./scripts/start-processor

# Start Web UI (port 3000)
./scripts/start-webui
```

## Typical Workflow

```bash
# 1. First time setup
./scripts/init-db

# 2. Start services (3 terminals)
./scripts/start-api        # Terminal 1
./scripts/start-processor  # Terminal 2
./scripts/start-webui      # Terminal 3

# 3. Add documents via CLI or Web UI
./scripts/add-document samples/pg\&e-bill.jpg --tags bill

# 4. View processed results (no API server needed)
./scripts/get-document              # List all documents
./scripts/get-document --stats      # Show statistics
./scripts/get-tags --popular        # View popular tags
./scripts/get-series                # View detected series
./scripts/get-files                 # View generated files
```

## Direct Database Access

The new `get-*` scripts provide fast access to database information without requiring the API server to be running. They use the same database access layer as the API endpoints but skip the HTTP overhead:

- **get-document** - View, list, search documents with flexible filtering
- **get-tags** - View all tags, popular tags, or search by keyword
- **get-series** - View detected series and their documents
- **get-files** - View generated files and their metadata
- **view-prompts** - View prompt evolution history and performance

All scripts support partial ID matching for convenience (e.g., `./scripts/get-document 5a8b` will match the full UUID).

## How They Work

Each script:
1. Determines project root from its location
2. Activates `venv` if it exists
3. Changes to project root directory
4. Executes the appropriate Python module or service

## Implementation Details

**CLI Tools** are Python scripts in `document-processor/src/document_processor/cli/`:
- `add-document.py` - Create inbox folders with metadata
- `create-alfrd-db` - Initialize PostgreSQL database
- `get-document.py` - Query and display documents (direct DB access)
- `get-tags.py` - View and search tags (direct DB access)
- `get-series.py` - View series information (direct DB access)
- `get-files.py` - View file information (direct DB access)
- `view-prompts.py` - View prompt evolution history (direct DB access)

**Service Scripts** launch the main application components:
- `start-api` → `api-server/src/api_server/main.py`
- `start-processor` → `document-processor/src/document_processor/main.py`
- `start-webui` → `cd web-ui && npm run dev`

## Environment

Scripts automatically activate the Python virtual environment at `./venv` if it exists.

If venv is not set up:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Making Scripts Globally Available

Add to your shell's PATH:

```bash
# In ~/.bashrc or ~/.zshrc
export PATH="/path/to/alfrd/scripts:$PATH"

# Then run from anywhere:
add-document photo.jpg
view-document
```

Or create aliases:
```bash
alias alfrd-init='~/alfrd/scripts/init-db'
alias alfrd-add='~/alfrd/scripts/add-document'
alias alfrd-view='~/alfrd/scripts/view-document'
```
