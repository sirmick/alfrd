"""MCP Tool: Summarize File

Generate summary for a collection of related documents (file).

Includes self-improvement scoring mechanism and JSON flattening table generation.
"""

import json
from typing import Dict, List, Any, Optional
from datetime import datetime


def _flatten_documents_to_table(documents: List[Dict[str, Any]]) -> Optional[str]:
    """Flatten document structured_data to a table format.
    
    Args:
        documents: List of document dicts with structured_data
        
    Returns:
        Markdown table string or None if no structured data
    """
    try:
        # Import here to avoid circular dependencies
        import sys
        from pathlib import Path
        _script_dir = Path(__file__).parent.parent.parent.parent
        sys.path.insert(0, str(_script_dir))
        
        from shared.json_flattener import flatten_to_dataframe
        
        # Only include documents with structured_data
        docs_with_data = [
            doc for doc in documents 
            if doc.get('structured_data')
        ]
        
        if not docs_with_data:
            return None
        
        # Flatten to DataFrame
        df = flatten_to_dataframe(
            docs_with_data,
            structured_data_key='structured_data',
            include_metadata=True,
            metadata_columns=['created_at', 'filename'],
            array_strategy='json',  # Keep arrays as JSON for readability
            max_depth=3  # Limit depth for readability
        )
        
        if df.empty:
            return None
        
        # Convert to markdown table
        return df.to_markdown(index=False)
        
    except Exception as e:
        # If flattening fails, return None (will fall back to JSON)
        return None


def summarize_file(
    documents: List[Dict[str, Any]],
    file_type: str = None,
    tags: List[str] = None,
    prompt: str = "",
    bedrock_client = None,
    flattened_table: Optional[str] = None
) -> Dict[str, Any]:
    """Generate summary for a file (collection of documents).
    
    Args:
        documents: List of document entries with summaries
        file_type: Optional document type (deprecated, use tags instead)
        tags: Tags defining this file
        prompt: Summarization prompt from DB
        bedrock_client: AWS Bedrock client instance
        flattened_table: Optional pre-generated flattened data table (markdown format)
    
    Returns:
        {
            'summary': str,          # Generated summary text
            'metadata': dict,         # Structured insights
            'confidence': float,      # 0-1 confidence score
            'model': str             # Model used
        }
    """
    # Validate inputs
    if not documents:
        raise ValueError("No documents provided for summarization")
    
    if not isinstance(documents, list):
        raise TypeError(f"documents must be a list, got {type(documents)}")
    
    # Generate flattened table if not provided
    if flattened_table is None:
        flattened_table = _flatten_documents_to_table(documents)
    
    # Build context for LLM
    tags = tags or []
    if not isinstance(tags, list):
        tags = [str(tags)]
    
    context = f"Tags: {', '.join(tags)}\n"
    context += f"Total Documents: {len(documents)}\n\n"
    
    # Include flattened table if available
    if flattened_table:
        context += "=== STRUCTURED DATA TABLE (Flattened) ===\n\n"
        context += flattened_table
        context += "\n\n=== END TABLE ===\n\n"
    
    context += "Documents (chronological order):\n\n"
    
    for i, doc in enumerate(documents, 1):
        doc_date = doc.get('created_at') or doc.get('date')
        if isinstance(doc_date, datetime):
            doc_date = doc_date.strftime('%Y-%m-%d')
        
        context += f"[{i}] {doc_date} - {doc.get('filename', 'Unknown')}\n"
        
        # Include summary or structured data
        if doc.get('summary'):
            context += f"Summary: {doc['summary']}\n"
        elif doc.get('structured_data') and not flattened_table:
            # Only include raw JSON if we don't have flattened table
            structured = doc['structured_data']
            if isinstance(structured, str):
                context += f"Data: {structured}\n"
            else:
                context += f"Data: {json.dumps(structured)}\n"
        
        context += "\n"
    
    # Build user message with table-aware instructions
    table_instruction = ""
    if flattened_table:
        table_instruction = "\nNOTE: Use the structured data table above to identify trends, patterns, and calculate statistics accurately."
    
    user_message = f"""{prompt}

--- DOCUMENTS TO SUMMARIZE ---

{context}

--- INSTRUCTIONS ---

Please provide:
1. A comprehensive summary{table_instruction}
2. Key insights and patterns across the series
3. Important statistics or totals (calculate from the table if provided)
4. Any recommendations or action items
5. Trend analysis (increasing/decreasing patterns, anomalies)

Format your response as JSON:
{{
  "summary": "<summary text>",
  "insights": ["<insight 1>", "<insight 2>", ...],
  "statistics": {{"<key>": "<value>", ...}},
  "recommendations": ["<recommendation 1>", ...],
  "trends": {{"<metric>": "<trend description>", ...}}
}}"""
    
    # Call Bedrock using the correct method
    try:
        response_text = bedrock_client.invoke_with_system_and_user(
            system="You are a document summarization expert. Analyze collections of related documents and provide comprehensive summaries with insights.",
            user_message=user_message,
            temperature=0.1,
            max_tokens=2000
        )
        
        # Try to parse as JSON
        try:
            # Find JSON in response (might have markdown code blocks)
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                parsed = json.loads(json_str)
                
                return {
                    'summary': parsed.get('summary', response_text),
                    'metadata': {
                        'insights': parsed.get('insights', []),
                        'statistics': parsed.get('statistics', {}),
                        'recommendations': parsed.get('recommendations', []),
                        'trends': parsed.get('trends', {})
                    },
                    'confidence': 0.85,  # Default confidence
                    'model': 'us.amazon.nova-lite-v1:0'
                }
            else:
                # Fallback: use entire response as summary
                return {
                    'summary': response_text,
                    'metadata': {},
                    'confidence': 0.75,
                    'model': 'us.amazon.nova-lite-v1:0'
                }
        
        except json.JSONDecodeError:
            # Fallback: use entire response as summary
            return {
                'summary': response_text,
                'metadata': {},
                'confidence': 0.75,
                'model': 'us.amazon.nova-lite-v1:0'
            }
    
    except Exception as e:
        raise RuntimeError(f"Bedrock API error: {e}")


