#!/bin/bash
# Start MCP Server
# Usage: ./scripts/start-mcp.sh

cd "$(dirname "$0")/.."
exec python3 mcp-server/src/mcp_server/main.py