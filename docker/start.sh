#!/bin/bash
# Startup script for ALFRD Docker container
# Runs API server, document processor, and web UI in screen sessions

set -e

echo "=================================================="
echo "🚀 ALFRD Container Starting"
echo "=================================================="
echo ""

# Initialize database if it doesn't exist
if [ ! -f "/data/alfrd.db" ]; then
    echo "📊 Initializing database..."
    cd /app
    python3 scripts/init-db.py
    echo ""
fi

# Start screen session with 3 windows
echo "📺 Starting screen session with 3 components..."
echo ""

# Create a detached screen session named 'alfrd'
screen -dmS alfrd -t api bash

# Window 0: API Server
screen -S alfrd -p 0 -X stuff "cd /app && python3 api-server/src/api_server/main.py^M"

# Window 1: Document Processor
screen -S alfrd -X screen -t processor bash
screen -S alfrd -p 1 -X stuff "cd /app && python3 document-processor/src/document_processor/main.py^M"

# Window 2: Web UI
screen -S alfrd -X screen -t webui bash
screen -S alfrd -p 2 -X stuff "cd /app/web-ui && npm run dev -- --host 0.0.0.0^M"

echo "✅ All components started in screen session 'alfrd'"
echo ""
echo "=================================================="
echo "📍 Service Endpoints:"
echo "   - API Server:  http://localhost:8000"
echo "   - Web UI:      http://localhost:5173"
echo "   - API Docs:    http://localhost:8000/docs"
echo ""
echo "🔧 Screen Commands:"
echo "   - Attach:      screen -r alfrd"
echo "   - List:        screen -ls"
echo "   - Switch:      Ctrl+A then 0/1/2"
echo "   - Detach:      Ctrl+A then d"
echo "=================================================="
echo ""

# Keep container running by attaching to screen
exec screen -r alfrd