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
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))
# Add api-server/src to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent))
# Add mcp-server/src to path for LLM client
sys.path.insert(0, str(project_root / "mcp-server" / "src"))

from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn

from shared.config import Settings
from shared.database import AlfrdDatabase
from shared.json_flattener import flatten_to_dataframe
from api_server.auth import (
    Token, LoginRequest, UserResponse,
    verify_password, create_access_token, decode_token, hash_password
)

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

# Public routes that don't require authentication
PUBLIC_ROUTES = {
    "/",
    "/api/v1/health",
    "/api/v1/status",
    "/api/v1/auth/login",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class AuthMiddleware(BaseHTTPMiddleware):
    """Middleware to enforce authentication on non-public routes."""

    async def dispatch(self, request: Request, call_next):
        # Skip auth for public routes
        path = request.url.path

        # Check if route is public
        if path in PUBLIC_ROUTES:
            return await call_next(request)

        # Check for static file routes or docs
        if path.startswith("/docs") or path.startswith("/redoc"):
            return await call_next(request)

        # Get Authorization header
        auth_header = request.headers.get("Authorization")

        # For file serving endpoints, also check for token in query params (for <img> tags)
        # Pattern: /api/v1/documents/{uuid}/file/{filename}?token=xxx
        if "/file/" in path and path.startswith("/api/v1/documents/"):
            query_token = request.query_params.get("token")
            if query_token:
                token_data = decode_token(query_token)
                if token_data and token_data.user_id:
                    request.state.user_id = token_data.user_id
                    request.state.username = token_data.username
                    return await call_next(request)

        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        token = auth_header.replace("Bearer ", "")
        token_data = decode_token(token)

        if token_data is None or token_data.user_id is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
                headers={"WWW-Authenticate": "Bearer"}
            )

        # Store user info in request state for later use
        request.state.user_id = token_data.user_id
        request.state.username = token_data.username

        return await call_next(request)


# CORS middleware (must be added after other middleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.env == "development" else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware
app.add_middleware(AuthMiddleware)

# HTTP Bearer security scheme for JWT
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    database: AlfrdDatabase = Depends(get_db)
) -> dict:
    """Dependency to get the current authenticated user."""
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    token_data = decode_token(credentials.credentials)

    if token_data is None or token_data.user_id is None:
        raise credentials_exception

    user = await database.get_user_by_id(token_data.user_id)

    if user is None:
        raise credentials_exception

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=401,
            detail="User account is disabled"
        )

    return user


async def optional_auth(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    database: AlfrdDatabase = Depends(get_db)
) -> Optional[dict]:
    """Optional auth dependency - returns user if authenticated, None otherwise."""
    if credentials is None:
        return None

    try:
        token_data = decode_token(credentials.credentials)
        if token_data is None or token_data.user_id is None:
            return None

        user = await database.get_user_by_id(token_data.user_id)
        if user is None or not user.get("is_active", False):
            return None

        return user
    except Exception:
        return None


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


# ==================== Authentication Endpoints ====================

