"""
AWS Bedrock LLM client for invoking Claude models.
"""
import json
import logging
from typing import Optional, Dict, Any, List

import boto3
from botocore.exceptions import ClientError

from shared.config import Settings

logger = logging.getLogger(__name__)


class BedrockClient:
    """Client for invoking Claude models via AWS Bedrock."""
    
    def __init__(
        self,
        model_id: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ):
        """
        Initialize Bedrock client.
        
        Args:
            model_id: Bedrock model ID (e.g., 'anthropic.claude-3-sonnet-20240229-v1:0')
            aws_access_key_id: AWS access key (uses Settings if not provided)
            aws_secret_access_key: AWS secret key (uses Settings if not provided)
            aws_region: AWS region (uses Settings if not provided)
            max_tokens: Maximum tokens for completion (uses Settings if not provided)
        """
        settings = Settings()
        
        self.model_id = model_id or settings.bedrock_model_id
        self.max_tokens = max_tokens or settings.bedrock_max_tokens
        
        # Initialize boto3 client
        session_kwargs = {}
        if aws_access_key_id and aws_secret_access_key:
            session_kwargs['aws_access_key_id'] = aws_access_key_id
            session_kwargs['aws_secret_access_key'] = aws_secret_access_key
        else:
            # Use settings or fall back to IAM role/environment
            if settings.aws_access_key_id and settings.aws_secret_access_key:
                session_kwargs['aws_access_key_id'] = settings.aws_access_key_id
                session_kwargs['aws_secret_access_key'] = settings.aws_secret_access_key
        
        region = aws_region or settings.aws_region
        
        self.client = boto3.client(
            'bedrock-runtime',
            region_name=region,
            **session_kwargs
        )
        
        logger.info(f"Initialized Bedrock client with model {self.model_id}")
    
    def invoke(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke Bedrock model with messages.
        
        Args:
            system: System prompt
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Override default max tokens
            
        Returns:
            Dict with:
                - content: Response text
                - stop_reason: Reason for stopping
                - usage: Token usage info
                - model_id: Model that was invoked
                
        Raises:
            ClientError: If Bedrock API call fails
        """
        max_tokens_to_use = max_tokens or self.max_tokens
        
        # Detect model type and build appropriate request body
        is_claude = 'anthropic' in self.model_id.lower() or 'claude' in self.model_id.lower()
        is_nova = 'amazon' in self.model_id.lower() and 'nova' in self.model_id.lower()
        
        if is_claude:
            # Claude models use Messages API format
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "system": system,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens_to_use,
            }
        elif is_nova:
            # Amazon Nova models use different format
            # Combine system and user message for Nova
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
                    "maxTokens": max_tokens_to_use,
                }
            }
        else:
            # Default to Claude format
            request_body = {
                "anthropic_version": "bedrock-2023-05-31",
                "system": system,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens_to_use,
            }
        
        try:
            logger.debug(f"Invoking Bedrock model {self.model_id}")
            
            response = self.client.invoke_model(
                modelId=self.model_id,
                body=json.dumps(request_body),
                contentType='application/json',
                accept='application/json',
            )
            
            # Parse response
            response_body = json.loads(response['body'].read())
            
            # Extract text content from response (handle both Claude and Nova formats)
            content = ""
            if is_nova:
                # Nova format: output.message.content[0].text
                if 'output' in response_body and 'message' in response_body['output']:
                    msg_content = response_body['output']['message'].get('content', [])
                    if len(msg_content) > 0:
                        content = msg_content[0].get('text', '')
            else:
                # Claude format: content[0].text
                if 'content' in response_body and len(response_body['content']) > 0:
                    content = response_body['content'][0].get('text', '')
            
            # Extract usage and stop reason (handle format differences)
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
                'model_id': self.model_id,
            }
            
            logger.info(
                f"Bedrock invocation successful. "
                f"Input tokens: {result['usage'].get('input_tokens', 0)}, "
                f"Output tokens: {result['usage'].get('output_tokens', 0)}"
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
    
    def invoke_with_system_and_user(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Convenience method for simple system + user message invocation.
        
        Args:
            system: System prompt
            user_message: User message content
            temperature: Sampling temperature (0-1)
            max_tokens: Override default max tokens
            
        Returns:
            Response text content
        """
        messages = [
            {
                "role": "user",
                "content": user_message,
            }
        ]
        
        result = self.invoke(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        
        return result['content']