def score_file_summary(
    file_summary: str,
    documents: List[Dict[str, Any]],
    current_prompt: Dict[str, Any],
    bedrock_client
) -> Dict[str, Any]:
    """Score file summary quality and suggest improvements.
    
    Evaluates:
    - Completeness (all documents covered?)
    - Insights (trends, patterns identified?)
    - Accuracy (no hallucinations?)
    - Usefulness (actionable information?)
    
    Args:
        file_summary: Generated file summary
        documents: Source documents
        current_prompt: Current prompt dict with text and performance_score
        bedrock_client: AWS Bedrock client instance
    
    Returns:
        {
            'score': float,              # 0-1 overall score
            'improved_prompt': str,      # Better prompt suggestion
            'reasoning': str,            # Explanation
            'metrics': dict             # Detailed scoring
        }
    """
    # Build evaluation context
    context = f"Current Prompt:\n{current_prompt['prompt_text']}\n\n"
    context += f"Generated Summary:\n{file_summary}\n\n"
    context += f"Number of Documents: {len(documents)}\n\n"
    context += "Document Summaries:\n"
    
    for i, doc in enumerate(documents, 1):
        context += f"[{i}] {doc.get('filename', 'Unknown')}: {doc.get('summary', 'N/A')[:200]}\n"
    
    # Scoring prompt
    scoring_prompt = """You are evaluating a file summary's quality. Score these criteria (0-1):

1. **Completeness**: Does it cover all documents?
2. **Insights**: Does it identify patterns/trends across documents?
3. **Accuracy**: Are there any hallucinations or incorrect facts?
4. **Usefulness**: Is there actionable information?

Provide your evaluation as JSON:
{
  "scores": {
    "completeness": 0.0-1.0,
    "insights": 0.0-1.0,
    "accuracy": 0.0-1.0,
    "usefulness": 0.0-1.0
  },
  "overall_score": 0.0-1.0,
  "reasoning": "<explanation>",
  "prompt_improvements": "<suggested changes to prompt>"
}"""
    
    try:
        response_text = bedrock_client.invoke_with_system_and_user(
            system="You are an expert at evaluating document summaries for quality and accuracy.",
            user_message=f"{scoring_prompt}\n\n--- CONTEXT ---\n\n{context}",
            temperature=0.1,
            max_tokens=1500
        )
        
        # Parse JSON response
        json_start = response_text.find('{')
        json_end = response_text.rfind('}') + 1
        
        if json_start >= 0 and json_end > json_start:
            json_str = response_text[json_start:json_end]
            parsed = json.loads(json_str)
            
            # Generate improved prompt if score is low
            improved_prompt = current_prompt['prompt_text']
            if parsed.get('prompt_improvements'):
                improved_prompt += f"\n\n{parsed['prompt_improvements']}"
            
            return {
                'score': parsed.get('overall_score', 0.5),
                'improved_prompt': improved_prompt,
                'reasoning': parsed.get('reasoning', 'Evaluation completed'),
                'metrics': parsed.get('scores', {})
            }
        else:
            # Fallback
            return {
                'score': 0.7,
                'improved_prompt': current_prompt['prompt_text'],
                'reasoning': 'Could not parse evaluation',
                'metrics': {}
            }
    
    except Exception as e:
        raise RuntimeError(f"Scoring error: {e}")