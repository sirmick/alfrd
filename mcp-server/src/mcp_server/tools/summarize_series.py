"""Series-specific document summarization with schema enforcement."""

import json
import re
from typing import Dict, Any, Optional
from mcp_server.llm.bedrock import BedrockClient
import logging

logger = logging.getLogger(__name__)


def create_series_prompt_from_generic(
    generic_prompt: str,
    series_entity: str,
    series_type: str,
    sample_document: str,
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """
    Create first series-specific prompt by analyzing a sample document.
    
    Args:
        generic_prompt: Base generic summarizer prompt
        series_entity: Entity name (e.g., "Pacific Gas & Electric")
        series_type: Series type (e.g., "monthly_utility_bill")
        sample_document: Sample document text for analysis
        bedrock_client: Bedrock client
        
    Returns:
        Dict with 'prompt_text' and 'schema_definition'
    """
    # Example JSON (outside f-string to avoid nesting issues)
    example_json = """{
  "prompt_text": "Extract data from Pacific Gas & Electric monthly bills. Look for account number in top-right, total due in bottom section...",
  "schema_definition": {
    "required_fields": ["account_number", "billing_date", "total_amount_due"],
    "optional_fields": ["previous_balance", "late_fee"],
    "field_definitions": {
      "account_number": {"type": "string", "description": "Customer account number"},
      "billing_date": {"type": "date", "format": "YYYY-MM-DD", "description": "Bill date"},
      "total_amount_due": {"type": "number", "description": "Total amount due in dollars"}
    },
    "vendor_notes": "Account number is typically 10 digits in top-right corner"
  }
}"""
    
    # Build the prompt
    analysis_prompt = f"""Analyze this {series_type} document from {series_entity} and create a specialized extraction schema.

SAMPLE DOCUMENT TEXT:
{sample_document[:3000]}

GENERIC PROMPT (for reference):
{generic_prompt}

YOUR TASK:
Create a JSON response with two parts:

1. "prompt_text": Write an improved extraction prompt specifically for {series_entity} {series_type} documents.
   Include vendor-specific patterns and field locations you notice in the sample.

2. "schema_definition": Define the exact fields to extract from every document in this series.
   Include:
   - "required_fields": List of field names that MUST be present
   - "optional_fields": List of field names that may be present
   - "field_definitions": Object mapping each field name to its type/format/description
   - "vendor_notes": Any vendor-specific extraction tips

FIELD NAMING RULES:
- Use lowercase_with_underscores
- Be specific (e.g., "total_amount_due" not "amount")
- Use consistent types: "string", "number", "date", "boolean"

RETURN ONLY THE JSON OBJECT. Example format:

{example_json}
"""
    
    try:
        response = bedrock_client.invoke_with_system_and_user(
            system="You are a document schema analysis expert. Create precise extraction schemas for recurring documents. Always return valid JSON.",
            user_message=analysis_prompt,
            temperature=0.3,
            max_tokens=2000
        )
        
        logger.info(f"LLM response length: {len(response)}")
        logger.debug(f"LLM response preview: {response[:500]}")
        
        # Clean response (remove markdown, extra whitespace, etc)
        cleaned = response.strip()
        
        # Try to extract JSON from markdown blocks first
        if "```json" in cleaned:
            json_start = cleaned.find("```json") + 7
            json_end = cleaned.find("```", json_start)
            cleaned = cleaned[json_start:json_end].strip()
            logger.debug(f"Extracted from markdown block")
        elif "```" in cleaned:
            # Try generic code block
            json_start = cleaned.find("```") + 3
            json_end = cleaned.find("```", json_start)
            cleaned = cleaned[json_start:json_end].strip()
            logger.debug(f"Extracted from code block")
        
        # Parse JSON response
        try:
            result = json.loads(cleaned)
            logger.info(f"Successfully parsed JSON response")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.error(f"Cleaned response was: {cleaned[:500]}")
            
            # Last resort: try regex extraction
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                logger.debug(f"Extracted JSON via regex: {json_str[:200]}")
                result = json.loads(json_str)
            else:
                logger.error(f"No valid JSON found. Full response: {response}")
                raise ValueError(f"Invalid JSON response from LLM: {e}")
        
        logger.info(
            f"Created series prompt for {series_entity}: "
            f"{len(result.get('schema_definition', {}).get('required_fields', []))} required fields"
        )
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse series prompt creation response: {e}")
        raise ValueError(f"Invalid JSON response from LLM: {e}")
    except Exception as e:
        logger.error(f"Error creating series prompt: {e}", exc_info=True)
        raise


def summarize_with_series_prompt(
    document_text: str,
    series_prompt_text: str,
    schema_definition: Dict[str, Any],
    bedrock_client: BedrockClient
) -> Dict[str, Any]:
    """
    Summarize document using series-specific prompt.
    
    Args:
        document_text: Full document text
        series_prompt_text: Series-specific extraction prompt
        schema_definition: Expected schema for validation
        bedrock_client: Bedrock client
        
    Returns:
        Structured data extracted according to series schema
    """
    # Extract field names and types from schema definition
    required_fields = schema_definition.get('required_fields', [])
    optional_fields = schema_definition.get('optional_fields', [])
    field_defs = schema_definition.get('field_definitions', {})
    
    # Build simplified field list for the prompt
    field_list = []
    for field_name in required_fields:
        field_def = field_defs.get(field_name, {})
        field_type = field_def.get('type', 'string')
        field_desc = field_def.get('description', '')
        field_list.append(f"  - {field_name}: {field_type} (REQUIRED) - {field_desc}")
    
    for field_name in optional_fields:
        field_def = field_defs.get(field_name, {})
        field_type = field_def.get('type', 'string')
        field_desc = field_def.get('description', '')
        field_list.append(f"  - {field_name}: {field_type} (optional) - {field_desc}")
    
    fields_text = "\n".join(field_list)
    vendor_notes = schema_definition.get('vendor_notes', '')
    
    # Build prompt that only asks for data values
    full_prompt = f"""{series_prompt_text}

EXTRACTION INSTRUCTIONS:
Extract the following fields from the document:

{fields_text}

{f"VENDOR-SPECIFIC NOTES: {vendor_notes}" if vendor_notes else ""}

CRITICAL RESPONSE FORMAT:
Return ONLY a flat JSON object with the extracted field values.
DO NOT include schema metadata like "required_fields", "field_definitions", or "vendor_notes".
Only return the actual data values extracted from the document.

Example response format:
{{
  "field_name_1": "extracted value",
  "field_name_2": 123.45,
  "field_name_3": "2024-01-15"
}}

Document:
{document_text}
"""
    
    try:
        response = bedrock_client.invoke_with_system_and_user(
            system="You are a document extraction expert. Extract data precisely according to the provided schema. Always return valid JSON.",
            user_message=full_prompt,
            temperature=0.1,  # Low temp for consistency
            max_tokens=2000
        )
        
        logger.info(f"Series extraction response length: {len(response)}")
        
        # Clean response
        cleaned = response.strip()
        
        # Try to extract JSON from markdown blocks first
        if "```json" in cleaned:
            json_start = cleaned.find("```json") + 7
            json_end = cleaned.find("```", json_start)
            cleaned = cleaned[json_start:json_end].strip()
            logger.debug(f"Extracted from markdown block")
        elif "```" in cleaned:
            json_start = cleaned.find("```") + 3
            json_end = cleaned.find("```", json_start)
            cleaned = cleaned[json_start:json_end].strip()
            logger.debug(f"Extracted from code block")
        
        # Parse and validate
        try:
            result = json.loads(cleaned)
            logger.info(f"Successfully parsed series extraction JSON")
        except json.JSONDecodeError as e:
            logger.error(f"JSON parse failed: {e}")
            logger.error(f"Cleaned response was: {cleaned[:500]}")
            
            # Last resort: try regex extraction
            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
            if json_match:
                json_str = json_match.group()
                logger.debug(f"Extracted JSON via regex: {json_str[:200]}")
                result = json.loads(json_str)
            else:
                logger.error(f"No valid JSON found. Full response: {response}")
                raise ValueError(f"Invalid JSON response from LLM: {e}")
        
        # TODO: Add schema validation here
        # For now, just log field count
        field_count = len(result) if isinstance(result, dict) else 0
        logger.info(f"Series extraction complete: {field_count} fields extracted")
        
        return result
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON response from series extraction: {e}")
        raise ValueError(f"Invalid JSON response from LLM: {e}")
    except Exception as e:
        logger.error(f"Error in series extraction: {e}", exc_info=True)
        raise