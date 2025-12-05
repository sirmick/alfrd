"""MCP Tool: Detect Series

Analyze document metadata to determine which recurring series it belongs to.
"""

import json
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


SERIES_DETECTION_SYSTEM_PROMPT = """You are a document series detection expert. Your task is to analyze a document and determine what recurring series it belongs to.

A **Series** is a collection of related recurring documents from the same entity, such as:
- Monthly insurance bills from State Farm
- Utility bills from PG&E
- Rent receipts from a landlord
- Tuition bills from a school

Analyze the document and identify:

1. **Entity Name**: The primary organization/company sending this document (e.g., "State Farm Insurance", "Pacific Gas & Electric")
2. **Series Type**: Category of recurring series using snake_case (e.g., "monthly_insurance_bill", "monthly_utility_bill", "monthly_rent_receipt")
3. **Frequency**: Recurrence pattern (monthly, quarterly, annual, weekly, etc.)
4. **Series Title**: Human-readable title for this series (e.g., "State Farm Auto Insurance - Monthly Premiums")
5. **Description**: 1-2 sentence description of what this series represents
6. **Key Metadata**: Important identifiers like policy numbers, account numbers, addresses, etc.

Respond ONLY with valid JSON in this exact format:
{
  "entity": "Official entity name",
  "series_type": "snake_case_category",
  "frequency": "monthly|quarterly|annual|weekly|etc",
  "title": "Human-readable series name",
  "description": "Brief description of this series",
  "metadata": {
    "key1": "value1",
    "key2": "value2"
  }
}"""


def detect_series(
    summary: str,
    document_type: str,
    structured_data: Dict[str, Any],
    tags: list[str],
    bedrock_client,
) -> Dict[str, Any]:
    """Detect which series a document belongs to using LLM analysis.
    
    Args:
        summary: Document summary
        document_type: Document type (e.g., "insurance", "bill", "finance")
        structured_data: Extracted structured data from document
        tags: Document tags
        bedrock_client: AWS Bedrock client instance
        
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
    
    user_message = f"""{context}

Based on this document, identify the recurring series it belongs to. Consider:
- What organization is sending this document?
- What type of recurring series is this (bills, receipts, statements, etc.)?
- How often does this document recur?
- What makes this series unique from other series from the same entity?

Respond with JSON only."""
    
    try:
        # Call Bedrock with low temperature for consistent detection
        response_text = bedrock_client.invoke_with_system_and_user(
            system=SERIES_DETECTION_SYSTEM_PROMPT,
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
    bedrock_client,
    max_retries: int = 2
) -> Dict[str, Any]:
    """Detect series with retry logic.
    
    Args:
        summary: Document summary
        document_type: Document type
        structured_data: Extracted structured data
        tags: Document tags
        bedrock_client: AWS Bedrock client instance
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
                summary, document_type, structured_data, tags, bedrock_client
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