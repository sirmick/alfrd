"""Unified AWS client manager with request caching.

This module provides a single source of truth for AWS API access with:
- Singleton boto3 clients (Bedrock, Textract)
- Request caching to avoid duplicate API calls (saves money!)
- Standardized credential handling
- Cost tracking and logging

Usage:
    from shared.aws_clients import AWSClientManager
    
    aws = AWSClientManager()
    
    # Bedrock LLM calls (with caching)
    response = aws.invoke_bedrock(
        system="You are helpful",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0
    )
    
    # Textract OCR (with caching)
    result = await aws.extract_text_textract(image_bytes)
"""

import hashlib
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path
import boto3
from botocore.exceptions import ClientError

from shared.config import Settings

logger = logging.getLogger(__name__)


class RequestCache:
    """Disk-based cache for AWS API requests.
    
    Uses content-based hashing (SHA256) to detect identical requests.
    Saves responses to disk as JSON files for persistence across restarts.
    Saves money by avoiding duplicate Bedrock/Textract calls during testing.
    """
    
    def __init__(self, cache_dir: Path = None, max_size: int = 1000):
        # Set up cache directory
        if cache_dir is None:
            from shared.config import Settings
            settings = Settings()
            cache_dir = settings.documents_path.parent / "cache"
        
        self._cache_dir = Path(cache_dir)
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        
        self._max_size = max_size
        self._hits = 0
        self._misses = 0
        
        logger.info(f"AWS cache initialized at: {self._cache_dir}")
    
    def _hash_request(self, request_type: str, **kwargs) -> str:
        """Generate cache key from request parameters."""
        # Create deterministic string representation
        cache_data = {
            'type': request_type,
            **kwargs
        }
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_str.encode()).hexdigest()
    
    def get(self, request_type: str, **kwargs) -> Optional[Any]:
        """Get cached response from disk if available."""
        cache_key = self._hash_request(request_type, **kwargs)
        cache_file = self._cache_dir / f"{cache_key}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    cached_data = json.load(f)
                
                self._hits += 1
                # Structured cache logging only (no console spam)
                from shared.logging_config import log_cache_operation
                log_cache_operation('hit', request_type, cache_key)
                
                return cached_data
            except Exception as e:
                logger.debug(f"Cache read failed {cache_key[:8]}: {e}")
                
                # Structured error logging
                from shared.logging_config import log_cache_operation
                log_cache_operation('error', request_type, cache_key,
                                  details={'error': str(e), 'action': 'deleting_corrupt_file'})
                
                # Delete corrupted cache file
                cache_file.unlink(missing_ok=True)
        
        self._misses += 1
        # Structured cache logging only (no console spam)
        from shared.logging_config import log_cache_operation
        log_cache_operation('miss', request_type, cache_key)
        
        return None
    
    def set(self, response: Any, request_type: str, **kwargs) -> None:
        """Cache a response to disk."""
        cache_key = self._hash_request(request_type, **kwargs)
        cache_file = self._cache_dir / f"{cache_key}.json"
        debug_file = self._cache_dir / f"{cache_key}.debug.json"
        
        try:
            # Check if we need to prune old cache files
            cache_files = sorted(self._cache_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
            if len(cache_files) >= self._max_size:
                # Remove oldest files
                files_to_remove = cache_files[:len(cache_files) - self._max_size + 1]
                for old_file in files_to_remove:
                    old_file.unlink(missing_ok=True)
                    # Also remove debug file if it exists
                    debug_path = old_file.parent / f"{old_file.stem}.debug.json"
                    debug_path.unlink(missing_ok=True)
                    logger.debug(f"Pruned old cache file: {old_file.name}")
            
            # Write cache file
            with open(cache_file, 'w') as f:
                json.dump(response, f, indent=2)
            
            # Write debug file with request parameters (for debugging cache key mismatches)
            with open(debug_file, 'w') as f:
                debug_data = {
                    'cache_key': cache_key,
                    'request_type': request_type,
                    'parameters': kwargs
                }
                json.dump(debug_data, f, indent=2)
            
            # Structured cache logging only (no console spam)
            from shared.logging_config import log_cache_operation
            log_cache_operation('save', request_type, cache_key,
                              details={'file_size': len(str(response))})
            
        except Exception as e:
            logger.debug(f"Cache save failed for {request_type}: {e}")
            
            # Structured error logging
            from shared.logging_config import log_cache_operation
            log_cache_operation('error', request_type, cache_key,
                              details={'error': str(e), 'action': 'cache_save_failed'})
    
    def clear(self) -> None:
        """Clear all cached responses from disk."""
        cache_files = list(self._cache_dir.glob("*.json"))
        for cache_file in cache_files:
            cache_file.unlink(missing_ok=True)
        
        self._hits = 0
        self._misses = 0
        logger.info(f"Request cache cleared ({len(cache_files)} files deleted from {self._cache_dir})")
    
    def stats(self) -> Dict[str, int]:
        """Get cache statistics."""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        # Count actual cache files on disk
        cache_files = list(self._cache_dir.glob("*.json"))
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'total_requests': total,
            'hit_rate_percent': round(hit_rate, 2),
            'cached_items': len(cache_files),
            'cache_dir': str(self._cache_dir)
        }


