#!/bin/bash
# Check status of development servers
# Usage: ./scripts/dev-status.sh

echo "📊 AI Document Secretary Server Status"
echo "========================================"
echo ""

# Check screen sessions
echo "Screen Sessions:"
if screen -list 2>/dev/null | grep -q esec; then
    screen -list | grep esec || echo "  No esec sessions found"
else
    echo "  No esec sessions running"
fi

echo ""
echo "API Health Check:"
if curl -s -f http://localhost:8000/api/v1/health > /dev/null 2>&1; then
    echo "  ✅ API Server is responding"
    curl -s http://localhost:8000/api/v1/health | python3 -m json.tool 2>/dev/null || echo "  (JSON parsing failed)"
else
    echo "  ❌ API Server is not responding"
fi

echo ""
echo "MCP Server:"
if screen -list | grep -q esec-mcp; then
    echo "  ✅ MCP Server screen session is active"
else
    echo "  ❌ MCP Server screen session not found"
fi

echo ""
echo "Document Processor:"
if screen -list | grep -q esec-processor; then
    echo "  ✅ Document Processor screen session is active"
else
    echo "  ❌ Document Processor screen session not found"
fi

echo ""
echo "To attach to a server:"
echo "  screen -r esec-api"
echo "  screen -r esec-mcp"
echo "  screen -r esec-processor"