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
    print(f"🤖 MCP Server Information")
    print(f"   Environment: {settings.env}")
    print()
    print("ℹ️  Note: MCP functionality is integrated directly into workers")
    print("   The MCP server doesn't need to run as a separate process.")
    print()
    print("   MCP tools are called by:")
    print("   - ClassifierWorker → classify_document()")
    print("   - WorkflowWorker → summarize_bill(), etc.")
    print()
    print("   To test MCP tools directly:")
    print("   >>> from mcp_server.tools.classify_document import classify_document")
    print("   >>> from mcp_server.tools.summarize_bill import summarize_bill")
    print("   >>> from mcp_server.llm import LLMClient")
    print()
    print("✅ No separate MCP server process needed!")


if __name__ == "__main__":
    run_server()