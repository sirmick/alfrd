"""
MCP tool for dynamic document summarization using DB-stored prompts.

This is the self-improving summarizer that uses type-specific prompts 
from the database.
"""
import logging
import json
import re
from typing import Dict, Any, Optional
from pathlib import Path

from mcp_server.llm import LLMClient

logger = logging.getLogger(__name__)


def summarize_document_dynamic(
    extracted_text: str,
    filename: str,
    document_type: str,
    summarizer_prompt: str,
    llm_data: Optional[Dict[str, Any]],
    llm_client: LLMClient,
) -> Dict[str, Any]:
    """
    Summarize a document using a dynamic DB-stored prompt.
    
    Args:
        extracted_text: Text extracted from the document
        filename: Original filename for context
        document_type: Type of document (bill, finance, etc.)
        summarizer_prompt: The summarization prompt from database
        llm_data: Optional LLM-optimized JSON with block-level data
        llm_client: Initialized LLMClient instance
        
    Returns:
        Dict with structured data extracted from the document
        
    Raises:
        ValueError: If summarization fails
    """
    logger.info(f"Dynamically summarizing document: {filename} (type: {document_type})")
    
    # Build the prompt with available data
    prompt_parts = [summarizer_prompt, "\n\n"]
    
    prompt_parts.append(f"Document Type: {document_type}\n\n")
    
    if llm_data:
        # Include block-level data for better extraction
        prompt_parts.append("Document Data (with spatial structure):\n")
        prompt_parts.append(json.dumps(llm_data, indent=2)[:4000])
        prompt_parts.append("\n\n")
    else:
        # Just include text
        prompt_parts.append("Document Text:\n")
        prompt_parts.append(extracted_text[:4000])
        prompt_parts.append("\n\n")
    
    prompt_parts.append(
        "Extract structured data from this document AND provide a one-line summary. "
        "Respond with JSON containing:\n"
        "1. A 'summary' field: One concise sentence describing this document.\n"
        "   - For bills: Include vendor, total amount due, and due date (e.g., 'City Light bill for $1,351.40 due Nov 02, 2020')\n"
        "   - For other documents: Include key identifying information\n"
        "2. Additional fields with relevant data for this document type\n"
        "Be specific and accurate. ALWAYS include monetary amounts in summaries for bills."
    )
    
    user_message = "".join(prompt_parts)
    
    try:
        # Invoke Bedrock with low temperature for accurate extraction
        logger.debug(f"Summarizing {filename} (type: {document_type})")
        
        response = llm_client.invoke_with_system_and_user(
            system="You are a document extraction expert. Extract structured data accurately from documents.",
            user_message=user_message,
            temperature=0.1,
            max_tokens=2048,
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
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    result_data = json.loads(json_match.group())
                else:
                    # Return raw text if no JSON found
                    result_data = {"summary": response}
        
        logger.debug(f"Summarized {filename} ({len(result_data)} fields)")
        
        return result_data
        
    except Exception as e:
        logger.error(f"Summarization failed for {filename}: {str(e)}")
        # Return fallback summary
        return {
            "summary": extracted_text[:500],
            "error": f"Failed to parse structured data: {e}"
        }