"""FastAPI application for esec API Server."""

import sys
from pathlib import Path
import uuid
import shutil
from datetime import datetime, timezone
from typing import Optional, List
import json
import logging
import traceback
from contextlib import asynccontextmanager
from uuid import UUID

# Add project root to path for shared imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import uvicorn

from shared.config import Settings
from shared.database import AlfrdDatabase

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize settings
settings = Settings()

# Global database instance
db: Optional[AlfrdDatabase] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan (startup/shutdown)."""
    global db
    
    # Startup: Initialize database connection pool
    logger.info("Initializing database connection pool...")
    db = AlfrdDatabase(
        database_url=settings.database_url,
        pool_min_size=5,
        pool_max_size=20,
        pool_timeout=30.0
    )
    await db.initialize()
    logger.info("Database connection pool initialized")
    
    yield
    
    # Shutdown: Close database connection pool
    logger.info("Closing database connection pool...")
    if db:
        await db.close()
    logger.info("Database connection pool closed")


async def get_db() -> AlfrdDatabase:
    """Dependency for getting database instance."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database not initialized")
    return db


# Create FastAPI app with lifespan
app = FastAPI(
    title="esec API",
    description="AI Document Secretary API",
    version="0.1.0",
    lifespan=lifespan
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
async def health_check(database: AlfrdDatabase = Depends(get_db)):
    """Health check endpoint."""
    db_status = "healthy"
    try:
        # Simple query to check database connectivity
        await database.get_stats()
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
    
    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "services": {
            "api": "healthy",
            "database": db_status,
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
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
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
        "created_at": datetime.now(timezone.utc).isoformat() + "Z",
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
    
    # Create document record in database immediately
    database = await get_db()
    await database.create_document(
        doc_id=UUID(doc_id),
        filename=f"photo{ext}",
        original_path=str(inbox_path),
        file_type="image",
        file_size=inbox_path.stat().st_size if inbox_path.exists() else 0,
        status="pending",
        folder_path=str(inbox_path)
    )
    
    return {
        "document_id": doc_id,
        "status": "pending",
        "folder": folder_name,
        "message": "Document uploaded successfully and queued for processing"
    }


@app.get("/api/v1/documents/search")
async def search_documents(
    q: str = Query(..., description="Search query string"),
    limit: int = Query(50, ge=1, le=200, description="Number of results to return"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Full-text search across all documents.
    
    Query Parameters:
        - q: Search query string (required)
        - limit: Max number of results (1-200)
    
    Returns:
        List of matching documents with relevance ranking
    """
    logger.info(f"GET /api/v1/documents/search - query={q}, limit={limit}")
    try:
        # Perform full-text search
        results = await database.search_documents(q, limit=limit)
        
        logger.info(f"Search returned {len(results)} results")
        
        # Normalize data for JSON serialization
        for doc in results:
            if doc.get('id'):
                doc['id'] = str(doc['id'])
        
        return {
            "results": results,
            "count": len(results),
            "query": q
        }
    
    except Exception as e:
        logger.error(f"Error in search_documents: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Search error: {str(e)}")


@app.get("/api/v1/documents")
async def list_documents(
    status: Optional[str] = Query(None, description="Filter by status (e.g., 'completed', 'pending')"),
    document_type: Optional[str] = Query(None, description="Filter by document type (e.g., 'bill', 'finance')"),
    limit: int = Query(50, ge=1, le=200, description="Number of documents to return"),
    offset: int = Query(0, ge=0, description="Number of documents to skip"),
    database: AlfrdDatabase = Depends(get_db)
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
        # Get documents from database
        documents = await database.list_documents_api(
            limit=limit,
            offset=offset,
            status=status,
            document_type=document_type
        )
        
        logger.info(f"Query returned {len(documents)} documents")
        
        # Normalize data for JSON serialization and fetch tags from junction table
        for doc in documents:
            # Convert UUIDs to strings
            if doc.get('id'):
                doc_id_str = doc['id']
                doc['id'] = str(doc['id'])
                
                # Fetch tags from junction table
                try:
                    doc['tags'] = await database.get_document_tags(doc_id_str)
                except Exception as e:
                    logger.warning(f"Failed to fetch tags for {doc_id_str}: {e}")
                    doc['tags'] = []
            else:
                doc['tags'] = []
            
            # Ensure structured_data is an object (not null)
            if doc.get('structured_data') is None:
                doc['structured_data'] = {}
        
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
async def get_document(document_id: str, database: AlfrdDatabase = Depends(get_db)):
    """
    Get full details for a specific document.
    
    Path Parameters:
        - document_id: UUID of the document
    
    Returns:
        Complete document record with all metadata
    """
    logger.info(f"GET /api/v1/documents/{document_id}")
    try:
        # Parse UUID
        try:
            doc_uuid = UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document ID format: {document_id}")
        
        # Get document from database
        doc = await database.get_document_full(doc_uuid)
        
        if not doc:
            raise HTTPException(status_code=404, detail=f"Document not found: {document_id}")
        
        # Normalize data for JSON serialization
        doc_id_uuid = doc['id']
        doc['id'] = str(doc['id'])
        
        # Fetch tags from junction table
        try:
            doc['tags'] = await database.get_document_tags(doc_id_uuid)
        except Exception as e:
            logger.warning(f"Failed to fetch tags for {doc_id_uuid}: {e}")
            doc['tags'] = []
        
        if doc.get('structured_data') is None:
            doc['structured_data'] = {}
        
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
async def get_document_file(document_id: str, filename: str, database: AlfrdDatabase = Depends(get_db)):
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
        # Parse UUID
        try:
            doc_uuid = UUID(document_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid document ID format: {document_id}")
        
        # Get document's paths from database
        paths = await database.get_document_paths(doc_uuid)
        
        if not paths:
            raise HTTPException(status_code=404, detail="Document not found")
        
        # Try raw_document_path first (permanent storage), fallback to original_path (inbox)
        raw_path = paths.get('raw_document_path')
        original_path = paths.get('original_path')
        
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


# ==========================================
# FILE ENDPOINTS
# ==========================================

@app.post("/api/v1/files/create")
async def create_file(
    tags: List[str] = Query(..., description="Tags for the file"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Create a new file for documents matching tags.
    
    Files automatically include ALL documents (current and future) matching the specified
    tags. You don't need to manually select documents.
    
    Query Parameters:
        - tags: List of tags defining the file (documents must have ANY of these tags)
    
    Returns:
        Created file queued for summary generation
    """
    logger.info(f"POST /api/v1/files/create - tags={tags}")
    try:
        if not tags:
            raise HTTPException(status_code=400, detail="At least one tag is required")
        
        # Generate file ID
        file_id = uuid.uuid4()
        
        # Find or create file (tag-only, no document_type needed)
        file_record = await database.find_or_create_file(
            file_id=file_id,
            tags=tags,
            user_id=None  # TODO: Add user support
        )
        
        # Mark file as pending to trigger generation
        # FileGeneratorWorker will automatically query all documents matching the tags
        await database.update_file(file_record['id'], status='pending')
        
        # Convert UUID to string for JSON
        file_record['id'] = str(file_record['id'])
        
        return {
            "file": file_record,
            "message": "File created and queued for summary generation. Documents matching these tags will be included automatically."
        }
    
    except Exception as e:
        logger.error(f"Error creating file: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating file: {str(e)}")


@app.get("/api/v1/files")
async def list_files(
    tags: Optional[List[str]] = Query(None, description="Filter by tags (contains all)"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    List all files with optional filtering.
    
    Query Parameters:
        - tags: Filter by tags (file must contain all specified tags)
        - status: Filter by status (pending/generated/outdated)
        - limit: Max number of results
        - offset: Pagination offset
    
    Returns:
        List of files with summaries
    """
    logger.info(f"GET /api/v1/files - tags={tags}, status={status}")
    try:
        files = await database.list_files(
            limit=limit,
            offset=offset,
            tags=tags,
            status=status,
            user_id=None  # TODO: Add user support
        )
        
        # Convert UUIDs to strings
        for file in files:
            file['id'] = str(file['id'])
        
        return {
            "files": files,
            "count": len(files),
            "limit": limit,
            "offset": offset
        }
    
    except Exception as e:
        logger.error(f"Error listing files: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error listing files: {str(e)}")


@app.get("/api/v1/files/{file_id}")
async def get_file(file_id: str, database: AlfrdDatabase = Depends(get_db)):
    """
    Get details for a specific file including summary and documents.
    
    Path Parameters:
        - file_id: UUID of the file
    
    Returns:
        File record with summary and list of documents
    """
    logger.info(f"GET /api/v1/files/{file_id}")
    try:
        # Parse UUID
        try:
            file_uuid = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file ID format: {file_id}")
        
        # Get file record
        file_record = await database.get_file(file_uuid)
        
        if not file_record:
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
        
        # Get documents in file
        documents = await database.get_file_documents(file_uuid)
        
        # Convert UUIDs to strings
        file_record['id'] = str(file_record['id'])
        if file_record.get('prompt_version'):
            file_record['prompt_version'] = str(file_record['prompt_version'])
        
        for doc in documents:
            doc['id'] = str(doc['id'])
        
        return {
            "file": file_record,
            "documents": documents
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting file: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting file: {str(e)}")


@app.post("/api/v1/files/{file_id}/regenerate")
async def regenerate_file(file_id: str, database: AlfrdDatabase = Depends(get_db)):
    """
    Force regeneration of file summary.
    
    Path Parameters:
        - file_id: UUID of the file
    
    Returns:
        Status confirmation
    """
    logger.info(f"POST /api/v1/files/{file_id}/regenerate")
    try:
        # Parse UUID
        try:
            file_uuid = UUID(file_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file ID format: {file_id}")
        
        # Check file exists
        file_record = await database.get_file(file_uuid)
        if not file_record:
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
        
        # Mark as outdated to trigger regeneration
        await database.update_file(file_uuid, status='outdated')
        
        return {
            "file_id": file_id,
            "status": "queued",
            "message": "File queued for regeneration"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating file: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error regenerating file: {str(e)}")

# ==========================================
# TAG ENDPOINTS
# ==========================================

@app.get("/api/v1/tags")
async def list_tags(
    limit: int = Query(100, ge=1, le=500, description="Max number of tags to return"),
    order_by: str = Query("usage_count DESC", description="Sort order (usage_count DESC, tag_name ASC, last_used DESC)"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    List all tags with usage statistics.
    
    Query Parameters:
        - limit: Max number of tags (1-500)
        - order_by: Sort order (usage_count DESC, tag_name ASC, last_used DESC)
    
    Returns:
        List of tags with usage statistics and metadata
    """
    logger.info(f"GET /api/v1/tags - limit={limit}, order_by={order_by}")
    try:
        # Validate order_by parameter
        valid_orders = ["usage_count DESC", "usage_count ASC", "tag_name ASC", "tag_name DESC", "last_used DESC", "last_used ASC"]
        if order_by not in valid_orders:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid order_by parameter. Valid options: {', '.join(valid_orders)}"
            )
        
        # Get tags from database
        tags = await database.get_all_tags(limit=limit, order_by=order_by)
        
        logger.info(f"Returning {len(tags)} tags")
        
        return {
            "tags": tags,
            "count": len(tags),
            "limit": limit
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tags: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error listing tags: {str(e)}")


@app.get("/api/v1/tags/popular")
async def get_popular_tags(
    limit: int = Query(20, ge=1, le=100, description="Number of popular tags to return"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Get most popular tags for autocomplete/suggestions.
    
    Query Parameters:
        - limit: Number of tags to return (1-100)
    
    Returns:
        List of popular tag names ordered by usage
    """
    logger.info(f"GET /api/v1/tags/popular - limit={limit}")
    try:
        tag_names = await database.get_popular_tags(limit=limit)
        
        return {
            "tags": tag_names,
            "count": len(tag_names)
        }
    
    except Exception as e:
        logger.error(f"Error getting popular tags: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting popular tags: {str(e)}")


@app.get("/api/v1/tags/search")
async def search_tags(
    q: str = Query(..., description="Search query (partial tag name)"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Search for tags matching a query string.
    
    Query Parameters:
        - q: Search query (partial tag name)
        - limit: Max number of results (1-50)
    
    Returns:
        List of matching tag names
    """
    logger.info(f"GET /api/v1/tags/search - query={q}, limit={limit}")
    try:
        if not q or len(q) < 1:
            raise HTTPException(status_code=400, detail="Query must be at least 1 character")
        
        tag_names = await database.search_tags(query=q, limit=limit)
        
        return {
            "tags": tag_names,
            "count": len(tag_names),
            "query": q
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error searching tags: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error searching tags: {str(e)}")




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