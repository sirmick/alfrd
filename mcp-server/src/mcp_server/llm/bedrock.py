"""
AWS Bedrock LLM client for invoking Claude models.

DEPRECATED: This class now wraps AWSClientManager for backward compatibility.
New code should use AWSClientManager directly for caching benefits.
"""
import logging
from typing import Optional, Dict, Any, List

from shared.config import Settings
from shared.aws_clients import AWSClientManager

logger = logging.getLogger(__name__)


class BedrockClient:
    """Client for invoking Claude models via AWS Bedrock.
    
    NOTE: This is now a thin wrapper around AWSClientManager.
    Uses shared client instance for caching and cost tracking.
    """
    
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
        
        # Use unified AWS client manager (singleton with caching)
        self._aws_manager = AWSClientManager(
            aws_access_key_id=aws_access_key_id,
            aws_secret_access_key=aws_secret_access_key,
            aws_region=aws_region,
            enable_cache=True
        )
        
        # Keep reference to boto3 client for backward compatibility
        self.client = self._aws_manager._bedrock_client
        
        logger.info(f"Initialized Bedrock client with model {self.model_id} (using AWSClientManager)")
    
    def invoke(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke Bedrock model with messages.
        
        Now uses AWSClientManager for automatic caching and cost tracking.
        
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
                - cached: Whether response was from cache
        """
        result = self._aws_manager.invoke_bedrock(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or self.max_tokens,
            model_id=self.model_id,
            use_cache=True
        )
        
        # Cache status logged in aws_clients.py
        return result
    
    def invoke_with_system_and_user(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> str:
        """
        Convenience method for simple system + user message invocation.
        
        Now uses AWSClientManager for automatic caching and cost tracking.
        
        Args:
            system: System prompt
            user_message: User message content
            temperature: Sampling temperature (0-1)
            max_tokens: Override default max tokens
            
        Returns:
            Response text content
        """
        result_text = self._aws_manager.invoke_bedrock_simple(
            system=system,
            user_message=user_message,
            temperature=temperature,
            max_tokens=max_tokens or self.max_tokens,
            use_cache=True
        )
        
        return result_text