class AWSClientManager:
    """Unified AWS client manager with caching.
    
    Singleton pattern - only one set of boto3 clients created per process.
    All AWS API calls should go through this manager.
    """
    
    _instance = None
    _initialized = False
    
    def __new__(cls, *args, **kwargs):
        """Singleton pattern."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(
        self,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
        enable_cache: Optional[bool] = None,
        cache_size: Optional[int] = None
    ):
        """Initialize AWS clients (only once due to singleton).
        
        Args:
            aws_access_key_id: AWS access key (uses Settings if not provided)
            aws_secret_access_key: AWS secret key (uses Settings if not provided)
            aws_region: AWS region (uses Settings if not provided)
            enable_cache: Enable request caching (uses Settings if not provided)
            cache_size: Maximum number of cached responses (uses Settings if not provided)
        """
        # Only initialize once
        if self._initialized:
            return
        
        settings = Settings()
        
        # Store configuration (use settings as fallback)
        self.aws_access_key_id = aws_access_key_id or settings.aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key or settings.aws_secret_access_key
        self.aws_region = aws_region or settings.aws_region
        self.bedrock_model_id = settings.bedrock_model_id
        self.bedrock_max_tokens = settings.bedrock_max_tokens
        
        # Cache configuration from settings
        if enable_cache is None:
            enable_cache = settings.aws_cache_enabled
        if cache_size is None:
            cache_size = settings.aws_cache_max_size
        
        # Build session kwargs
        session_kwargs = {}
        if self.aws_access_key_id and self.aws_secret_access_key:
            session_kwargs['aws_access_key_id'] = self.aws_access_key_id
            session_kwargs['aws_secret_access_key'] = self.aws_secret_access_key
        
        # Create boto3 clients (singleton - reused across all calls)
        logger.info(f"Initializing AWS clients (region: {self.aws_region})")
        
        self._bedrock_client = boto3.client(
            'bedrock-runtime',
            region_name=self.aws_region,
            **session_kwargs
        )
        
        self._textract_client = boto3.client(
            'textract',
            region_name=self.aws_region,
            **session_kwargs
        )
        
        # Initialize cache (using config settings)
        self._cache_enabled = enable_cache
        self._cache = RequestCache(max_size=cache_size) if enable_cache else None
        
        # Cost tracking
        self._total_bedrock_input_tokens = 0
        self._total_bedrock_output_tokens = 0
        self._total_textract_pages = 0
        
        self._initialized = True
        logger.info(
            f"AWS clients initialized (Bedrock model: {self.bedrock_model_id}, "
            f"Cache: {'enabled' if enable_cache else 'disabled'})"
        )
    
    # =========================================================================
    # BEDROCK LLM
    # =========================================================================
    
    def invoke_bedrock(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        model_id: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Invoke Bedrock model with caching.
        
        Args:
            system: System prompt
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Override default max tokens
            model_id: Override default model ID
            use_cache: Use cache if available (default: True)
            
        Returns:
            Dict with:
                - content: Response text
                - stop_reason: Reason for stopping
                - usage: Token usage info
                - model_id: Model that was invoked
                - cached: Whether response was from cache
        """
        model_id = model_id or self.bedrock_model_id
        max_tokens = max_tokens or self.bedrock_max_tokens
        
        # Check cache first
        if use_cache and self._cache_enabled:
            cached = self._cache.get(
                'bedrock',
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                model_id=model_id
            )
            if cached:
                cached['cached'] = True
                return cached
        
        # Detect model type and build request
        is_claude = 'anthropic' in model_id.lower() or 'claude' in model_id.lower()
        is_nova = 'amazon' in model_id.lower() and 'nova' in model_id.lower()
        
        if is_claude:
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "system": system,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        elif is_nova:
            # Amazon Nova format
            combined_prompt = f"{system}\n\n{messages[0]['content']}"
            request_body = {
                "messages": [
                    {
                        "role": "user",
                        "content": [{"text": combined_prompt}]
                    }
                ],
                "inferenceConfig": {
                    "temperature": temperature,
                    "maxTokens": max_tokens,
                }
            }
        else:
            # Default to Claude format
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "system": system,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        
        try:
            logger.debug(f"Invoking Bedrock model {model_id}")
            
            response = self._bedrock_client.invoke_model(
                modelId=model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json',
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Extract content (handle both Claude and Nova formats)
            content = ""
            if is_nova:
                if 'output' in response_body and 'message' in response_body['output']:
                    msg_content = response_body['output']['message'].get('content', [])
                    if len(msg_content) > 0:
                        content = msg_content[0].get('text', '')
            else:
                if 'content' in response_body and len(response_body['content']) > 0:
                    content = response_body['content'][0].get('text', '')
            
            # Extract usage and stop reason
            if is_nova:
                usage = response_body.get('usage', {})
                stop_reason = response_body.get('stopReason', 'unknown')
            else:
                usage = response_body.get('usage', {})
                stop_reason = response_body.get('stop_reason', 'unknown')
            
            result = {
                'content': content,
                'stop_reason': stop_reason,
                'usage': usage,
                'model_id': model_id,
                'cached': False
            }
            
            # Track costs
            self._total_bedrock_input_tokens += usage.get('input_tokens', 0)
            self._total_bedrock_output_tokens += usage.get('output_tokens', 0)
            
            # Structured AWS usage logging (no console spam)
            logger.debug(f"Bedrock {model_id}: {usage.get('input_tokens', 0)}in/{usage.get('output_tokens', 0)}out tokens")
            
            # Cache the result
            if use_cache and self._cache_enabled:
                self._cache.set(
                    result,
                    'bedrock',
                    system=system,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    model_id=model_id
                )
            
            return result
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Bedrock API error: {error_code} - {error_message}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error invoking Bedrock: {str(e)}")
            raise
    
    def invoke_bedrock_simple(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> str:
        """Convenience method for simple system + user message invocation.
        
        Args:
            system: System prompt
            user_message: User message content
            temperature: Sampling temperature (0-1)
            max_tokens: Override default max tokens
            use_cache: Use cache if available
            
        Returns:
            Response text content
        """
        messages = [{"role": "user", "content": user_message}]
        
        result = self.invoke_bedrock(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            use_cache=use_cache
        )
        
        return result['content']
    
    # =========================================================================
    # TEXTRACT OCR
    # =========================================================================
    
    async def extract_text_textract(
        self,
        image_bytes: bytes,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Extract text from image using AWS Textract with caching.
        
        Args:
            image_bytes: Image file bytes
            use_cache: Use cache if available (default: True)
            
        Returns:
            Dictionary containing:
                - extracted_text: str - The extracted text content
                - confidence: float - Average confidence score (0-1)
                - blocks: dict - Block-level data by type
                - metadata: dict - Additional metadata
                - cached: bool - Whether response was from cache
        """
        # Check cache first (hash the image bytes)
        if use_cache and self._cache_enabled:
            image_hash = hashlib.sha256(image_bytes).hexdigest()
            cached = self._cache.get('textract', image_hash=image_hash)
            if cached:
                cached['cached'] = True
                logger.debug("Textract cache hit")
                return cached
        
        try:
            # Call Textract
            response = self._textract_client.detect_document_text(
                Document={'Bytes': image_bytes}
            )
            
            # Parse response blocks
            lines = []
            blocks_by_type = {'PAGE': [], 'LINE': [], 'WORD': []}
            total_confidence = 0
            line_count = 0
            word_count = 0
            
            for block in response['Blocks']:
                block_type = block['BlockType']
                
                # Store block information
                block_info = {
                    'id': block.get('Id'),
                    'type': block_type,
                    'text': block.get('Text', ''),
                    'confidence': block.get('Confidence', 0),
                    'geometry': block.get('Geometry', {})
                }
                
                if block_type in blocks_by_type:
                    blocks_by_type[block_type].append(block_info)
                
                # Collect lines for text extraction
                if block_type == 'LINE':
                    lines.append(block['Text'])
                    total_confidence += block.get('Confidence', 0)
                    line_count += 1
                elif block_type == 'WORD':
                    word_count += 1
            
            # Join lines into full text
            extracted_text = '\n'.join(lines)
            
            # Calculate average confidence (convert from 0-100 to 0-1)
            avg_confidence = (total_confidence / line_count / 100) if line_count > 0 else 0
            
            # Get document metadata
            doc_metadata = response.get('DocumentMetadata', {})
            
            result = {
                'extracted_text': extracted_text,
                'confidence': avg_confidence,
                'blocks': blocks_by_type,
                'metadata': {
                    'extractor': 'aws_textract',
                    'pages': doc_metadata.get('Pages', 1),
                    'blocks_total': len(response['Blocks']),
                    'lines_detected': line_count,
                    'words_detected': word_count,
                    'file_size': len(image_bytes)
                },
                'cached': False
            }
            
            # Track costs
            self._total_textract_pages += doc_metadata.get('Pages', 1)
            
            # Structured AWS usage logging (no console spam)
            logger.debug(f"Textract: {line_count} lines, {avg_confidence:.2%} confidence, {doc_metadata.get('Pages', 1)} page(s)")
            
            # Cache the result
            if use_cache and self._cache_enabled:
                image_hash = hashlib.sha256(image_bytes).hexdigest()
                self._cache.set(result, 'textract', image_hash=image_hash)
            
            return result
            
        except ClientError as e:
            error_code = e.response['Error']['Code']
            error_message = e.response['Error']['Message']
            logger.error(f"Textract API error: {error_code} - {error_message}")
            raise RuntimeError(f"AWS Textract error: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error in Textract: {str(e)}")
            raise RuntimeError(f"Failed to extract text from image: {e}") from e
    
    # =========================================================================
    # CACHE MANAGEMENT
    # =========================================================================
    
    def clear_cache(self) -> None:
        """Clear all cached responses."""
        if self._cache:
            self._cache.clear()
            logger.info("AWS request cache cleared")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        if not self._cache:
            return {'cache_enabled': False}
        
        stats = self._cache.stats()
        stats['cache_enabled'] = True
        return stats
    
    # =========================================================================
    # COST TRACKING
    # =========================================================================
    
    def get_cost_stats(self) -> Dict[str, Any]:
        """Get approximate cost statistics.
        
        Returns:
            Dict with cost estimates and usage stats
        """
        # Rough cost estimates (as of 2024):
        # - Textract: $1.50 per 1000 pages
        # - Nova Lite: ~$0.00006/1K input tokens, ~$0.00024/1K output tokens
        
        textract_cost = (self._total_textract_pages / 1000) * 1.50
        bedrock_input_cost = (self._total_bedrock_input_tokens / 1000) * 0.00006
        bedrock_output_cost = (self._total_bedrock_output_tokens / 1000) * 0.00024
        bedrock_total_cost = bedrock_input_cost + bedrock_output_cost
        
        total_cost = textract_cost + bedrock_total_cost
        
        return {
            'textract': {
                'pages_processed': self._total_textract_pages,
                'estimated_cost_usd': round(textract_cost, 4)
            },
            'bedrock': {
                'input_tokens': self._total_bedrock_input_tokens,
                'output_tokens': self._total_bedrock_output_tokens,
                'total_tokens': self._total_bedrock_input_tokens + self._total_bedrock_output_tokens,
                'estimated_cost_usd': round(bedrock_total_cost, 4)
            },
            'total_estimated_cost_usd': round(total_cost, 4)
        }
    
    def reset_cost_tracking(self) -> None:
        """Reset all cost tracking counters."""
        self._total_bedrock_input_tokens = 0
        self._total_bedrock_output_tokens = 0
        self._total_textract_pages = 0
        logger.info("Cost tracking reset")