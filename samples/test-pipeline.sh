#!/bin/bash
# Test the ALFRD self-improving pipeline with a sample document

set -e  # Exit on error

# Get script directory
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." && pwd )"

# Activate venv if it exists
if [ -f "$PROJECT_ROOT/venv/bin/activate" ]; then
    echo "🐍 Activating virtual environment..."
    source "$PROJECT_ROOT/venv/bin/activate"
else
    echo "⚠️  Warning: Virtual environment not found at $PROJECT_ROOT/venv/"
    echo "   Please create venv and install dependencies:"
    echo "   python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt"
    exit 1
fi

echo "========================================"
echo "ALFRD Self-Improving Pipeline Test"
echo "========================================"
echo

# Step 1: Initialize database
echo "📊 Step 1: Initializing database with prompts..."
cd "$PROJECT_ROOT"
./scripts/init-db
echo

# Step 2: Add sample document
echo "📄 Step 2: Adding sample document..."
./scripts/add-document samples/scl-smb-bill.png
echo

# Step 3: Run the processor in run-once mode
echo "🚀 Step 3: Running document processor (run-once mode)..."
echo "   (This will run the 5-worker self-improving pipeline until all documents are processed)"
echo
python3 document-processor/src/document_processor/main.py --once

echo
echo "✅ Pipeline test complete!"
echo
echo "To view the processed document:"
echo "  ./scripts/view-document <document_id>"