@app.post("/api/v1/auth/login", response_model=Token)
async def login(
    login_request: LoginRequest,
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Authenticate user and return JWT token.

    Args:
        login_request: Username and password

    Returns:
        JWT access token
    """
    user = await database.get_user_by_username(login_request.username)

    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not verify_password(login_request.password, user["password_hash"]):
        raise HTTPException(
            status_code=401,
            detail="Invalid username or password"
        )

    if not user.get("is_active", False):
        raise HTTPException(
            status_code=401,
            detail="User account is disabled"
        )

    # Update last login
    await database.update_last_login(str(user["id"]))

    # Create access token
    access_token = create_access_token(
        data={
            "sub": str(user["id"]),
            "username": user["username"]
        }
    )

    return Token(access_token=access_token)


@app.get("/api/v1/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """
    Get current authenticated user info.

    Returns:
        Current user details
    """
    return UserResponse(
        id=str(current_user["id"]),
        username=current_user["username"],
        is_active=current_user["is_active"],
        created_at=current_user["created_at"],
        last_login=current_user.get("last_login")
    )


# ==================== Document Endpoints ====================

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


@app.get("/api/v1/search")
async def search(
    q: str = Query(..., description="Search query string"),
    limit: int = Query(20, ge=1, le=100, description="Number of results per type to return"),
    include_documents: bool = Query(True, description="Include document results"),
    include_files: bool = Query(True, description="Include file results"),
    include_series: bool = Query(True, description="Include series results"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Unified search across documents, files, and series.

    Query Parameters:
        - q: Search query string (required)
        - limit: Max number of results per type (1-100)
        - include_documents: Include document results (default: true)
        - include_files: Include file results (default: true)
        - include_series: Include series results (default: true)

    Returns:
        Results grouped by type (documents, files, series) with total count
    """
    logger.info(f"GET /api/v1/search - query={q}, limit={limit}")
    try:
        results = await database.search(
            query=q,
            limit=limit,
            include_documents=include_documents,
            include_files=include_files,
            include_series=include_series
        )

        logger.info(f"Search returned {results['total_count']} total results")
        return results

    except Exception as e:
        logger.error(f"Error in search: {str(e)}")
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
        
        # Ensure structured_data is an object (database layer handles JSON parsing)
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
        
        # Convert UUIDs to strings and parse JSONB tags
        for file in files:
            file['id'] = str(file['id'])
            
            # Parse tags JSONB field to ensure it's an array
            if file.get('tags'):
                if isinstance(file['tags'], str):
                    try:
                        file['tags'] = json.loads(file['tags'])
                    except (json.JSONDecodeError, TypeError):
                        file['tags'] = []
            else:
                file['tags'] = []
        
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
        
        # Convert UUIDs to strings and parse JSONB tags
        file_record['id'] = str(file_record['id'])
        if file_record.get('prompt_version'):
            file_record['prompt_version'] = str(file_record['prompt_version'])
        
        # Parse tags JSONB field to ensure it's an array
        if file_record.get('tags'):
            if isinstance(file_record['tags'], str):
                try:
                    file_record['tags'] = json.loads(file_record['tags'])
                except (json.JSONDecodeError, TypeError):
                    file_record['tags'] = []
        else:
            file_record['tags'] = []
        
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


@app.get("/api/v1/files/{file_id}/flatten")
async def flatten_file_data(
    file_id: str,
    array_strategy: str = Query('flatten', description="How to handle arrays (flatten, json, first, count)"),
    max_depth: Optional[int] = Query(None, description="Maximum nesting depth"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Flatten all documents in a file to tabular format.
    
    Returns the structured_data from all documents as a flat table structure
    suitable for display in a UI table component.
    
    Path Parameters:
        - file_id: UUID of the file
    
    Query Parameters:
        - array_strategy: How to handle arrays (flatten, json, first, count)
        - max_depth: Maximum nesting depth to flatten
    
    Returns:
        Flattened data with columns and rows
    """
    logger.info(f"GET /api/v1/files/{file_id}/flatten - array_strategy={array_strategy}")
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
        
        # Get documents in file
        documents = await database.get_file_documents(file_uuid)
        
        if not documents:
            logger.info(f"File {file_id}: No documents found for flattening")
            return {
                "columns": [],
                "rows": [],
                "count": 0,
                "message": "No documents found in file"
            }
        
        # Flatten documents to DataFrame
        df = flatten_to_dataframe(
            documents,
            array_strategy=array_strategy,
            max_depth=max_depth,
            include_metadata=True,
            metadata_columns=['id', 'created_at', 'document_type']
        )
        
        # Convert DataFrame to table format
        columns = df.columns.tolist()
        rows = df.to_dict(orient='records')
        
        logger.info(f"File {file_id}: Flattened {len(documents)} documents to {len(rows)} rows × {len(columns)} columns")
        
        # Convert datetime objects to ISO strings for JSON serialization
        for row in rows:
            for key, value in row.items():
                if hasattr(value, 'isoformat'):
                    row[key] = value.isoformat()
                elif value is None or (isinstance(value, float) and str(value) == 'nan'):
                    row[key] = None
        
        result = {
            "columns": columns,
            "rows": rows,
            "count": len(rows),
            "array_strategy": array_strategy
        }
        return result
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error flattening file data: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error flattening file data: {str(e)}")

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




# ==========================================
# SERIES ENDPOINTS
# ==========================================

@app.get("/api/v1/series")
async def list_series(
    entity: Optional[str] = Query(None, description="Filter by entity name"),
    series_type: Optional[str] = Query(None, description="Filter by series type"),
    frequency: Optional[str] = Query(None, description="Filter by frequency"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    List all series with optional filtering.
    
    Query Parameters:
        - entity: Filter by entity name
        - series_type: Filter by series type
        - frequency: Filter by frequency (monthly, quarterly, annual)
        - status: Filter by status (active, completed, archived)
        - limit: Max number of results
        - offset: Pagination offset
    
    Returns:
        List of series with metadata
    """
    logger.info(f"GET /api/v1/series - entity={entity}, type={series_type}")
    try:
        series_list = await database.list_series(
            limit=limit,
            offset=offset,
            entity=entity,
            series_type=series_type,
            frequency=frequency,
            status=status,
            user_id=None  # TODO: Add user support
        )
        
        # Convert UUIDs to strings
        for series in series_list:
            series['id'] = str(series['id'])
        
        return {
            "series": series_list,
            "count": len(series_list),
            "limit": limit,
            "offset": offset
        }
    
    except Exception as e:
        logger.error(f"Error listing series: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error listing series: {str(e)}")


@app.get("/api/v1/series/{series_id}")
async def get_series(series_id: str, database: AlfrdDatabase = Depends(get_db)):
    """
    Get details for a specific series including all documents.
    
    Path Parameters:
        - series_id: UUID of the series
    
    Returns:
        Series record with metadata and list of documents
    """
    logger.info(f"GET /api/v1/series/{series_id}")
    try:
        # Parse UUID
        try:
            series_uuid = UUID(series_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid series ID format: {series_id}")
        
        # Get series record
        series = await database.get_series(series_uuid)
        
        if not series:
            raise HTTPException(status_code=404, detail=f"Series not found: {series_id}")
        
        # Get documents in series
        documents = await database.get_series_documents(series_uuid)
        
        # Convert UUIDs to strings
        series['id'] = str(series['id'])
        for doc in documents:
            doc['id'] = str(doc['id'])
        
        return {
            "series": series,
            "documents": documents
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting series: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting series: {str(e)}")


@app.post("/api/v1/series/{series_id}/regenerate")
async def regenerate_series(series_id: str, database: AlfrdDatabase = Depends(get_db)):
    """
    Force regeneration of series summary.
    
    Path Parameters:
        - series_id: UUID of the series
    
    Returns:
        Status confirmation
    """
    logger.info(f"POST /api/v1/series/{series_id}/regenerate")
    try:
        # Parse UUID
        try:
            series_uuid = UUID(series_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid series ID format: {series_id}")
        
        # Check series exists
        series = await database.get_series(series_uuid)
        if not series:
            raise HTTPException(status_code=404, detail=f"Series not found: {series_id}")
        
        # Mark as outdated to trigger regeneration
        await database.update_series(series_uuid, status='active', last_generated_at=None)
        
        return {
            "series_id": series_id,
            "status": "queued",
            "message": "Series queued for regeneration"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating series: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error regenerating series: {str(e)}")


# ==========================================
# PROMPT MANAGEMENT ENDPOINTS
# ==========================================

@app.get("/api/v1/prompts")
async def list_prompts(
    prompt_type: Optional[str] = Query(None, description="Filter by prompt type (classifier, summarizer, file_summarizer, series_detector)"),
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    include_inactive: bool = Query(False, description="Include inactive prompts"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    List all prompts with optional filtering.
    
    Query Parameters:
        - prompt_type: Filter by prompt type
        - document_type: Filter by document type
        - include_inactive: Include inactive prompts
    
    Returns:
        List of prompts with metadata
    """
    logger.info(f"GET /api/v1/prompts - type={prompt_type}, doc_type={document_type}, include_inactive={include_inactive}")
    try:
        prompts = await database.list_prompts(
            prompt_type=prompt_type,
            document_type=document_type,
            include_inactive=include_inactive
        )
        
        # Convert UUIDs to strings
        for prompt in prompts:
            prompt['id'] = str(prompt['id'])
        
        return {
            "prompts": prompts,
            "count": len(prompts)
        }
    
    except Exception as e:
        logger.error(f"Error listing prompts: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error listing prompts: {str(e)}")


@app.get("/api/v1/prompts/active")
async def get_active_prompts(
    prompt_type: Optional[str] = Query(None, description="Filter by prompt type"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Get all active prompts (one per prompt_type/document_type combination).
    
    Query Parameters:
        - prompt_type: Filter by prompt type
    
    Returns:
        List of active prompts
    """
    logger.info(f"GET /api/v1/prompts/active - type={prompt_type}")
    try:
        prompts = await database.list_prompts(
            prompt_type=prompt_type,
            include_inactive=False
        )
        
        # Convert UUIDs to strings
        for prompt in prompts:
            prompt['id'] = str(prompt['id'])
        
        return {
            "prompts": prompts,
            "count": len(prompts)
        }
    
    except Exception as e:
        logger.error(f"Error getting active prompts: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting active prompts: {str(e)}")


@app.get("/api/v1/prompts/{prompt_id}")
async def get_prompt(prompt_id: str, database: AlfrdDatabase = Depends(get_db)):
    """
    Get a specific prompt by ID.
    
    Path Parameters:
        - prompt_id: UUID of the prompt
    
    Returns:
        Complete prompt record
    """
    logger.info(f"GET /api/v1/prompts/{prompt_id}")
    try:
        # Parse UUID
        try:
            prompt_uuid = UUID(prompt_id)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid prompt ID format: {prompt_id}")
        
        # Get all prompts and find the one with matching ID
        all_prompts = await database.list_prompts(include_inactive=True)
        prompt = next((p for p in all_prompts if p['id'] == prompt_uuid), None)
        
        if not prompt:
            raise HTTPException(status_code=404, detail=f"Prompt not found: {prompt_id}")
        
        # Convert UUID to string
        prompt['id'] = str(prompt['id'])
        
        return prompt
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting prompt: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting prompt: {str(e)}")


@app.post("/api/v1/prompts")
async def create_prompt(
    prompt_type: str = Query(..., description="Type of prompt (classifier, summarizer, file_summarizer, series_detector)"),
    prompt_text: str = Query(..., description="The prompt text"),
    document_type: Optional[str] = Query(None, description="Document type (for summarizers)"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Create a new prompt version.
    
    Query Parameters:
        - prompt_type: Type of prompt
        - prompt_text: The prompt text
        - document_type: Document type (required for summarizers)
    
    Returns:
        Created prompt record
    """
    logger.info(f"POST /api/v1/prompts - type={prompt_type}, doc_type={document_type}")
    try:
        # Validate prompt_type
        valid_types = ['classifier', 'summarizer', 'file_summarizer', 'series_detector']
        if prompt_type not in valid_types:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid prompt_type. Must be one of: {', '.join(valid_types)}"
            )
        
        # Validate document_type for summarizers
        if prompt_type == 'summarizer' and not document_type:
            raise HTTPException(
                status_code=400,
                detail="document_type is required for summarizer prompts"
            )
        
        # Get existing prompts to determine next version
        existing = await database.list_prompts(
            prompt_type=prompt_type,
            document_type=document_type,
            include_inactive=True
        )
        
        # Calculate next version
        max_version = 0
        for p in existing:
            if p['version'] > max_version:
                max_version = p['version']
        next_version = max_version + 1
        
        # Deactivate old versions
        await database.deactivate_old_prompts(prompt_type, document_type)
        
        # Create new prompt
        prompt_id = uuid.uuid4()
        await database.create_prompt(
            prompt_id=prompt_id,
            prompt_type=prompt_type,
            prompt_text=prompt_text,
            document_type=document_type,
            version=next_version,
            performance_score=0.5  # Default initial score
        )
        
        # Fetch and return the created prompt
        all_prompts = await database.list_prompts(include_inactive=True)
        prompt = next((p for p in all_prompts if p['id'] == prompt_id), None)
        
        if prompt:
            prompt['id'] = str(prompt['id'])
        
        return {
            "prompt": prompt,
            "message": f"Created prompt version {next_version}"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating prompt: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error creating prompt: {str(e)}")


@app.get("/api/v1/document-types")
async def list_document_types(
    active_only: bool = Query(True, description="Only return active document types"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    List all document types.

    Query Parameters:
        - active_only: Only return active types

    Returns:
        List of document types
    """
    logger.info(f"GET /api/v1/document-types - active_only={active_only}")
    try:
        types = await database.get_document_types(active_only=active_only)

        # Convert UUIDs to strings
        for dt in types:
            dt['id'] = str(dt['id'])

        return {
            "document_types": types,
            "count": len(types)
        }

    except Exception as e:
        logger.error(f"Error listing document types: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error listing document types: {str(e)}")


# ==========================================
# EVENT LOG ENDPOINTS
# ==========================================

from pydantic import BaseModel

class ChatRequest(BaseModel):
    """Request model for chat endpoint."""
    message: str
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    """Response model for chat endpoint."""
    response: str
    session_id: str
    tool_calls: List[dict] = []


# Global chat service (initialized lazily)
_chat_service = None


async def get_chat_service(database: AlfrdDatabase = Depends(get_db)):
    """Get or create chat service instance."""
    global _chat_service
    if _chat_service is None:
        # Import works both as module and when run directly
        try:
            from .chat_service import ChatService
        except ImportError:
            from api_server.chat_service import ChatService
        _chat_service = ChatService(database)
    return _chat_service


# ==========================================
# CHAT ENDPOINTS
# ==========================================

@app.post("/api/v1/chat", response_model=ChatResponse)
async def chat(
    request: ChatRequest,
    chat_service = Depends(get_chat_service)
):
    """
    Send a message to the AI assistant.

    The assistant can query documents, series, files, and tags using tools.
    Provide a session_id to continue a conversation, or omit it to start a new one.

    Request Body:
        - message: The user's message
        - session_id: Optional session ID to continue a conversation

    Returns:
        AI response with session ID for continuation
    """
    logger.info(f"POST /api/v1/chat - session={request.session_id}, message={request.message[:50]}...")
    try:
        result = await chat_service.chat(
            user_message=request.message,
            session_id=request.session_id
        )

        return ChatResponse(
            response=result["response"],
            session_id=result["session_id"],
            tool_calls=result.get("tool_calls", [])
        )

    except Exception as e:
        logger.error(f"Error in chat: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Chat error: {str(e)}")


@app.delete("/api/v1/chat/{session_id}")
async def delete_chat_session(
    session_id: str,
    chat_service = Depends(get_chat_service)
):
    """
    Delete a chat session to clear conversation history.

    Path Parameters:
        - session_id: The session ID to delete

    Returns:
        Confirmation of deletion
    """
    logger.info(f"DELETE /api/v1/chat/{session_id}")
    try:
        deleted = chat_service.delete_session(session_id)
        if not deleted:
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        return {"message": "Session deleted", "session_id": session_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting session: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error deleting session: {str(e)}")


@app.get("/api/v1/events")
async def get_events(
    id: Optional[str] = Query(None, description="Entity UUID (document, file, or series - auto-detected)"),
    document_id: Optional[str] = Query(None, description="Filter by document UUID (explicit)"),
    file_id: Optional[str] = Query(None, description="Filter by file UUID (explicit)"),
    series_id: Optional[str] = Query(None, description="Filter by series UUID (explicit)"),
    event_category: Optional[str] = Query(None, description="Filter by category (state_transition, llm_request, processing, error, user_action)"),
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    limit: int = Query(100, ge=1, le=1000, description="Max number of events to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
    database: AlfrdDatabase = Depends(get_db)
):
    """
    Get events for documents, files, or series.

    Pass `id` with any UUID and it will auto-detect whether it's a document, file, or series.
    Alternatively, use explicit document_id/file_id/series_id parameters.

    Query Parameters:
        - id: Any entity UUID (auto-detects type)
        - document_id: Filter by document UUID (explicit)
        - file_id: Filter by file UUID (explicit)
        - series_id: Filter by series UUID (explicit)
        - event_category: Filter by category
        - event_type: Filter by type
        - limit: Max results (1-1000)
        - offset: Pagination offset

    Returns:
        List of events ordered by created_at DESC
    """
    logger.info(f"GET /api/v1/events - id={id}, doc={document_id}, file={file_id}, series={series_id}")
    try:
        # Parse UUIDs if provided
        doc_uuid = None
        file_uuid = None
        series_uuid = None

        # Handle generic `id` parameter - auto-detect entity type
        if id:
            try:
                entity_uuid = UUID(id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid id format: {id}")

            # Check which table contains this UUID
            doc = await database.get_document(entity_uuid)
            if doc:
                doc_uuid = entity_uuid
            else:
                file_record = await database.get_file(entity_uuid)
                if file_record:
                    file_uuid = entity_uuid
                else:
                    series_record = await database.get_series(entity_uuid)
                    if series_record:
                        series_uuid = entity_uuid
                    else:
                        raise HTTPException(status_code=404, detail=f"No document, file, or series found with id: {id}")

        # Handle explicit parameters (override auto-detected if both provided)
        if document_id:
            try:
                doc_uuid = UUID(document_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid document_id format: {document_id}")

        if file_id:
            try:
                file_uuid = UUID(file_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid file_id format: {file_id}")

        if series_id:
            try:
                series_uuid = UUID(series_id)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid series_id format: {series_id}")

        # Validate event_category if provided
        if event_category:
            valid_categories = ['state_transition', 'llm_request', 'processing', 'error', 'user_action']
            if event_category not in valid_categories:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid event_category. Must be one of: {', '.join(valid_categories)}"
                )

        # Get events from database
        events = await database.get_events(
            document_id=doc_uuid,
            file_id=file_uuid,
            series_id=series_uuid,
            event_category=event_category,
            event_type=event_type,
            limit=limit,
            offset=offset
        )

        # Convert UUIDs to strings for JSON serialization
        for event in events:
            event['id'] = str(event['id'])
            if event.get('document_id'):
                event['document_id'] = str(event['document_id'])
            if event.get('file_id'):
                event['file_id'] = str(event['file_id'])
            if event.get('series_id'):
                event['series_id'] = str(event['series_id'])
            # Convert datetime to ISO string
            if event.get('created_at'):
                event['created_at'] = event['created_at'].isoformat()

        logger.info(f"Returning {len(events)} events")

        return {
            "events": events,
            "count": len(events),
            "limit": limit,
            "offset": offset
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting events: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Error getting events: {str(e)}")


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