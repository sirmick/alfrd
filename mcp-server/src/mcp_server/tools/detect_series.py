"""MCP Tool: Detect Series

Analyze document metadata to determine which recurring series it belongs to.
"""

import json
import logging
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


# DEPRECATED: This hardcoded prompt is no longer used
# The series detector now fetches prompts from the database
# This constant is kept for backward compatibility only
SERIES_DETECTION_SYSTEM_PROMPT = """DEPRECATED - DO NOT USE"""


def detect_series(
    summary: str,
    document_type: str,
    structured_data: Dict[str, Any],
    tags: list[str],
    llm_client,
    series_prompt: str,
    existing_series: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """Detect which series a document belongs to using LLM analysis.
    
    Args:
        summary: Document summary
        document_type: Document type (e.g., "insurance", "bill", "finance")
        structured_data: Extracted structured data from document
        tags: Document tags
        llm_client: AWS Bedrock client instance
        series_prompt: Series detection prompt from database
        existing_series: Optional list of existing series for context injection
                        [{"entity": "State Farm", "series_type": "monthly_insurance_bill"}, ...]
        
    Returns:
        {
            'entity': str,           # Entity name
            'series_type': str,      # Series type (snake_case)
            'frequency': str,        # Recurrence frequency
            'title': str,            # Human-readable title
            'description': str,      # Description
            'metadata': dict,        # Key identifiers
            'confidence': float      # 0-1 confidence score
        }
        
    Raises:
        RuntimeError: If series detection fails
    """
    logger.info(f"Detecting series for document type: {document_type}")
    
    # Build context for LLM
    context = f"""Document Summary: {summary}

Document Type: {document_type}

Structured Data: {json.dumps(structured_data, indent=2)}

Tags: {', '.join(tags)}"""
    
    # Add existing series context if provided
    existing_series_context = ""
    if existing_series and len(existing_series) > 0:
        series_list = "\n".join([
            f"  - Entity: \"{s['entity']}\", Type: {s['series_type']}"
            for s in existing_series
        ])
        existing_series_context = f"""

EXISTING SERIES (use these exact names when matching):
{series_list}

IMPORTANT: If this document belongs to an existing series above, you MUST use the exact entity name and series_type shown. This prevents duplicate series creation."""
    
    user_message = f"""{context}{existing_series_context}

Based on this document, identify the recurring series it belongs to. Consider:
- What organization is sending this document?
- What type of recurring series is this (bills, receipts, statements, etc.)?
- How often does this document recur?
- What makes this series unique from other series from the same entity?

Respond with JSON only."""
    
    try:
        # Call Bedrock with low temperature for consistent detection
        response_text = llm_client.invoke_with_system_and_user(
            system=series_prompt,
            user_message=user_message,
            temperature=0.0,
            max_tokens=800
        )
        
        # Try to parse JSON response
        try:
            # Find JSON in response (might have markdown code blocks)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start < 0 or json_end <= json_start:
                raise ValueError("No JSON found in response")
            
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)
            
            # Validate required fields
            required_fields = ['entity', 'series_type', 'title']
            missing_fields = [f for f in required_fields if not parsed.get(f)]
            if missing_fields:
                raise ValueError(f"Missing required fields: {missing_fields}")
            
            # Build result with defaults for optional fields
            result = {
                'entity': parsed['entity'],
                'series_type': parsed['series_type'],
                'frequency': parsed.get('frequency', 'unknown'),
                'title': parsed['title'],
                'description': parsed.get('description', ''),
                'metadata': parsed.get('metadata', {}),
                'confidence': 0.85  # Default confidence for series detection
            }
            
            logger.info(
                f"Series detected: {result['title']} "
                f"(entity: {result['entity']}, type: {result['series_type']})"
            )
            
            return result
        
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from response: {e}\nResponse: {response_text}")
    
    except Exception as e:
        logger.error(f"Series detection failed: {str(e)}")
        raise RuntimeError(f"Series detection failed: {str(e)}") from e


def detect_series_with_retry(
    summary: str,
    document_type: str,
    structured_data: Dict[str, Any],
    tags: list[str],
    llm_client,
    series_prompt: str,
    existing_series: Optional[List[Dict[str, str]]] = None,
    max_retries: int = 2
) -> Dict[str, Any]:
    """Detect series with retry logic.
    
    Args:
        summary: Document summary
        document_type: Document type
        structured_data: Extracted structured data
        tags: Document tags
        llm_client: AWS Bedrock client instance
        series_prompt: Series detection prompt from database
        existing_series: Optional list of existing series for context injection
        max_retries: Maximum number of retry attempts
        
    Returns:
        Series detection result dict
        
    Raises:
        RuntimeError: If all retry attempts fail
    """
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return detect_series(
                summary, document_type, structured_data, tags, llm_client,
                series_prompt, existing_series
            )
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Series detection attempt {attempt + 1} failed, "
                    f"retrying... Error: {str(e)}"
                )
            else:
                logger.error(
                    f"All series detection attempts failed: {str(e)}"
                )
    
    raise RuntimeError(f"Series detection failed after {max_retries + 1} attempts") from last_error