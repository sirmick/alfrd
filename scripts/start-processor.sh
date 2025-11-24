#!/bin/bash
# Start Document Processor
# Usage: ./scripts/start-processor.sh

cd "$(dirname "$0")/.."
exec python3 document-processor/src/document_processor/watcher.py