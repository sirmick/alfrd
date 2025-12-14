"""
MCP tool for summarizing bill documents using AWS Bedrock.
"""
import logging
import json
from typing import Dict, Any
from dataclasses import dataclass, asdict

from mcp_server.llm import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class BillSummary:
    """Structured bill summary result."""
    vendor: str
    amount: float
    due_date: str  # YYYY-MM-DD format
    account_number: str
    billing_period: Dict[str, str]  # {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}
    service_type: str
    charges: Dict[str, float]  # {"previous_balance": 0.00, "new_charges": 0.00, ...}
    line_items: list[Dict[str, Any]]  # [{"description": "...", "amount": 0.00}, ...]
    usage_data: Dict[str, Any]  # Optional usage information
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)


BILL_SUMMARY_SYSTEM_PROMPT = """You are a financial document analyzer specializing in utility bills and service invoices. Your task is to extract detailed, structured information from bill documents.

Extract the following information:
1. **vendor**: Company or service provider name
2. **amount**: Total amount due (numeric only, no currency symbols)
3. **due_date**: Payment due date in YYYY-MM-DD format
4. **account_number**: Customer account number
5. **billing_period**: Start and end dates of billing period
6. **service_type**: Type of service (electric, gas, water, internet, phone, cable, trash, etc.)
7. **charges**: Breakdown of charges (previous balance, new charges, payments, adjustments)
8. **line_items**: List of major charges with descriptions and amounts
9. **usage_data**: Usage information if available (readings, usage amount, units)

For missing information, use null or empty values. Ensure all dates are in YYYY-MM-DD format.

Respond ONLY with valid JSON in this exact format:
{
  "vendor": "Company Name",
  "amount": 123.45,
  "due_date": "2024-12-15",
  "account_number": "1234567890",
  "billing_period": {
    "start": "2024-11-01",
    "end": "2024-11-30"
  },
  "service_type": "electric",
  "charges": {
    "previous_balance": 0.00,
    "new_charges": 123.45,
    "payments": 0.00,
    "adjustments": 0.00
  },
  "line_items": [
    {"description": "Electric usage", "amount": 98.50},
    {"description": "Delivery charge", "amount": 24.95}
  ],
  "usage_data": {
    "current_reading": 12345,
    "previous_reading": 12000,
    "usage_amount": 345,
    "usage_unit": "kWh"
  }
}"""


def summarize_bill(
    llm_data: Dict[str, Any],
    filename: str,
    llm_client: LLMClient,
) -> BillSummary:
    """
    Summarize a bill document using AWS Bedrock.
    
    Args:
        llm_data: LLM-formatted data with full_text and optional blocks structure
        filename: Original filename for context
        llm_client: Initialized LLMClient instance
        
    Returns:
        BillSummary with structured bill information
        
    Raises:
        ValueError: If summarization fails or returns invalid data
    """
    logger.info(f"Summarizing bill document: {filename}")
    
    # Extract text and blocks
    full_text = llm_data.get("full_text", "")
    blocks = llm_data.get("blocks_by_document", [])
    doc_count = llm_data.get("document_count", 0)
    
    # Build user message with full structure
    # Include blocks information if available for better spatial understanding
    if blocks:
        # Truncate blocks to avoid token limits (keep first 2 documents worth)
        blocks_preview = blocks[:2] if len(blocks) > 2 else blocks
        blocks_str = json.dumps(blocks_preview, indent=2)
        
        user_message = f"""Document filename: {filename}

Document structure:
- Total pages/documents: {doc_count}
- Full text with blocks available for spatial analysis

Full text:
{full_text[:4000]}

Block structure (for spatial analysis):
{blocks_str[:2000]}

Using the text and block structure, extract detailed bill information. The blocks contain spatial positioning that can help identify tables, line items, and structured data. Respond with JSON only."""
    else:
        # Fallback to plain text only
        user_message = f"""Document filename: {filename}

Extracted text:
{full_text[:6000]}

Extract structured bill information. Respond with JSON only."""
    
    try:
        # Invoke Bedrock with low temperature for consistent extraction
        response = llm_client.invoke_with_system_and_user(
            system=BILL_SUMMARY_SYSTEM_PROMPT,
            user_message=user_message,
            temperature=0.0,
            max_tokens=2000,
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
                raise ValueError(f"Failed to parse JSON from response: {response}")
        
        # Validate and construct BillSummary
        summary = BillSummary(
            vendor=result_data.get("vendor", "Unknown"),
            amount=float(result_data.get("amount", 0.0)),
            due_date=result_data.get("due_date", ""),
            account_number=result_data.get("account_number", ""),
            billing_period=result_data.get("billing_period", {"start": "", "end": ""}),
            service_type=result_data.get("service_type", ""),
            charges=result_data.get("charges", {}),
            line_items=result_data.get("line_items", []),
            usage_data=result_data.get("usage_data", {}),
        )
        
        logger.info(
            f"Bill summarized: {summary.vendor}, ${summary.amount:.2f}, "
            f"due {summary.due_date}"
        )
        
        return summary
        
    except Exception as e:
        logger.error(f"Bill summarization failed for {filename}: {str(e)}")
        raise ValueError(f"Bill summarization failed: {str(e)}") from e


def summarize_bill_with_retry(
    llm_data: Dict[str, Any],
    filename: str,
    llm_client: LLMClient,
    max_retries: int = 2,
) -> BillSummary:
    """
    Summarize bill document with retry logic.
    
    Args:
        llm_data: LLM-formatted data with full_text and optional blocks
        filename: Original filename for context
        llm_client: Initialized LLMClient instance
        max_retries: Maximum number of retry attempts
        
    Returns:
        BillSummary with structured bill information
        
    Raises:
        ValueError: If all retry attempts fail
    """
    last_error = None
    
    for attempt in range(max_retries + 1):
        try:
            return summarize_bill(llm_data, filename, llm_client)
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                logger.warning(
                    f"Bill summarization attempt {attempt + 1} failed for {filename}, "
                    f"retrying... Error: {str(e)}"
                )
            else:
                logger.error(
                    f"All bill summarization attempts failed for {filename}: {str(e)}"
                )
    
    raise ValueError(f"Bill summarization failed after {max_retries + 1} attempts") from last_error