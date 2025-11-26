"""FastAPI application for esec API Server."""

import sys
from pathlib import Path
import uuid
import shutil
from datetime import datetime
from typing import Optional, List
import json
import logging
import traceback

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn
import duckdb

from shared.config import Settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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


@app.get("/api/v1/documents")
async def list_documents(
    status: Optional[str] = Query(None, description="Filter by status (e.g., 'completed', 'pending')"),
    document_type: Optional[str] = Query(None, description="Filter by document type (e.g., 'bill', 'finance')"),
    limit: int = Query(50, ge=1, le=200, description="Number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip")
):
    """
    List documents from the database with optional filtering.
    
    Query Parameters:
        - status: Filter by document status
        - document_type: Filter by classified document type
        - limit: Max number of results (1-200)
        - offset: Skip N documents for pagination
    
    Returns:
        List of documents with basic metadata
    """
    logger.info(f"GET /api/v1/documents - status={status}, type={document_type}, limit={limit}, offset={offset}")
    try:
        logger.debug(f"Database path: {settings.database_path}")
        # Build query
        query = """
            SELECT
                id,
                created_at,
                status,
                document_type,
                suggested_type,
                secondary_tags,
                confidence,
                classification_confidence,
                summary,
                structured_data
            FROM documents
            WHERE 1=1
        """
        params = []
        
        if status:
            query += " AND status = ?"
            params.append(status)
        
        if document_type:
            query += " AND document_type = ?"
            params.append(document_type)
        
        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        
        # Execute query
        logger.debug(f"Executing query: {query}")
        logger.debug(f"Query params: {params}")
        
        conn = duckdb.connect(str(settings.database_path))
        result = conn.execute(query, params).fetchall()
        columns = [desc[0] for desc in conn.description]
        conn.close()
        
        logger.info(f"Query returned {len(result)} documents")
        
        # Format results
        documents = []
        for row in result:
            doc = dict(zip(columns, row))
            # Parse JSON fields
            if doc.get('secondary_tags'):
                doc['secondary_tags'] = json.loads(doc['secondary_tags'])
            if doc.get('structured_data'):
                doc['structured_data'] = json.loads(doc['structured_data'])
            documents.append(doc)
        
        response = {
            "documents": documents,
            "count": len(documents),
            "limit": limit,
            "offset": offset
        }
        logger.debug(f"Returning response with {len(documents)} documents")
        return response
    
    except Exception as e:
        logger.error(f"Error in list_documents: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/v1/documents/{document_id}")
async def get_document(document_id: str):
    """
    Get full details for a specific document.
    
    Path Parameters:
        - document_id: UUID of the document
    
    Returns:
        Complete document record with all metadata
    """
    logger.info(f"GET /api/v1/documents/{document_id}")
    try:
        logger.debug(f"Database path: {settings.database_path}")
        conn = duckdb.connect(str(settings.database_path))
        result = conn.execute(
            """
            SELECT
                id,
                created_at,
                updated_at,
                status,
                document_type,
                suggested_type,
                secondary_tags,
                original_path,
                raw_document_path,
                extracted_text_path,
                extracted_text,
                confidence,
                classification_confidence,
                classification_reasoning,
                summary,
                structured_data,
                error_message,
                user_id
            FROM documents
            WHERE id = ?
            """,
            [document_id]
        ).fetchone()
        
        if not result:
            conn.close()
            raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
        
        columns = [desc[0] for desc in conn.description]
        conn.close()
        
        # Build document dict
        doc = dict(zip(columns, result))
        
        # Parse JSON fields
        json_fields = ['secondary_tags', 'structured_data']
        for field in json_fields:
            if doc.get(field):
                try:
                    doc[field] = json.loads(doc[field])
                except:
                    pass
        
        # Add file links from raw_document_path (permanent storage)
        doc['files'] = []
        raw_path = doc.get('raw_document_path')
        if raw_path:
            raw_dir = Path(raw_path)
            if raw_dir.exists():
                for file in raw_dir.iterdir():
                    if file.is_file() and file.name != 'meta.json':
                        doc['files'].append({
                            'filename': file.name,
                            'url': f"/api/v1/documents/{document_id}/file/{file.name}"
                        })
        
        logger.debug(f"Returning document with {len(doc.get('files', []))} files")
        return doc
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_document: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")


@app.get("/api/v1/documents/{document_id}/file/{filename}")
async def get_document_file(document_id: str, filename: str):
    """
    Serve original document files (images, PDFs, etc.).
    
    Path Parameters:
        - document_id: UUID of the document
        - filename: Name of the file to retrieve
    
    Returns:
        File with appropriate content-type headers
    """
    logger.info(f"GET /api/v1/documents/{document_id}/file/{filename}")
    try:
        # Get document's raw_document_path from database
        conn = duckdb.connect(str(settings.database_path))
        result = conn.execute(
            "SELECT raw_document_path, original_path FROM documents WHERE id = ?",
            [document_id]
        ).fetchone()
        conn.close()
        
        if not result:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Try raw_document_path first (permanent storage), fallback to original_path (inbox)
        raw_path = result[0]
        original_path = result[1]
        
        if raw_path and Path(raw_path).exists():
            file_path = Path(raw_path) / filename
        elif original_path and Path(original_path).exists():
            file_path = Path(original_path) / filename
        else:
            raise HTTPException(status_code=404, detail="Document files not found")
        
        logger.debug(f"Original path from DB: {original_path}")
        logger.debug(f"Requested file path: {file_path}")
        
        # Security check: ensure file is within allowed directories (documents OR inbox)
        # Use absolute paths for comparison
        documents_path = settings.documents_path.resolve()
        inbox_path = settings.inbox_path.resolve()
        file_path_resolved = file_path.resolve()
        
        logger.debug(f"Resolved file path: {file_path_resolved}")
        logger.debug(f"Documents path: {documents_path}")
        logger.debug(f"Inbox path: {inbox_path}")
        
        # Check if file path is within documents OR inbox directory
        in_documents = False
        in_inbox = False
        
        try:
            file_path_resolved.relative_to(documents_path)
            in_documents = True
            logger.debug("File is in documents directory")
        except ValueError:
            pass
        
        try:
            file_path_resolved.relative_to(inbox_path)
            in_inbox = True
            logger.debug("File is in inbox directory")
        except ValueError:
            pass
        
        if not (in_documents or in_inbox):
            logger.error(f"Security check failed: {file_path_resolved} not in allowed directories")
            raise HTTPException(status_code=403, detail="Access denied")
        
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File not found: {filename}")
        
        # Determine media type
        media_types = {
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg',
            '.png': 'image/png',
            '.webp': 'image/webp',
            '.pdf': 'application/pdf',
            '.txt': 'text/plain'
        }
        media_type = media_types.get(file_path.suffix.lower(), 'application/octet-stream')
        
        logger.debug(f"Serving file: {file_path} as {media_type}")
        return FileResponse(
            path=file_path,
            media_type=media_type,
            filename=filename
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in get_document_file: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error serving file: {str(e)}")


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