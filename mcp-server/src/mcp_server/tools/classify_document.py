"""
MCP tool for classifying documents using AWS Bedrock.
"""
import logging
from typing import Dict, Any

from shared.types import ClassificationResult, DocumentType
from mcp_server.llm import LLMClient

logger = logging.getLogger(__name__)


CLASSIFICATION_SYSTEM_PROMPT = """You are a document classification expert. Your task is to classify documents into one of three categories based on their extracted text content:

1. **junk** - Advertising, promotional materials, marketing flyers, spam mail, catalogs
2. **bill** - Utility bills (electricity, water, gas), service invoices, subscription bills, phone/internet bills
3. **finance** - Tax documents (W-2, 1099, tax returns), bank statements, investment statements, mortgage documents, loan documents, financial reports

Analyze the document text and provide:
1. The document type (junk, bill, or finance)
2. A confidence score between 0.0 and 1.0
3. A brief reasoning explaining your classification

Respond ONLY with valid JSON in this exact format:
{
  "document_type": "junk|bill|finance",
  "confidence": 0.95,
  "reasoning": "Brief explanation of classification"
}"""


def classify_document(
    extracted_text: str,
    filename: str,
    llm_client: LLMClient,
) -> ClassificationResult:
    """
    Classify a document using AWS Bedrock.
    
    Args:
        extracted_text: Text extracted from the document
        filename: Original filename for context
        llm_client: Initialized LLMClient instance
        
    Returns:
        ClassificationResult with type, confidence, and reasoning
        
    Raises:
        ValueError: If classification fails or returns invalid data
    """
    logger.info(f"Classifying document: {filename}")
    
    # Build user message with document context
    user_message = f"""Document filename: {filename}

Extracted text:
{extracted_text[:4000]}  

Classify this document as junk, bill, or finance. Respond with JSON only."""
    
    try:
        # Invoke Bedrock with low temperature for consistent classification
        response = llm_client.invoke_with_system_and_user(
            system=CLASSIFICATION_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
            max_tokens=500,
        )
        
        # Parse JSON response
        import json
        try:
            result_data = json.loads(response)
        except json.JSONDecodeError:
            # Try to extract JSON from response if wrapped in markdown
            if "```json" in response:
                json_start = response.find("```json") + 7
                json_end = response.find("```", json_start)
                result_data = json.loads(response[json_start:json_end].strip())
            else:
                raise ValueError(f"Failed to parse JSON from response: {response}")
        
        # Validate document_type
        doc_type_str = result_data.get("document_type", "").lower()
        try:
            document_type = DocumentType(doc_type_str)
        except ValueError:
            raise ValueError(f"Invalid document_type: {doc_type_str}")
        
        # Validate confidence
        confidence = result_data.get("confidence", 0.0)
        if not isinstance(confidence, (int, float)) or not (0.0 <= confidence <= 1.0):
            raise ValueError(f"Invalid confidence value: {confidence}")
        
        # Get reasoning
        reasoning = result_data.get("reasoning", "No reasoning provided")
        
        result = ClassificationResult(
            document_type=document_type,
            confidence=float(confidence),
            reasoning=reasoning,
        )
        
        logger.info(
            f"Document classified as {result.document_type.value} "
            f"with confidence {result.confidence:.2f}"
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Classification failed for {filename}: {str(e)}")
        raise ValueError(f"Classification failed: {str(e)}") from e


def classify_document_with_retry(
    extracted_text: str,
    filename: str,
    llm_client: LLMClient,
    max_retries: int = 2,
) -> ClassificationResult:
    """
    Classify document with retry logic.
    
    Args:
        extracted_text: Text extracted from the document
        filename: Original filename for context
        llm_client: Initialized LLMClient instance
        max_retries: Maximum number of retry attempts
        
    Returns:
        ClassificationResult with type, confidence, and reasoning
        
    Raises:
        ValueError: If all retry attempts fail
    """
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return classify_document(extracted_text, filename, llm_client)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Classification attempt {attempt + 1} failed for {filename}, "
                    f"retrying... Error: {str(e)}"
                )
            else:
                logger.error(
                    f"All classification attempts failed for {filename}: {str(e)}"
                )
    
    raise ValueError(f"Classification failed after {max_retries + 1} attempts") from last_error