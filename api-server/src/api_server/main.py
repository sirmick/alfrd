"""FastAPI application for esec API Server."""

import sys
from pathlib import Path
import uuid
import shutil
from datetime import datetime

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import FastAPI, UploadFile, File, HTTPException
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


@app.post("/api/v1/documents/upload-image")
async def upload_image(file: UploadFile = File(...)):
    """
    Upload an image document for processing.
    
    The image will be saved to the inbox with a folder structure
    and meta.json file for the document processor to pick up.
    
    Returns:
        dict: Contains document_id and status
    """
    # Validate file type
    allowed_types = ["image/jpeg", "image/jpg", "image/png", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type: {file.content_type}. Allowed: {', '.join(allowed_types)}"
        )
    
    # Generate document ID and create folder
    doc_id = str(uuid.uuid4())
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    folder_name = f"mobile_upload_{timestamp}"
    
    inbox_path = settings.inbox_path / folder_name
    inbox_path.mkdir(parents=True, exist_ok=True)
    
    # Determine file extension
    ext_map = {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp"
    }
    ext = ext_map.get(file.content_type, ".jpg")
    
    # Save uploaded file
    image_path = inbox_path / f"photo{ext}"
    with open(image_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Create meta.json
    meta = {
        "id": doc_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "documents": [
            {
                "file": f"photo{ext}",
                "type": "image",
                "order": 1
            }
        ],
        "metadata": {
            "source": "mobile_pwa",
            "tags": ["mobile", "upload"],
            "original_filename": file.filename or "photo"
        }
    }
    
    import json
    meta_path = inbox_path / "meta.json"
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    
    return {
        "document_id": doc_id,
        "status": "uploaded",
        "folder": folder_name,
        "message": "Document uploaded successfully and queued for processing"
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