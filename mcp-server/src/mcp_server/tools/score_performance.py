"""
MCP tool for scoring classifier and summarizer performance.

This tool evaluates how well the system performed on a task and provides
feedback for prompt evolution.
"""
import logging
import json
import re
from typing import Dict, Any

from mcp_server.llm import BedrockClient

logger = logging.getLogger(__name__)


def score_classification(
    document_info: Dict[str, Any],
    classifier_prompt: str,
    bedrock_client: BedrockClient,
) -> Dict[str, Any]:
    """
    Score how well a classification was performed.
    
    Args:
        document_info: Dict with extracted_text, filename, document_type, 
                      confidence, reasoning, secondary_tags
        classifier_prompt: The prompt that was used for classification
        bedrock_client: Initialized BedrockClient instance
        
    Returns:
        Dict with:
            - score: Overall score (0.0-1.0)
            - feedback: Specific critique
            - suggested_improvements: How to improve the prompt
            - metrics: Detailed scoring metrics
        
    Raises:
        ValueError: If scoring fails
    """
    logger.info(f"Scoring classification for document {document_info.get('filename')}")
    
    scoring_prompt = f"""You are evaluating the performance of a document classifier.

Current Classifier Prompt:
{classifier_prompt}

Document classified:
- Filename: {document_info.get('filename')}
- Text (first 2000 chars): {document_info.get('extracted_text', '')[:2000]}

Classification result:
- Type: {document_info.get('document_type')}
- Confidence: {document_info.get('confidence', 0):.2%}
- Reasoning: {document_info.get('reasoning')}
- Secondary tags: {document_info.get('secondary_tags', [])}

Evaluate this classification:
1. Was the document type correct? (based on text content)
2. Was the confidence score appropriate?
3. Is the reasoning sound?
4. Are the secondary tags accurate and useful?
5. How could the classifier prompt be improved?

Respond with JSON:
{{
    "score": 0.85,  // 0.0 to 1.0, overall classification quality
    "feedback": "specific critique of this classification",
    "suggested_improvements": "how to improve the classifier prompt (be specific, under 300 words)",
    "metrics": {{
        "type_accuracy": 1.0,  // 0 or 1
        "confidence_appropriate": 1.0,  // 0 or 1
        "reasoning_quality": 0.8,  // 0.0 to 1.0
        "tags_quality": 0.7  // 0.0 to 1.0
    }}
}}"""
    
    try:
        response = bedrock_client.invoke_with_system_and_user(
            system="You are an expert at evaluating document classification quality.",
            user_message=scoring_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        
        # Parse JSON response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            raise ValueError("No JSON found in response")
        
        logger.info(f"Classification scored: {result.get('score', 0):.2f}")
        return result
        
    except Exception as e:
        logger.error(f"Scoring failed: {str(e)}")
        return {
            "score": 0.5,
            "feedback": f"Scoring error: {e}",
            "suggested_improvements": "",
            "metrics": {}
        }


def score_summarization(
    document_info: Dict[str, Any],
    summarizer_prompt: str,
    bedrock_client: BedrockClient,
) -> Dict[str, Any]:
    """
    Score how well a summarization was performed.
    
    Args:
        document_info: Dict with extracted_text, filename, document_type, structured_data
        summarizer_prompt: The prompt that was used for summarization
        bedrock_client: Initialized BedrockClient instance
        
    Returns:
        Dict with:
            - score: Overall score (0.0-1.0)
            - feedback: Specific critique
            - suggested_improvements: How to improve the prompt
            - metrics: Detailed scoring metrics
        
    Raises:
        ValueError: If scoring fails
    """
    logger.info(f"Scoring summarization for document {document_info.get('filename')}")
    
    structured_data = document_info.get('structured_data', {})
    
    scoring_prompt = f"""You are evaluating the performance of a document summarizer.

Current Summarizer Prompt:
{summarizer_prompt}

Document summarized:
- Type: {document_info.get('document_type')}
- Filename: {document_info.get('filename')}
- Text (first 2000 chars): {document_info.get('extracted_text', '')[:2000]}

Summary result:
{json.dumps(structured_data, indent=2)}

Evaluate this summary:
1. Is the summary accurate and complete?
2. Were key fields extracted correctly?
3. Is the format appropriate for the document type?
4. What information was missed?
5. How could the summarizer prompt be improved?

Respond with JSON:
{{
    "score": 0.85,  // 0.0 to 1.0, overall summary quality
    "feedback": "specific critique of this summary",
    "suggested_improvements": "how to improve the summarizer prompt (be specific)",
    "metrics": {{
        "accuracy": 0.9,
        "completeness": 0.8,
        "format_quality": 0.9
    }}
}}"""
    
    try:
        response = bedrock_client.invoke_with_system_and_user(
            system="You are an expert at evaluating document summarization quality.",
            user_message=scoring_prompt,
            temperature=0.3,
            max_tokens=1024,
        )
        
        # Parse JSON response
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
        else:
            raise ValueError("No JSON found in response")
        
        logger.info(f"Summarization scored: {result.get('score', 0):.2f}")
        return result
        
    except Exception as e:
        logger.error(f"Scoring failed: {str(e)}")
        return {
            "score": 0.5,
            "feedback": f"Scoring error: {e}",
            "suggested_improvements": "",
            "metrics": {}
        }


def evolve_prompt(
    current_prompt: str,
    prompt_type: str,
    document_type: str,
    feedback: str,
    improvements: str,
    max_words: int = 300,
    bedrock_client: BedrockClient = None,
) -> str:
    """
    Generate an improved prompt based on feedback.
    
    Args:
        current_prompt: The current prompt text
        prompt_type: 'classifier' or 'summarizer'
        document_type: Document type (for summarizer) or None (for classifier)
        feedback: Performance feedback
        improvements: Suggested improvements
        max_words: Maximum words for new prompt (default 300 for classifier)
        bedrock_client: Initialized BedrockClient instance
        
    Returns:
        Improved prompt text
        
    Raises:
        ValueError: If evolution fails
    """
    logger.info(f"Evolving {prompt_type} prompt")
    
    if prompt_type == "classifier":
        evolution_prompt = f"""You are improving a document classifier prompt.

Current prompt:
{current_prompt}

Performance feedback:
{feedback}

Suggested improvements:
{improvements}

Rewrite the classifier prompt to be more effective.

Requirements:
- Maximum {max_words} words
- Clear, specific instructions
- Include guidance on confidence scoring
- Mention that new types can be suggested
- Incorporate the improvement suggestions

Respond with ONLY the new prompt text (no JSON, no explanation)."""
    else:  # summarizer
        evolution_prompt = f"""You are improving a document summarizer prompt for {document_type} documents.

Current prompt:
{current_prompt}

Performance feedback:
{feedback}

Suggested improvements:
{improvements}

Rewrite the summarizer prompt to be more effective for {document_type} documents.

Respond with ONLY the new prompt text (no JSON, no explanation)."""
    
    try:
        response = bedrock_client.invoke_with_system_and_user(
            system="You are an expert at writing effective AI prompts.",
            user_message=evolution_prompt,
            temperature=0.5,  # Some creativity for improvements
            max_tokens=1024,
        )
        
        # Trim to max words if needed
        if max_words and prompt_type == "classifier":
            words = response.split()
            if len(words) > max_words:
                response = " ".join(words[:max_words])
        
        logger.info(f"Evolved {prompt_type} prompt ({len(response.split())} words)")
        return response.strip()
        
    except Exception as e:
        logger.error(f"Prompt evolution failed: {str(e)}")
        raise ValueError(f"Prompt evolution failed: {str(e)}") from e