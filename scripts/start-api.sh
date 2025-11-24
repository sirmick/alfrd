#!/bin/bash
# Start API Server
# Usage: ./scripts/start-api.sh

cd "$(dirname "$0")/.."
exec python3 api-server/src/api_server/main.py