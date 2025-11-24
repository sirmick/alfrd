"""Document watcher using watchdog."""

import sys
from pathlib import Path

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from shared.config import Settings

# Initialize settings
settings = Settings()


def run_watcher():
    """Run the document processor watcher."""
    print(f"👀 Starting esec Document Processor")
    print(f"   Watching: {settings.inbox_path}")
    print(f"   Environment: {settings.env}")
    print()
    print("⚠️  Document Processor implementation coming soon!")
    print("   This processor will:")
    print("   - Watch for new documents in inbox")
    print("   - Extract text via OCR/PDF parsing")
    print("   - Store documents and metadata")
    print("   - Emit events to API server")
    print()
    
    # TODO: Implement actual watchdog file monitoring
    # For now, just keep the process alive
    try:
        import time
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Document Processor shutting down")


if __name__ == "__main__":
    run_watcher()