#!/bin/bash
# Stop all development servers
# Usage: ./scripts/stop-dev.sh

echo "🛑 Stopping AI Document Secretary Development Servers"
echo "=================================================="

# Function to stop screen session
stop_screen() {
    local name=$1
    if screen -list | grep -q "$name"; then
        echo "Stopping $name..."
        screen -S "$name" -X quit 2>/dev/null || true
    else
        echo "$name is not running"
    fi
}

stop_screen "esec-api"
stop_screen "esec-mcp"
stop_screen "esec-processor"

echo ""
echo "✅ All servers stopped!"