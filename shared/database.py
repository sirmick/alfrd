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
        """Initialize the connection pool."""
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                dsn=self.database_url,
                min_size=self.pool_min_size,
                max_size=self.pool_max_size,
                timeout=self.pool_timeout,
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
                       document_type, suggested_type, secondary_tags,
                       classification_confidence, classification_reasoning,
                       category, subcategory, confidence,
                       vendor, amount, currency, due_date, issue_date,
                       raw_document_path, extracted_text_path, metadata_path, folder_path,
                       created_at, updated_at, user_id,
                       extracted_text, summary, structured_data, tags, folder_metadata
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
        
        # Build dynamic UPDATE query
        set_clauses = [f"{key} = ${i+2}" for i, key in enumerate(fields.keys())]
        set_clause = ", ".join(set_clauses)
        values = list(fields.values())
        
        query = f"""
            UPDATE documents
            SET {set_clause}, updated_at = ${len(values) + 2}
            WHERE id = $1
        """
        
        async with self.pool.acquire() as conn:
            await conn.execute(query, doc_id, *values, utc_now())
    
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
                       classification_confidence, classification_reasoning, secondary_tags,
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
                secondary_tags,
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
            return [dict(row) for row in rows]
    
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
                WHERE id = $1
            """, doc_id)
            
            return dict(row) if row else None
    
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
                       created_at, summary,
                       ts_rank(extracted_text_tsv, to_tsquery($1)) as rank
                FROM documents 
                WHERE extracted_text_tsv @@ to_tsquery($1)
                ORDER BY rank DESC
                LIMIT $2
            """, query, limit)
            
            return [dict(row) for row in rows]
    
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
            
            return {
                "total_documents": total_docs,
                "by_status": {row['status']: row['count'] for row in by_status},
                "by_type": {row['document_type']: row['count'] for row in by_type}
            }