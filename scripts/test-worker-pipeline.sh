#!/bin/bash
# Test the worker-based document processing pipeline
# This script demonstrates the complete workflow from adding a document to processing it

set -e  # Exit on error

echo "=================================="
echo "🧪 ALFRD Worker Pipeline Test"
echo "=================================="
echo ""

# Step 1: Initialize database if it doesn't exist
if [ ! -f "./data/alfrd.db" ]; then
    echo "📊 Step 1: Initialize database"
    python3 scripts/init-db.py
    echo ""
else
    echo "📊 Step 1: Database already initialized ✓"
    echo ""
fi

# Step 2: Add a test document
echo "📄 Step 2: Add test document to inbox"
echo ""

# Check if sample file exists
if [ ! -f "samples/pg&e-bill.jpg" ]; then
    echo "⚠️  Sample file not found: samples/pg&e-bill.jpg"
    echo "   Using a text file instead..."
    
    # Create a sample text file
    mkdir -p ./temp
    cat > ./temp/test-bill.txt << 'EOF'
PG&E Electric Bill

Account Number: 1234567890
Service Address: 123 Main St, San Francisco, CA 94102

Billing Period: November 1-30, 2024
Due Date: December 15, 2024

Amount Due: $125.50

Usage: 350 kWh
Rate: $0.35/kWh

Thank you for your payment.
EOF
    
    python3 scripts/add-document.py ./temp/test-bill.txt --tags bill utilities electric --source test
else
    python3 scripts/add-document.py samples/pg\&e-bill.jpg --tags bill utilities electric --source test
fi

echo ""

# Step 3: Check inbox
echo "📁 Step 3: Check inbox contents"
echo ""
ls -la ./data/inbox/
echo ""

# Step 4: Process with OLD batch processor (for comparison)
echo "⏸️  Step 4: Skip old batch processor (will use workers instead)"
echo ""

# Step 5: Show how to use workers (manual test)
echo "🔧 Step 5: Worker-based processing"
echo ""
echo "To test the worker architecture:"
echo ""
echo "  # Option A: Run OCRWorker standalone (Python console)"
echo "  python3 << 'PYEOF'"
echo "import asyncio"
echo "from pathlib import Path"
echo "import sys"
echo "sys.path.insert(0, '.')"
echo "from shared.config import Settings"
echo "from document_processor.ocr_worker import OCRWorker"
echo ""
echo "async def test():"
echo "    settings = Settings()"
echo "    worker = OCRWorker(settings)"
echo "    "
echo "    # Process one batch"
echo "    docs = await worker.get_documents(worker.source_status, limit=10)"
echo "    print(f'Found {len(docs)} documents to process')"
echo "    "
echo "    for doc in docs:"
echo "        result = await worker.process_document(doc)"
echo "        print(f'Processed {doc[\"id\"]}: {result}')"
echo ""
echo "asyncio.run(test())"
echo "PYEOF"
echo ""
echo "  # Option B: Create a simple worker runner script"
echo "  # See: scripts/run-workers.py (to be created)"
echo ""

# Step 6: Query database
echo "📊 Step 6: Query database for document status"
echo ""
python3 << 'PYEOF'
import sys
from pathlib import Path
sys.path.insert(0, '.')

from shared.config import Settings
import duckdb

settings = Settings()
conn = duckdb.connect(str(settings.database_path))

try:
    # Query all documents
    results = conn.execute("""
        SELECT id, filename, status, created_at
        FROM documents
        ORDER BY created_at DESC
        LIMIT 5
    """).fetchall()
    
    if results:
        print("Recent documents:")
        print("-" * 80)
        for row in results:
            print(f"  ID: {row[0][:8]}... | File: {row[1]:30} | Status: {row[2]:15} | Created: {row[3]}")
    else:
        print("No documents found in database")
    
    # Show status counts
    print()
    status_counts = conn.execute("""
        SELECT status, COUNT(*) as count
        FROM documents
        GROUP BY status
    """).fetchall()
    
    if status_counts:
        print("Documents by status:")
        print("-" * 40)
        for row in status_counts:
            print(f"  {row[0]:20} {row[1]:3} documents")
    
finally:
    conn.close()
PYEOF

echo ""
echo "=================================="
echo "✅ Test Setup Complete!"
echo "=================================="
echo ""
echo "Next steps to test workers:"
echo "  1. Install dependencies: pip install -r requirements.txt"
echo "  2. Run tests: cd document-processor && python3 -m pytest tests/ -v"
echo "  3. Create worker runner script to orchestrate OCR + Classifier workers"
echo ""