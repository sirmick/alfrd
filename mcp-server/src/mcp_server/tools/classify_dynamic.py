"""
MCP tool for dynamic document classification using DB-stored prompts.

This is the self-improving classifier that uses prompts from the database
and can suggest new document types.
"""
import logging
import json
from typing import Dict, Any

from mcp_server.llm import BedrockClient

logger = logging.getLogger(__name__)


def classify_document_dynamic(
    extracted_text: str,
    filename: str,
    classifier_prompt: str,
    known_types: list[str],
    existing_tags: list[str],
    bedrock_client: BedrockClient,
) -> Dict[str, Any]:
    """
    Classify a document using a dynamic DB-stored prompt.
    
    Args:
        extracted_text: Text extracted from the document
        filename: Original filename for context
        classifier_prompt: The classification prompt from database
        known_types: List of known document types
        existing_tags: List of existing tags from database for consistency
        bedrock_client: Initialized BedrockClient instance
        
    Returns:
        Dict with:
            - document_type: Classified type (string)
            - confidence: Confidence score (0.0-1.0)
            - reasoning: Explanation of classification
            - tags: List of tags (company/service + attributes)
            - suggested_type: (Optional) New type suggestion
            - suggestion_reasoning: (Optional) Why new type is needed
        
    Raises:
        ValueError: If classification fails or returns invalid data
    """
    logger.info(f"Dynamically classifying document: {filename}")
    
    # Build the prompt with known types and existing tags
    types_list = ", ".join(f"'{t}'" for t in known_types)
    tags_list = ", ".join(f"'{t}'" for t in existing_tags[:50])  # Limit to 50 most popular
    
    user_message = f"""{classifier_prompt}

Known document types: {types_list}

Existing tags (use when applicable): {tags_list}

You may classify the document as one of the known types, OR suggest a new type if none fit well.

Document text:
{extracted_text[:4000]}

Respond with JSON:
{{
    "document_type": "chosen_type",
    "confidence": 0.95,
    "reasoning": "why this classification",
    "tags": ["company-name", "attribute1", "attribute2"],  // REQUIRED: include company/service + attributes
    "suggested_type": "new_type_if_needed",  // Optional: only if suggesting new type
    "suggestion_reasoning": "why new type is better"  // Optional
}}"""
    
    try:
        # Invoke Bedrock with low temperature for consistent classification
        logger.debug(f"Classifying {filename}")
        
        response = bedrock_client.invoke_with_system_and_user(
            system="You are a document classification expert. Analyze documents and classify them accurately.",
            user_message=user_message,
            temperature=0.1,
            max_tokens=1024,
        )
        
        # Parse JSON response
        try:
            result_data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response if wrapped in markdown
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                result_data = json.loads(response[json_start:json_end].strip())
            else:
                # Try regex extraction
                import re
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    result_data = json.loads(json_match.group())
                else:
                    raise ValueError(f"Failed to parse JSON from response: {response}")
        
        # Validate required fields
        if "document_type" not in result_data:
            raise ValueError("Missing 'document_type' in response")
        if "confidence" not in result_data:
            result_data["confidence"] = 0.5
        if "reasoning" not in result_data:
            result_data["reasoning"] = "No reasoning provided"
        if "tags" not in result_data:
            result_data["tags"] = []  # Default to empty list if missing
        
        # Validate confidence
        confidence = float(result_data["confidence"])
        if not (0.0 <= confidence <= 1.0):
            confidence = max(0.0, min(1.0, confidence))
            result_data["confidence"] = confidence
        
        logger.debug(
            f"Classified as {result_data['document_type']} "
            f"(confidence: {confidence:.2%})"
        )
        
        return result_data
        
    except Exception as e:
        logger.error(f"Classification failed for {filename}: {str(e)}")
        raise ValueError(f"Classification failed: {str(e)}") from e