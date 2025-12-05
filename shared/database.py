"""Shared PostgreSQL database access layer for ALFRD.

This module provides a unified database interface used by:
- Document processor workers
- API server endpoints
- CLI scripts (add-document, view-prompts, view-document)

All database operations in ALFRD go through this class.
"""

from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, List, Any
from uuid import UUID, uuid4
import asyncpg
import json


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class AlfrdDatabase:
    """Shared database access layer for ALFRD with connection pooling."""
    
    def __init__(self, database_url: str, pool_min_size: int = 5, pool_max_size: int = 20, pool_timeout: float = 30.0):
        """Initialize database connection manager.
        
        Args:
            database_url: PostgreSQL connection string (e.g., postgresql://user@/dbname?host=/var/run/postgresql)
            pool_min_size: Minimum connections in pool
            pool_max_size: Maximum connections in pool
            pool_timeout: Connection timeout in seconds
        """
        self.database_url = database_url
        self.pool_min_size = pool_min_size
        self.pool_max_size = pool_max_size
        self.pool_timeout = pool_timeout
        self.pool: Optional[asyncpg.Pool] = None
    
    async def initialize(self):
        """Initialize the connection pool with JSONB type codec."""
        if self.pool is None:
            async def init_connection(conn):
                """Set up JSONB codec for each connection.
                
                This is called for EVERY new connection in the pool,
                ensuring consistent JSONB handling across all connections.
                """
                # Register JSONB codec to automatically convert between Python dict and JSONB
                await conn.set_type_codec(
                    'jsonb',
                    encoder=json.dumps,  # Python dict -> JSON string -> JSONB binary
                    decoder=json.loads,  # JSONB binary -> JSON string -> Python dict
                    schema='pg_catalog',
                    format='text'  # Explicitly use text format for compatibility
                )
            
            self.pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
                timeout=self.pool_timeout,
                init=init_connection  # This callback runs for EVERY new connection
            )
    
    async def close(self):
        """Close the connection pool."""
        if self.pool is not None:
            await self.pool.close()
            self.pool = None
    
    # ==========================================
    # DOCUMENT OPERATIONS
    # ==========================================
    
    async def create_document(
        self,
        doc_id: UUID,
        filename: str,
        original_path: str,
        file_type: str,
        file_size: int,
        status: str,
        raw_document_path: str = None,
        extracted_text_path: str = None,
        metadata_path: str = None,
        folder_path: str = None,
        **kwargs
    ) -> UUID:
        """Create a new document record.
        
        Args:
            doc_id: Document UUID
            filename: Original filename
            original_path: Original file path
            file_type: Type of file (folder, image, pdf, etc.)
            file_size: Size in bytes
            status: Processing status
            raw_document_path: Path to stored raw document
            extracted_text_path: Path to extracted text file
            metadata_path: Path to metadata JSON
            folder_path: Path to document folder
            **kwargs: Additional fields
            
        Returns:
            Document UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            # Try to insert, ignore if already exists
            await conn.execute("""
                INSERT INTO documents (
                    id, filename, original_path, file_type, file_size,
                    status, raw_document_path, extracted_text_path,
                    metadata_path, folder_path, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                ON CONFLICT (id) DO NOTHING
            """,
                doc_id, filename, original_path, file_type, file_size,
                status, raw_document_path, extracted_text_path,
                metadata_path, folder_path, utc_now()
            )
        
        return doc_id
    
    async def get_document(self, doc_id: UUID) -> Optional[Dict[str, Any]]:
        """Get document by ID.
        
        Args:
            doc_id: Document UUID
            
        Returns:
            Document dict or None if not found
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, filename, original_path, file_type, file_size,
                       status, processed_at, error_message,
                       document_type, suggested_type,
                       classification_confidence, classification_reasoning,
                       category, subcategory, confidence,
                       vendor, amount, currency, due_date, issue_date,
                       raw_document_path, extracted_text_path, metadata_path, folder_path,
                       created_at, updated_at, user_id,
                       extracted_text, summary, structured_data, folder_metadata
                FROM documents
                WHERE id = $1
            """, doc_id)
            
            return dict(row) if row else None
    
    async def update_document(self, doc_id: UUID, **fields):
        """Update document fields.
        
        Args:
            doc_id: Document UUID
            **fields: Fields to update (key=value pairs)
        """
        await self.initialize()
        
        if not fields:
            return
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Ensure doc_id is a UUID object
        from uuid import UUID as UUIDType
        if isinstance(doc_id, str):
            doc_id = UUIDType(doc_id)
        
        # JSONB fields that need JSON serialization
        jsonb_fields = {'structured_data', 'folder_metadata'}
        
        # Log incoming fields for debugging
        logger.info(f"update_document called with fields: {list(fields.keys())}")
        for key, value in fields.items():
            logger.info(f"  {key}: type={type(value).__name__}, value={repr(value)[:100]}")
        
        # Serialize JSONB fields and handle complex types
        values = []
        for key, value in fields.items():
            if key in jsonb_fields and value is not None and not isinstance(value, str):
                serialized = json.dumps(value)
                values.append(serialized)
                logger.info(f"  Serialized {key} to JSON: {serialized[:100]}")
            elif isinstance(value, (list, dict)) and key not in jsonb_fields:
                # Convert unexpected lists/dicts to JSON string
                serialized = json.dumps(value)
                values.append(serialized)
                logger.warning(f"  Unexpected complex type for {key}, converting to JSON: {serialized[:100]}")
            else:
                values.append(value)
        
        # Build dynamic UPDATE query with explicit UUID casting
        set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(fields.keys())]
        set_clause = ", ".join(set_clauses)
        
        query = f"""
            UPDATE documents
            SET {set_clause}, updated_at = ${len(values) + 2}
            WHERE id = $1::uuid
        """
        
        logger.info(f"Executing query with {len(values)} values (doc_id={doc_id})")
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, str(doc_id), *values, utc_now())
    
    async def get_documents_by_status(self, status: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Get documents with specific status.
        
        Args:
            status: Document status to filter by
            limit: Maximum number of documents to return
            
        Returns:
            List of document dicts
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, filename, file_type, status, folder_path,
                       extracted_text, extracted_text_path, created_at, document_type,
                       classification_confidence, classification_reasoning,
                       structured_data, confidence
                FROM documents
                WHERE status = $1
                ORDER BY created_at ASC
                LIMIT $2
            """, status, limit)
            
            return [dict(row) for row in rows]
    
    async def list_documents(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = None,
        document_type: str = None,
        order_by: str = "created_at DESC"
    ) -> List[Dict[str, Any]]:
        """List documents with optional filtering.
        
        Args:
            limit: Maximum number of documents
            offset: Pagination offset
            status: Filter by status
            document_type: Filter by document type
            order_by: SQL ORDER BY clause
            
        Returns:
            List of document dicts
        """
        await self.initialize()
        
        conditions = []
        params = []
        param_count = 1
        
        if status:
            conditions.append(f"status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if document_type:
            conditions.append(f"document_type = ${param_count}")
            params.append(document_type)
            param_count += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        params.extend([limit, offset])
        
        query = f"""
            SELECT id, filename, file_type, status, document_type,
                   vendor, amount, due_date, created_at, summary
            FROM documents
            {where_clause}
            ORDER BY {order_by}
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    async def list_documents_api(
        self,
        limit: int = 50,
        offset: int = 0,
        status: str = None,
        document_type: str = None
    ) -> List[Dict[str, Any]]:
        """List documents for API endpoint with specific fields.
        
        Args:
            limit: Maximum number of documents
            offset: Pagination offset
            status: Filter by status
            document_type: Filter by document type
            
        Returns:
            List of document dicts with API-specific fields
        """
        await self.initialize()
        
        conditions = []
        params = []
        param_count = 1
        
        if status:
            conditions.append(f"status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if document_type:
            conditions.append(f"document_type = ${param_count}")
            params.append(document_type)
            param_count += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        params.extend([limit, offset])
        
        query = f"""
            SELECT
                id,
                created_at,
                status,
                document_type,
                suggested_type,
                confidence,
                classification_confidence,
                summary,
                structured_data
            FROM documents
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            # Parse JSONB fields to ensure they're proper JSON objects
            results = []
            for row in rows:
                doc = dict(row)
                # Parse structured_data if it's a string
                if doc.get('structured_data') and isinstance(doc['structured_data'], str):
                    import json
                    try:
                        doc['structured_data'] = json.loads(doc['structured_data'])
                    except (json.JSONDecodeError, TypeError):
                        doc['structured_data'] = {}
                results.append(doc)
            return results
    
    async def get_document_full(self, doc_id: UUID) -> Optional[Dict[str, Any]]:
        """Get complete document details for API endpoint.
        
        Args:
            doc_id: Document UUID
            
        Returns:
            Complete document dict with all fields or None if not found
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT
                    id,
                    created_at,
                    updated_at,
                    status,
                    document_type,
                    suggested_type,
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
                WHERE id = $1
            """, doc_id)
            
            if not row:
                return None
            
            # Convert to dict and parse structured_data if needed
            doc = dict(row)
            if doc.get('structured_data') and isinstance(doc['structured_data'], str):
                import json
                try:
                    doc['structured_data'] = json.loads(doc['structured_data'])
                except (json.JSONDecodeError, TypeError):
                    doc['structured_data'] = {}
            
            return doc
    
    async def get_document_paths(self, doc_id: UUID) -> Optional[Dict[str, str]]:
        """Get document file paths for serving files.
        
        Args:
            doc_id: Document UUID
            
        Returns:
            Dict with raw_document_path and original_path or None if not found
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT raw_document_path, original_path
                FROM documents
                WHERE id = $1
            """, doc_id)
            
            return dict(row) if row else None
    
    async def delete_document(self, doc_id: UUID):
        """Delete document (cascade deletes related records).
        
        Args:
            doc_id: Document UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM documents WHERE id = $1", doc_id)
    
    async def search_documents(self, query: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Full-text search across documents.
        
        Args:
            query: Search query string
            limit: Maximum number of results
            
        Returns:
            List of matching document dicts
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, filename, document_type, vendor,
                       created_at, summary, structured_data,
                       ts_rank(extracted_text_tsv, to_tsquery($1)) as rank
                FROM documents
                WHERE extracted_text_tsv @@ to_tsquery($1)
                ORDER BY rank DESC
                LIMIT $2
            """, query, limit)
            
            return [dict(row) for row in rows]
    
    async def get_documents_by_tags(
        self,
        document_type: str = None,
        tags: List[str] = None,
        order_by: str = "created_at DESC",
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """Get documents matching specific tags using junction table.
        
        Args:
            document_type: Filter by document type
            tags: List of tag names (documents must contain ANY of the specified tags)
            order_by: SQL ORDER BY clause
            limit: Maximum results
            
        Returns:
            List of document dicts
        """
        await self.initialize()
        
        conditions = []
        params = []
        param_count = 1
        
        # Base query uses document_tags junction table if tags are specified
        if tags:
            # Normalize tags for matching
            normalized_tags = [self.normalize_tag(tag) for tag in tags]
            
            # Query with COUNT to ensure documents have ALL specified tags
            # Documents must match ALL tags to be included
            query = f"""
                SELECT DISTINCT d.id, d.filename, d.created_at, d.document_type,
                       d.summary, d.structured_data, d.extracted_text
                FROM documents d
                WHERE d.status = 'completed'
                  AND (
                    SELECT COUNT(DISTINCT t.tag_normalized)
                    FROM document_tags dt
                    INNER JOIN tags t ON dt.tag_id = t.id
                    WHERE dt.document_id = d.id
                      AND t.tag_normalized = ANY($1::text[])
                  ) = $2
                ORDER BY d.{order_by}
                LIMIT $3
            """
            params = [normalized_tags, len(normalized_tags), limit]
        else:
            # No tags specified, just filter by type and status
            if document_type:
                conditions.append(f"document_type = ${param_count}")
                params.append(document_type)
                param_count += 1
            
            conditions.append("status = 'completed'")
            where_clause = f"WHERE {' AND '.join(conditions)}"
            params.append(limit)
            
            query = f"""
                SELECT id, filename, created_at, document_type,
                       summary, structured_data, extracted_text
                FROM documents
                {where_clause}
                ORDER BY {order_by}
                LIMIT ${param_count}
            """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            # Parse JSONB fields
            results = []
            for row in rows:
                doc = dict(row)
                if doc.get('structured_data') and isinstance(doc['structured_data'], str):
                    import json
                    try:
                        doc['structured_data'] = json.loads(doc['structured_data'])
                    except (json.JSONDecodeError, TypeError):
                        doc['structured_data'] = {}
                results.append(doc)
            return results
    
    # ==========================================
    # PROMPT OPERATIONS
    # ==========================================
    
    async def get_active_prompt(self, prompt_type: str, document_type: str = None) -> Optional[Dict[str, Any]]:
        """Get active prompt for classification or summarization.
        
        Args:
            prompt_type: 'classifier' or 'summarizer'
            document_type: Document type (required for summarizer, None for classifier)
            
        Returns:
            Prompt dict or None
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, prompt_type, document_type, prompt_text, 
                       version, performance_score, performance_metrics,
                       created_at, updated_at
                FROM prompts 
                WHERE prompt_type = $1 
                  AND (document_type = $2 OR ($2 IS NULL AND document_type IS NULL))
                  AND is_active = true
                ORDER BY version DESC
                LIMIT 1
            """, prompt_type, document_type)
            
            return dict(row) if row else None
    
    async def create_prompt(
        self,
        prompt_id: UUID,
        prompt_type: str,
        prompt_text: str,
        document_type: str = None,
        version: int = 1,
        performance_score: float = None,
        performance_metrics: dict = None
    ) -> UUID:
        """Create a new prompt version.
        
        Args:
            prompt_id: Prompt UUID
            prompt_type: 'classifier' or 'summarizer'
            prompt_text: The prompt content
            document_type: Document type (for summarizers)
            version: Version number
            performance_score: Performance score (0.0 - 1.0)
            performance_metrics: Detailed metrics as dict
            
        Returns:
            Prompt UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO prompts (
                    id, prompt_type, document_type, prompt_text, version,
                    performance_score, performance_metrics, 
                    is_active, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, true, $8, $9)
            """,
                prompt_id, prompt_type, document_type, prompt_text, version,
                performance_score, performance_metrics,
                utc_now(), utc_now()
            )
        
        return prompt_id
    
    async def deactivate_old_prompts(self, prompt_type: str, document_type: str = None):
        """Deactivate old prompt versions (keeps only latest active).
        
        Args:
            prompt_type: 'classifier' or 'summarizer'
            document_type: Document type (for summarizers)
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE prompts
                SET is_active = false, updated_at = $3
                WHERE prompt_type = $1
                  AND (document_type = $2 OR ($2 IS NULL AND document_type IS NULL))
                  AND is_active = true
            """, prompt_type, document_type, utc_now())
    
    async def list_prompts(
        self,
        prompt_type: str = None,
        document_type: str = None,
        include_inactive: bool = False
    ) -> List[Dict[str, Any]]:
        """List prompts with optional filtering.
        
        Args:
            prompt_type: Filter by type
            document_type: Filter by document type
            include_inactive: Include inactive prompts
            
        Returns:
            List of prompt dicts
        """
        await self.initialize()
        
        conditions = []
        params = []
        param_count = 1
        
        if prompt_type:
            conditions.append(f"prompt_type = ${param_count}")
            params.append(prompt_type)
            param_count += 1
        
        if document_type:
            conditions.append(f"document_type = ${param_count}")
            params.append(document_type)
            param_count += 1
        
        if not include_inactive:
            conditions.append("is_active = true")
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        query = f"""
            SELECT id, prompt_type, document_type, prompt_text, version,
                   performance_score, performance_metrics, is_active,
                   created_at, updated_at
            FROM prompts 
            {where_clause}
            ORDER BY prompt_type, document_type, version DESC
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    # ==========================================
    # DOCUMENT TYPE OPERATIONS
    # ==========================================
    
    async def get_document_types(self, active_only: bool = True) -> List[Dict[str, Any]]:
        """Get list of known document types.
        
        Args:
            active_only: Only return active types
            
        Returns:
            List of document type dicts
        """
        await self.initialize()
        
        where_clause = "WHERE is_active = true" if active_only else ""
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT id, type_name, description, is_active, usage_count, created_at
                FROM document_types 
                {where_clause}
                ORDER BY usage_count DESC, type_name
            """)
            
            return [dict(row) for row in rows]
    
    async def create_document_type(
        self,
        type_id: UUID,
        type_name: str,
        description: str = None
    ) -> UUID:
        """Create a new document type.
        
        Args:
            type_id: Type UUID
            type_name: Type name (unique)
            description: Type description
            
        Returns:
            Type UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO document_types (id, type_name, description, is_active, usage_count, created_at)
                VALUES ($1, $2, $3, true, 0, $4)
                ON CONFLICT (type_name) DO NOTHING
            """, type_id, type_name, description, utc_now())
        
        return type_id
    
    async def increment_type_usage(self, type_name: str):
        """Increment usage count for a document type.
        
        Args:
            type_name: Document type name
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE document_types 
                SET usage_count = usage_count + 1
                WHERE type_name = $1
            """, type_name)
    
    # ==========================================
    # CLASSIFICATION SUGGESTION OPERATIONS
    # ==========================================
    
    async def record_classification_suggestion(
        self,
        suggestion_id: UUID,
        suggested_type: str,
        document_id: UUID,
        confidence: float,
        reasoning: str
    ) -> UUID:
        """Record an LLM suggestion for a new document type.
        
        Args:
            suggestion_id: Suggestion UUID
            suggested_type: Suggested type name
            document_id: Document UUID
            confidence: Confidence score
            reasoning: Why this type is suggested
            
        Returns:
            Suggestion UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO classification_suggestions (
                    id, suggested_type, document_id, confidence, reasoning,
                    approved, created_at
                ) VALUES ($1, $2, $3, $4, $5, false, $6)
            """, suggestion_id, suggested_type, document_id, confidence, reasoning, utc_now())
        
        return suggestion_id
    
    # ==========================================
    # FILE OPERATIONS
    # ==========================================
    
    async def add_tag_to_file(self, file_id: UUID, tag_name: str):
        """Add a tag to a file's matching criteria.
        
        Args:
            file_id: File UUID
            tag_name: Tag to add to file
        """
        await self.initialize()
        
        # Find or create tag
        tag_record = await self.find_or_create_tag(tag_name, created_by='system')
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO file_tags (file_id, tag_id)
                VALUES ($1, $2)
                ON CONFLICT (file_id, tag_id) DO NOTHING
            """, file_id, tag_record['id'])
    
    async def get_file_tags(self, file_id: UUID) -> List[str]:
        """Get all tags for a file.
        
        Args:
            file_id: File UUID
            
        Returns:
            List of tag names
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT t.tag_name
                FROM tags t
                INNER JOIN file_tags ft ON t.id = ft.tag_id
                WHERE ft.file_id = $1
                ORDER BY t.tag_name
            """, file_id)
            
            return [row['tag_name'] for row in rows]
    
    async def find_or_create_file(
        self,
        file_id: UUID,
        tags: list[str],
        user_id: str = None
    ) -> Dict[str, Any]:
        """Find existing file or create new one (tag-based).
        
        Args:
            file_id: File UUID to use if creating
            tags: List of tags defining this file
            user_id: User ID for multi-user support
            
        Returns:
            File record dict
        """
        await self.initialize()
        
        # Normalize tags for comparison
        normalized_tags = sorted([self.normalize_tag(tag) for tag in tags])
        
        async with self.pool.acquire() as conn:
            # Try to find existing file with exact same tags
            # This requires checking all files and comparing their tags
            rows = await conn.fetch("""
                SELECT f.id, f.document_count, f.first_document_date, f.last_document_date,
                       f.summary_text, f.summary_metadata, f.prompt_version,
                       f.status, f.created_at, f.updated_at, f.last_generated_at, f.user_id,
                       array_agg(t.tag_normalized ORDER BY t.tag_normalized) as file_tags
                FROM files f
                LEFT JOIN file_tags ft ON f.id = ft.file_id
                LEFT JOIN tags t ON ft.tag_id = t.id
                WHERE f.user_id = $1 OR ($1 IS NULL AND f.user_id IS NULL)
                GROUP BY f.id, f.document_count, f.first_document_date, f.last_document_date,
                         f.summary_text, f.summary_metadata, f.prompt_version,
                         f.status, f.created_at, f.updated_at, f.last_generated_at, f.user_id
            """, user_id)
            
            # Find file with matching tags
            for row in rows:
                file_tags = row['file_tags']
                if file_tags and sorted([t for t in file_tags if t]) == normalized_tags:
                    # Found matching file
                    result = dict(row)
                    result.pop('file_tags')  # Remove temporary field
                    return result
            
            # Create new file
            await conn.execute("""
                INSERT INTO files (
                    id, document_count, status, created_at, updated_at, user_id
                ) VALUES ($1, 0, 'pending', $2, $3, $4)
            """, file_id, utc_now(), utc_now(), user_id)
            
            # Add tags to file
            for tag in tags:
                await self.add_tag_to_file(file_id, tag)
            
            # Fetch and return new file
            row = await conn.fetchrow("""
                SELECT id, document_count, status, created_at, updated_at, user_id
                FROM files
                WHERE id = $1
            """, file_id)
            
            return dict(row)
    
    async def add_document_to_file(self, file_id: UUID, document_id: UUID):
        """Add document to file (if not already present).
        
        Args:
            file_id: File UUID
            document_id: Document UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            # Check if already exists
            exists = await conn.fetchval("""
                SELECT 1 FROM file_documents
                WHERE file_id = $1 AND document_id = $2
            """, file_id, document_id)
            
            if not exists:
                await conn.execute("""
                    INSERT INTO file_documents (file_id, document_id, added_at)
                    VALUES ($1, $2, $3)
                """, file_id, document_id, utc_now())
                
                # Update file document count and dates
                await conn.execute("""
                    UPDATE files
                    SET document_count = document_count + 1,
                        first_document_date = COALESCE(
                            first_document_date,
                            (SELECT created_at FROM documents WHERE id = $2)
                        ),
                        last_document_date = GREATEST(
                            COALESCE(last_document_date, '1970-01-01'::timestamp),
                            (SELECT created_at FROM documents WHERE id = $2)
                        ),
                        updated_at = $3
                    WHERE id = $1
                """, file_id, document_id, utc_now())
    
    async def mark_file_outdated(self, file_id: UUID):
        """Mark file as needing regeneration.
        
        Args:
            file_id: File UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE files
                SET status = 'outdated', updated_at = $2
                WHERE id = $1 AND status = 'generated'
            """, file_id, utc_now())
    
    async def get_file(self, file_id: UUID) -> Optional[Dict[str, Any]]:
        """Get file by ID with tags and document count.
        
        Args:
            file_id: File UUID
            
        Returns:
            File dict or None if not found
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            # Get file
            row = await conn.fetchrow("""
                SELECT f.id, f.first_document_date, f.last_document_date,
                       f.summary_text, f.summary_metadata, f.prompt_version,
                       f.status, f.created_at, f.updated_at, f.last_generated_at, f.user_id
                FROM files f
                WHERE f.id = $1
            """, file_id)
            
            if not row:
                return None
            
            file_dict = dict(row)
            
            # Get tags for this file
            file_dict['tags'] = await self.get_file_tags(file_id)
            
            # Get actual document count
            documents = await self.get_file_documents(file_id)
            file_dict['document_count'] = len(documents)
            
            return file_dict
    
    async def get_files_by_status(self, statuses: list[str], limit: int = 10) -> List[Dict[str, Any]]:
        """Get files with specific statuses.
        
        Args:
            statuses: List of statuses to filter by
            limit: Maximum number of files to return
            
        Returns:
            List of file dicts with tags
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, document_count, status, updated_at, last_generated_at
                FROM files
                WHERE status = ANY($1::text[])
                ORDER BY updated_at ASC
                LIMIT $2
            """, statuses, limit)
            
            # Add tags to each file
            files = []
            for row in rows:
                file_dict = dict(row)
                file_dict['tags'] = await self.get_file_tags(file_dict['id'])
                files.append(file_dict)
            
            return files
    
    async def get_file_documents(
        self,
        file_id: UUID,
        order_by: str = "created_at DESC"
    ) -> List[Dict[str, Any]]:
        """Get all documents matching a file's tags.
        
        This queries ALL documents with tags matching the file's tags,
        enabling dynamic file contents that update automatically.
        
        Args:
            file_id: File UUID
            order_by: SQL ORDER BY clause
            
        Returns:
            List of document dicts with metadata
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            # Get file's tag IDs from file_tags junction table
            tag_rows = await conn.fetch("""
                SELECT tag_id FROM file_tags WHERE file_id = $1
            """, file_id)
            
            if not tag_rows:
                return []
            
            tag_ids = [row['tag_id'] for row in tag_rows]
            
            # Get documents that have ALL of these tags
            # Count how many of the file's tags each document has
            rows = await conn.fetch("""
                SELECT DISTINCT d.id, d.filename, d.created_at, d.document_type,
                       d.summary, d.structured_data
                FROM documents d
                WHERE d.status = 'completed'
                  AND (
                    SELECT COUNT(DISTINCT dt.tag_id)
                    FROM document_tags dt
                    WHERE dt.document_id = d.id
                      AND dt.tag_id = ANY($1::uuid[])
                  ) = $2
                ORDER BY d.{order_by}
            """.format(order_by=order_by), tag_ids, len(tag_ids))
            
            # Parse JSONB fields and fetch tags for each document
            results = []
            for row in rows:
                doc = dict(row)
                
                # Fetch tags for this document
                doc['tags'] = await self.get_document_tags(doc['id'])
                
                # Parse structured_data
                if doc.get('structured_data') and isinstance(doc['structured_data'], str):
                    import json
                    try:
                        doc['structured_data'] = json.loads(doc['structured_data'])
                    except (json.JSONDecodeError, TypeError):
                        doc['structured_data'] = {}
                
                results.append(doc)
            
            return results
    
    async def get_document_tags(self, document_id: UUID) -> List[str]:
        """Get all tags for a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of tag names
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT t.tag_name
                FROM tags t
                INNER JOIN document_tags dt ON t.id = dt.tag_id
                WHERE dt.document_id = $1
                ORDER BY t.tag_name
            """, document_id)
            
            return [row['tag_name'] for row in rows]
    
    async def add_tag_to_document(self, document_id: UUID, tag_name: str, created_by: str = 'user'):
        """Add a tag to a document.
        
        Args:
            document_id: Document UUID
            tag_name: Tag to add
            created_by: Source of tag ('user', 'llm', 'system')
        """
        await self.initialize()
        
        import logging
        logger = logging.getLogger(__name__)
        
        # Find or create tag
        tag_record = await self.find_or_create_tag(tag_name, created_by)
        
        # Ensure UUIDs are proper UUID objects
        from uuid import UUID as UUIDType
        if isinstance(document_id, str):
            document_id = UUIDType(document_id)
        
        tag_id = tag_record['id']
        if isinstance(tag_id, str):
            tag_id = UUIDType(tag_id)
        
        logger.info(f"Adding tag '{tag_name}' to document {document_id} (tag_id={tag_id})")
        
        # Add to document_tags junction table
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO document_tags (document_id, tag_id)
                VALUES ($1::uuid, $2::uuid)
                ON CONFLICT (document_id, tag_id) DO NOTHING
            """, str(document_id), str(tag_id))
        
        # Increment tag usage
        await self.increment_tag_usage(self.normalize_tag(tag_name))
        
        # Note: File invalidation is handled automatically by database trigger
        # See schema.sql: document_tags_invalidate_files trigger
    
    async def update_file(self, file_id: UUID, **fields):
        """Update file fields.
        
        Args:
            file_id: File UUID
            **fields: Fields to update (key=value pairs)
        """
        await self.initialize()
        
        if not fields:
            return
        
        import json
        
        # JSONB fields that need JSON serialization
        jsonb_fields = {'summary_metadata'}
        
        # Serialize JSONB fields
        values = []
        for key, value in fields.items():
            if key in jsonb_fields and value is not None and not isinstance(value, str):
                values.append(json.dumps(value))
            else:
                values.append(value)
        
        # Build dynamic UPDATE query
        set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(fields.keys())]
        set_clause = ", ".join(set_clauses)
        
        query = f"""
            UPDATE files
            SET {set_clause}, updated_at = ${len(values) + 2}
            WHERE id = $1
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, file_id, *values, utc_now())
    
    async def list_files(
        self,
        limit: int = 50,
        offset: int = 0,
        tags: list[str] = None,
        status: str = None,
        user_id: str = None
    ) -> List[Dict[str, Any]]:
        """List files with optional filtering.
        
        Args:
            limit: Maximum number of files
            offset: Pagination offset
            tags: Filter by tags (files must have all specified tags)
            status: Filter by status
            user_id: Filter by user
            
        Returns:
            List of file dicts with tags
        """
        await self.initialize()
        
        conditions = []
        params = []
        param_count = 1
        
        # Tag filtering requires JOIN with file_tags
        if tags:
            # Normalize tags
            normalized_tags = [self.normalize_tag(tag) for tag in tags]
            
            # Need to get tag IDs first
            async with self.pool.acquire() as conn:
                tag_id_rows = await conn.fetch("""
                    SELECT id FROM tags WHERE tag_normalized = ANY($1::text[])
                """, normalized_tags)
                
                if len(tag_id_rows) != len(normalized_tags):
                    # Some tags don't exist, no files will match
                    return []
                
                tag_ids = [row['id'] for row in tag_id_rows]
            
            # Filter files that have ALL these tag IDs
            conditions.append(f"""
                (SELECT COUNT(DISTINCT ft.tag_id) FROM file_tags ft
                 WHERE ft.file_id = f.id AND ft.tag_id = ANY(${param_count}::uuid[]))
                = ${param_count + 1}
            """)
            params.extend([tag_ids, len(tag_ids)])
            param_count += 2
        
        if status:
            conditions.append(f"f.status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if user_id is not None:
            conditions.append(f"(f.user_id = ${param_count} OR (${param_count} IS NULL AND f.user_id IS NULL))")
            params.append(user_id)
            param_count += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        params.extend([limit, offset])
        
        query = f"""
            SELECT f.id, f.first_document_date, f.last_document_date,
                   f.summary_text, f.status, f.created_at, f.updated_at
            FROM files f
            {where_clause}
            ORDER BY f.updated_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            files = []
            
            # Add tags and document count for each file
            for row in rows:
                file_dict = dict(row)
                file_dict['tags'] = await self.get_file_tags(file_dict['id'])
                documents = await self.get_file_documents(file_dict['id'])
                file_dict['document_count'] = len(documents)
                files.append(file_dict)
            
            return files
    
    async def delete_file(self, file_id: UUID):
        """Delete file (cascade deletes file_documents).
        
        Args:
            file_id: File UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM files WHERE id = $1", file_id)
    
    # ==========================================
    # SERIES OPERATIONS
    # ==========================================
    
    async def create_series(
        self,
        series_id: UUID,
        title: str,
        entity: str,
        series_type: str,
        frequency: str = None,
        description: str = None,
        metadata: dict = None,
        user_id: str = None,
        source: str = 'llm'
    ) -> UUID:
        """Create a new series.
        
        Args:
            series_id: Series UUID
            title: Human-readable series title
            entity: Entity name (e.g., "State Farm Insurance")
            series_type: Series type (e.g., "monthly_insurance_bill")
            frequency: Recurrence frequency (monthly, quarterly, annual, etc.)
            description: LLM-generated description
            metadata: Structured metadata as dict
            user_id: User ID for multi-user support
            source: 'llm' or 'user'
            
        Returns:
            Series UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO series (
                    id, title, entity, series_type, frequency,
                    description, metadata, status, user_id, source,
                    document_count, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, 'active', $8, $9, 0, $10, $11)
                ON CONFLICT (entity, series_type, user_id) DO NOTHING
            """,
                series_id, title, entity, series_type, frequency,
                description, metadata, user_id, source,
                utc_now(), utc_now()
            )
        
        return series_id
    
    async def find_or_create_series(
        self,
        series_id: UUID,
        entity: str,
        series_type: str,
        title: str,
        frequency: str = None,
        description: str = None,
        metadata: dict = None,
        user_id: str = None
    ) -> Dict[str, Any]:
        """Find existing series or create new one.
        
        Args:
            series_id: Series UUID to use if creating
            entity: Entity name
            series_type: Series type
            title: Series title
            frequency: Recurrence frequency
            description: Description
            metadata: Metadata dict
            user_id: User ID
            
        Returns:
            Series record dict
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            # Try to find existing series
            row = await conn.fetchrow("""
                SELECT id, title, entity, series_type, frequency,
                       description, metadata, document_count,
                       first_document_date, last_document_date,
                       expected_frequency_days, summary_text, summary_metadata,
                       status, user_id, source, created_at, updated_at, last_generated_at
                FROM series
                WHERE entity = $1 AND series_type = $2
                  AND (user_id = $3 OR ($3 IS NULL AND user_id IS NULL))
            """, entity, series_type, user_id)
            
            if row:
                return dict(row)
            
            # Create new series
            await self.create_series(
                series_id, title, entity, series_type, frequency,
                description, metadata, user_id
            )
            
            # Fetch and return new series
            row = await conn.fetchrow("""
                SELECT id, title, entity, series_type, frequency,
                       description, metadata, document_count,
                       status, user_id, source, created_at, updated_at
                FROM series
                WHERE id = $1
            """, series_id)
            
            return dict(row)
    
    async def get_series(self, series_id: UUID) -> Optional[Dict[str, Any]]:
        """Get series by ID.
        
        Args:
            series_id: Series UUID
            
        Returns:
            Series dict or None if not found
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, title, entity, series_type, frequency,
                       description, metadata, document_count,
                       first_document_date, last_document_date,
                       expected_frequency_days, summary_text, summary_metadata,
                       status, user_id, source, created_at, updated_at, last_generated_at
                FROM series
                WHERE id = $1
            """, series_id)
            
            return dict(row) if row else None
    
    async def list_series(
        self,
        limit: int = 50,
        offset: int = 0,
        entity: str = None,
        series_type: str = None,
        frequency: str = None,
        status: str = None,
        user_id: str = None
    ) -> List[Dict[str, Any]]:
        """List series with optional filtering.
        
        Args:
            limit: Maximum number of series
            offset: Pagination offset
            entity: Filter by entity name
            series_type: Filter by series type
            frequency: Filter by frequency
            status: Filter by status
            user_id: Filter by user
            
        Returns:
            List of series dicts
        """
        await self.initialize()
        
        conditions = []
        params = []
        param_count = 1
        
        if entity:
            conditions.append(f"entity = ${param_count}")
            params.append(entity)
            param_count += 1
        
        if series_type:
            conditions.append(f"series_type = ${param_count}")
            params.append(series_type)
            param_count += 1
        
        if frequency:
            conditions.append(f"frequency = ${param_count}")
            params.append(frequency)
            param_count += 1
        
        if status:
            conditions.append(f"status = ${param_count}")
            params.append(status)
            param_count += 1
        
        if user_id is not None:
            conditions.append(f"(user_id = ${param_count} OR (${param_count} IS NULL AND user_id IS NULL))")
            params.append(user_id)
            param_count += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        params.extend([limit, offset])
        
        query = f"""
            SELECT id, title, entity, series_type, frequency,
                   description, metadata, document_count,
                   first_document_date, last_document_date,
                   status, created_at, updated_at
            FROM series
            {where_clause}
            ORDER BY last_document_date DESC NULLS LAST, updated_at DESC
            LIMIT ${param_count} OFFSET ${param_count + 1}
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, *params)
            return [dict(row) for row in rows]
    
    async def update_series(self, series_id: UUID, **fields):
        """Update series fields.
        
        Args:
            series_id: Series UUID
            **fields: Fields to update (key=value pairs)
        """
        await self.initialize()
        
        if not fields:
            return
        
        import json
        
        # JSONB fields that need JSON serialization
        jsonb_fields = {'metadata', 'summary_metadata'}
        
        # Serialize JSONB fields
        values = []
        for key, value in fields.items():
            if key in jsonb_fields and value is not None and not isinstance(value, str):
                values.append(json.dumps(value))
            else:
                values.append(value)
        
        # Build dynamic UPDATE query
        set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(fields.keys())]
        set_clause = ", ".join(set_clauses)
        
        query = f"""
            UPDATE series
            SET {set_clause}, updated_at = ${len(values) + 2}
            WHERE id = $1
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, series_id, *values, utc_now())
    
    async def add_document_to_series(
        self,
        series_id: UUID,
        document_id: UUID,
        added_by: str = 'llm'
    ):
        """Add document to series.
        
        Args:
            series_id: Series UUID
            document_id: Document UUID
            added_by: 'llm' or 'user'
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            # Check if already exists
            exists = await conn.fetchval("""
                SELECT 1 FROM document_series
                WHERE document_id = $1 AND series_id = $2
            """, document_id, series_id)
            
            if not exists:
                await conn.execute("""
                    INSERT INTO document_series (document_id, series_id, added_at, added_by)
                    VALUES ($1, $2, $3, $4)
                """, document_id, series_id, utc_now(), added_by)
    
    async def get_series_documents(
        self,
        series_id: UUID,
        order_by: str = "created_at ASC"
    ) -> List[Dict[str, Any]]:
        """Get all documents in a series.
        
        Args:
            series_id: Series UUID
            order_by: SQL ORDER BY clause
            
        Returns:
            List of document dicts
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(f"""
                SELECT d.id, d.filename, d.created_at, d.document_type,
                       d.summary, d.structured_data, ds.added_at, ds.added_by
                FROM documents d
                INNER JOIN document_series ds ON d.id = ds.document_id
                WHERE ds.series_id = $1
                ORDER BY d.{order_by}
            """, series_id)
            
            # Parse JSONB fields
            results = []
            for row in rows:
                doc = dict(row)
                if doc.get('structured_data') and isinstance(doc['structured_data'], str):
                    import json
                    try:
                        doc['structured_data'] = json.loads(doc['structured_data'])
                    except (json.JSONDecodeError, TypeError):
                        doc['structured_data'] = {}
                results.append(doc)
            
            return results
    
    async def delete_series(self, series_id: UUID):
        """Delete series (cascade deletes document_series).
        
        Args:
            series_id: Series UUID
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM series WHERE id = $1", series_id)
    
    # ==========================================
    # UTILITY OPERATIONS
    # ==========================================
    
    async def get_stats(self) -> Dict[str, Any]:
        """Get database statistics.
        
        Returns:
            Dict with counts and stats
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            total_docs = await conn.fetchval("SELECT COUNT(*) FROM documents")
            by_status = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM documents
                GROUP BY status
            """)
            by_type = await conn.fetch("""
                SELECT document_type, COUNT(*) as count
                FROM documents
                WHERE document_type IS NOT NULL
                GROUP BY document_type
            """)
            
            # File statistics
            total_files = await conn.fetchval("SELECT COUNT(*) FROM files")
            files_by_status = await conn.fetch("""
                SELECT status, COUNT(*) as count
                FROM files
                GROUP BY status
            """)
            
            return {
                "total_documents": total_docs,
                "by_status": {row['status']: row['count'] for row in by_status},
                "by_type": {row['document_type']: row['count'] for row in by_type},
                "total_files": total_files,
                "files_by_status": {row['status']: row['count'] for row in files_by_status}
            }
    
    # ==========================================
    # TAG OPERATIONS
    # ==========================================
    
    def normalize_tag(self, tag: str) -> str:
        """Normalize a tag to lowercase, trimmed format.
        
        Args:
            tag: Tag string to normalize
            
        Returns:
            Normalized tag string
        """
        return tag.lower().strip()
    
    async def find_or_create_tag(
        self,
        tag: str,
        created_by: str = 'system',
        category: str = None
    ) -> Dict[str, Any]:
        """Find existing tag or create new one.
        
        Args:
            tag: Tag name
            created_by: Source ('user', 'llm', or 'system')
            category: Optional category
            
        Returns:
            Tag record dict
        """
        await self.initialize()
        
        tag_normalized = self.normalize_tag(tag)
        
        async with self.pool.acquire() as conn:
            # Try to find existing tag
            row = await conn.fetchrow("""
                SELECT id, tag_name, tag_normalized, usage_count,
                       created_by, category, first_used, last_used
                FROM tags
                WHERE tag_normalized = $1
            """, tag_normalized)
            
            if row:
                return dict(row)
            
            # Create new tag
            tag_id = uuid4()
            await conn.execute("""
                INSERT INTO tags (
                    id, tag_name, tag_normalized, usage_count,
                    created_by, category, first_used, last_used,
                    created_at, updated_at
                ) VALUES ($1, $2, $3, 0, $4, $5, $6, $7, $8, $9)
            """, tag_id, tag, tag_normalized, created_by, category,
                utc_now(), utc_now(), utc_now(), utc_now())
            
            # Fetch and return new tag
            row = await conn.fetchrow("""
                SELECT id, tag_name, tag_normalized, usage_count,
                       created_by, category, first_used, last_used
                FROM tags
                WHERE id = $1
            """, tag_id)
            
            return dict(row)
    
    async def increment_tag_usage(self, tag_normalized: str):
        """Increment usage count and update last_used for a tag.
        
        Args:
            tag_normalized: Normalized tag name
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE tags
                SET usage_count = usage_count + 1,
                    last_used = $2
                WHERE tag_normalized = $1
            """, tag_normalized, utc_now())
    
    async def get_all_tags(
        self,
        limit: int = 100,
        order_by: str = "usage_count DESC"
    ) -> List[Dict[str, Any]]:
        """Get all tags with optional ordering.
        
        Args:
            limit: Maximum number of tags to return
            order_by: SQL ORDER BY clause
            
        Returns:
            List of tag dicts
        """
        await self.initialize()
        
        query = f"""
            SELECT tag_name, tag_normalized, usage_count,
                   created_by, category, first_used, last_used
            FROM tags
            ORDER BY {order_by}
            LIMIT $1
        """
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(query, limit)
            return [dict(row) for row in rows]
    
    async def get_popular_tags(self, limit: int = 20) -> List[str]:
        """Get most popular tag names for suggestions.
        
        Args:
            limit: Maximum number of tags to return
            
        Returns:
            List of tag names (original casing)
        """
        await self.initialize()
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tag_name
                FROM tags
                WHERE usage_count > 0
                ORDER BY usage_count DESC, last_used DESC
                LIMIT $1
            """, limit)
            
            return [row['tag_name'] for row in rows]
    
    async def search_tags(self, query: str, limit: int = 10) -> List[str]:
        """Search for tags matching a query.
        
        Args:
            query: Search query
            limit: Maximum results
            
        Returns:
            List of matching tag names
        """
        await self.initialize()
        
        query_normalized = self.normalize_tag(query)
        
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT tag_name
                FROM tags
                WHERE tag_normalized LIKE $1
                ORDER BY usage_count DESC
                LIMIT $2
            """, f"%{query_normalized}%", limit)
            
            return [row['tag_name'] for row in rows]
    
    async def merge_tags_from_document(
        self,
        user_tags: List[str],
        llm_tags: List[str]
    ) -> List[str]:
        """Merge user-provided and LLM-generated tags, creating tag records.
        
        Args:
            user_tags: Tags from user input
            llm_tags: Tags from LLM classification
            
        Returns:
            Merged list of unique tags
        """
        await self.initialize()
        
        # Normalize and deduplicate
        all_tags = set()
        tag_mapping = {}  # normalized -> original
        
        # Add user tags
        for tag in user_tags:
            normalized = self.normalize_tag(tag)
            if normalized and normalized not in all_tags:
                all_tags.add(normalized)
                tag_mapping[normalized] = tag
        
        # Add LLM tags
        for tag in llm_tags:
            normalized = self.normalize_tag(tag)
            if normalized and normalized not in all_tags:
                all_tags.add(normalized)
                tag_mapping[normalized] = tag
        
        # Create/update tag records and increment usage
        final_tags = []
        for normalized in all_tags:
            original = tag_mapping[normalized]
            created_by = 'user' if original in user_tags else 'llm'
            
            # Find or create tag
            tag_record = await self.find_or_create_tag(original, created_by)
            
            # Increment usage
            await self.increment_tag_usage(normalized)
            
            # Use the canonical tag name from database
            final_tags.append(tag_record['tag_name'])
        
        return final_tags