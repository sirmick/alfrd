#!/bin/bash
# Start Document Processor (Worker Pool Mode)
# Usage: ./scripts/start-processor.sh

cd "$(dirname "$0")/.."
exec python3 document-processor/src/document_processor/main.py