#!/bin/bash
# Start all development servers in screen sessions
# Usage: ./scripts/start-dev.sh

set -e

PROJECT_ROOT="/home/mick/esec"
VENV="$PROJECT_ROOT/venv/bin/python3"

echo "🚀 Starting AI Document Secretary Development Servers"
echo "=================================================="

# Check if virtual environment exists
if [ ! -f "$VENV" ]; then
    echo "❌ Virtual environment not found at $VENV"
    echo "Please create it first: python3 -m venv venv"
    exit 1
fi

# Check if .env exists
if [ ! -f "$PROJECT_ROOT/.env" ]; then
    echo "❌ .env file not found"
    echo "Please copy .env.example to .env and configure it"
    exit 1
fi

# Function to check if screen session exists
screen_exists() {
    screen -list | grep -q "$1"
}

# Function to start a screen session
start_screen() {
    local name=$1
    local dir=$2
    local cmd=$3
    
    if screen_exists "$name"; then
        echo "⚠️  Screen session '$name' already exists. Killing it..."
        screen -S "$name" -X quit 2>/dev/null || true
        sleep 1
    fi
    
    echo "▶️  Starting $name in screen session..."
    cd "$PROJECT_ROOT/$dir"
    screen -dmS "$name" bash -c "cd '$PROJECT_ROOT/$dir' && PYTHONPATH='$PROJECT_ROOT:$PYTHONPATH' '$VENV' $cmd; exec bash"
    sleep 1
}

# Start API Server
echo "▶️  Starting esec-api in screen session..."
screen -dmS "esec-api" bash -c "cd '$PROJECT_ROOT' && ./scripts/start-api.sh; exec bash"
sleep 1

# Start MCP Server
echo "▶️  Starting esec-mcp in screen session..."
screen -dmS "esec-mcp" bash -c "cd '$PROJECT_ROOT' && ./scripts/start-mcp.sh; exec bash"
sleep 1

# Start Document Processor Watcher
echo "▶️  Starting esec-processor in screen session..."
screen -dmS "esec-processor" bash -c "cd '$PROJECT_ROOT' && ./scripts/start-processor.sh; exec bash"
sleep 1

echo ""
echo "✅ All servers started!"
echo ""
echo "Screen Sessions:"
echo "  - esec-api       (API Server)"
echo "  - esec-mcp       (MCP Server)"
echo "  - esec-processor (Document Processor)"
echo ""
echo "Commands:"
echo "  View all sessions:    screen -list"
echo "  Attach to API:        screen -r esec-api"
echo "  Attach to MCP:        screen -r esec-mcp"
echo "  Attach to Processor:  screen -r esec-processor"
echo "  Detach from screen:   Ctrl+A then D"
echo "  Stop all servers:     ./scripts/stop-dev.sh"
echo ""
echo "Check status:"
echo "  curl http://localhost:8000/api/v1/health"