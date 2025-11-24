"""MCP Server for esec AI integration."""

import sys
from pathlib import Path

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.config import Settings

# Initialize settings
settings = Settings()


def run_server():
    """Run the MCP server."""
    print(f"🤖 Starting esec MCP Server")
    print(f"   Port: {settings.mcp_port}")
    print(f"   Environment: {settings.env}")
    print()
    print("⚠️  MCP Server implementation coming soon!")
    print("   This server will handle:")
    print("   - Document categorization")
    print("   - Structured data extraction")
    print("   - Summary generation")
    print("   - Natural language queries")
    print()
    
    # TODO: Implement actual MCP server
    # For now, just keep the process alive
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 MCP Server shutting down")


if __name__ == "__main__":
    run_server()