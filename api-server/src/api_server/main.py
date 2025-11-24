"""FastAPI application for esec API Server."""

import sys
from pathlib import Path

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from shared.config import Settings

# Initialize settings
settings = Settings()

# Create FastAPI app
app = FastAPI(
    title="esec API",
    description="AI Document Secretary API",
    version="0.1.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "esec API",
        "version": "0.1.0",
        "status": "running"
    }


@app.get("/api/v1/health")
async def health_check():
    """Health check endpoint."""
    # TODO: Check database connection
    return {
        "status": "healthy",
        "services": {
            "api": "healthy",
            "database": "not_implemented",
            "processor": "unknown",
            "mcp": "unknown"
        }
    }


@app.get("/api/v1/status")
async def status():
    """System status endpoint."""
    return {
        "processor": {"status": "unknown"},
        "mcp_server": {"status": "unknown"},
        "api_server": {"status": "healthy"}
    }


def run_server():
    """Run the uvicorn server."""
    print(f"🚀 Starting esec API Server")
    print(f"   Host: {settings.api_host}:{settings.api_port}")
    print(f"   Environment: {settings.env}")
    print(f"   Docs: http://{settings.api_host}:{settings.api_port}/docs")
    print()
    
    # Run uvicorn with the app object directly
    # Note: reload mode requires import string, but we can't use that without pip install
    # So we disable reload when running directly - just restart the process manually
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=False,  # Disabled to avoid import issues
        log_level=settings.log_level.lower()
    )


if __name__ == "__main__":
    run_server()