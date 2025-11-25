#!/bin/bash
# Process documents in the inbox
# This script sets up the environment and runs the document processor

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Set PYTHONPATH to include both project root and document-processor/src
export PYTHONPATH="${PROJECT_ROOT}:${PROJECT_ROOT}/document-processor/src:${PYTHONPATH}"

# Run the document processor
python3 "${PROJECT_ROOT}/document-processor/src/document_processor/main.py" "$@"