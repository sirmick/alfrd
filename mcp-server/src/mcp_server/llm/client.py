"""
Multi-provider LLM client (Bedrock, LM Studio, OpenAI).

Supports:
- AWS Bedrock (Claude, Nova) - default
- LM Studio (local, OpenAI-compatible)
- OpenAI API

Provider is determined by LLM_PROVIDER env var.
"""
import json
import hashlib
import logging
from typing import Optional, Dict, Any, List
from pathlib import Path

import httpx

from shared.config import Settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Multi-provider LLM client.

    Supports:
    - bedrock: AWS Bedrock (Claude, Nova)
    - lmstudio: LM Studio (OpenAI-compatible local server)
    - openai: OpenAI API

    Provider is determined by LLM_PROVIDER config setting.
    """

    def __init__(
        self,
        model_id: Optional[str] = None,
        aws_access_key_id: Optional[str] = None,
        aws_secret_access_key: Optional[str] = None,
        aws_region: Optional[str] = None,
        max_tokens: Optional[int] = None,
        provider: Optional[str] = None,
    ):
        """
        Initialize LLM client.

        Args:
            model_id: Model ID (uses Settings if not provided)
            aws_access_key_id: AWS access key (for Bedrock)
            aws_secret_access_key: AWS secret key (for Bedrock)
            aws_region: AWS region (for Bedrock)
            max_tokens: Maximum tokens for completion
            provider: Override provider (bedrock/lmstudio/openai)
        """
        self.settings = Settings()

        # Determine provider
        self.provider = provider or self.settings.llm_provider

        # Set model_id based on provider
        if model_id:
            self.model_id = model_id
        elif self.provider == "lmstudio":
            self.model_id = self.settings.lmstudio_model
        elif self.provider == "openai":
            self.model_id = self.settings.openai_model
        else:
            self.model_id = self.settings.bedrock_model_id

        self.max_tokens = max_tokens or self.settings.bedrock_max_tokens

        # Cache settings
        self._cache_enabled = self.settings.aws_cache_enabled
        self._cache_dir = self.settings.documents_path.parent / "cache" / "llm"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Provider-specific clients (lazy-loaded)
        self._aws_manager = None
        self._http_client = None

        # Store AWS credentials for Bedrock
        self._aws_access_key_id = aws_access_key_id
        self._aws_secret_access_key = aws_secret_access_key
        self._aws_region = aws_region

        # For backward compatibility - expose client attribute
        if self.provider == "bedrock":
            self._init_bedrock()
            self.client = self._aws_manager._bedrock_client if self._aws_manager else None
        else:
            self.client = None

        logger.info(f"LLM client initialized (provider: {self.provider}, model: {self.model_id})")

    def _init_bedrock(self):
        """Initialize Bedrock client."""
        if self._aws_manager is None:
            from shared.aws_clients import AWSClientManager
            self._aws_manager = AWSClientManager(
                aws_access_key_id=self._aws_access_key_id,
                aws_secret_access_key=self._aws_secret_access_key,
                aws_region=self._aws_region,
                enable_cache=True
            )

    def _get_http_client(self) -> httpx.Client:
        """Get synchronous HTTP client for OpenAI-compatible APIs."""
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=120.0)
        return self._http_client

    def _cache_key(self, **kwargs) -> str:
        """Generate cache key from request parameters."""
        cache_data = {'provider': self.provider, **kwargs}
        cache_str = json.dumps(cache_data, sort_keys=True)
        return hashlib.sha256(cache_str.encode()).hexdigest()

    def _get_cached(self, cache_key: str) -> Optional[Dict]:
        """Get cached response if available."""
        if not self._cache_enabled:
            return None

        cache_file = self._cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    data = json.load(f)

                # Log cache hit
                from shared.logging_config import log_cache_operation
                log_cache_operation('hit', self.provider, cache_key)

                return data
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
                cache_file.unlink(missing_ok=True)

        # Log cache miss
        from shared.logging_config import log_cache_operation
        log_cache_operation('miss', self.provider, cache_key)

        return None

    def _set_cached(self, cache_key: str, response: Dict) -> None:
        """Cache a response."""
        if not self._cache_enabled:
            return

        cache_file = self._cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(response, f, indent=2)

            # Log cache save
            from shared.logging_config import log_cache_operation
            log_cache_operation('save', self.provider, cache_key,
                              details={'file_size': len(json.dumps(response))})
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    def invoke(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Invoke LLM with messages.

        Routes to appropriate provider based on config.

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
        max_tokens = max_tokens or self.max_tokens

        if self.provider == "bedrock":
            return self._invoke_bedrock(system, messages, temperature, max_tokens)
        elif self.provider == "lmstudio":
            return self._invoke_openai_compatible(
                base_url=self.settings.lmstudio_base_url,
                api_key="lm-studio",
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        elif self.provider == "openai":
            return self._invoke_openai_compatible(
                base_url=self.settings.openai_base_url,
                api_key=self.settings.openai_api_key,
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    def _invoke_bedrock(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Invoke AWS Bedrock."""
        self._init_bedrock()

        result = self._aws_manager.invoke_bedrock(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            model_id=self.model_id,
            use_cache=True
        )

        return result

    def _invoke_openai_compatible(
        self,
        base_url: str,
        api_key: str,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Invoke OpenAI-compatible API (LM Studio, OpenAI, etc.)."""

        # Check cache
        cache_key = self._cache_key(
            base_url=base_url,
            model=self.model_id,
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )

        cached = self._get_cached(cache_key)
        if cached:
            cached['cached'] = True
            return cached

        # Build request
        full_messages = [{"role": "system", "content": system}] + messages

        request_body = {
            "model": self.model_id,
            "messages": full_messages,
            "temperature": temperature,
        }
        if max_tokens:
            request_body["max_tokens"] = max_tokens

        # Make request
        client = self._get_http_client()
        headers = {
            "Content-Type": "application/json",
        }
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            logger.debug(f"Invoking {self.provider} at {base_url} with model {self.model_id}")

            response = client.post(
                f"{base_url}/chat/completions",
                headers=headers,
                json=request_body
            )
            response.raise_for_status()

            data = response.json()

            # Extract response
            content = ""
            if data.get('choices') and len(data['choices']) > 0:
                content = data['choices'][0].get('message', {}).get('content', '')

            usage = data.get('usage', {})

            result = {
                'content': content,
                'stop_reason': data['choices'][0].get('finish_reason', 'stop') if data.get('choices') else 'unknown',
                'usage': {
                    'input_tokens': usage.get('prompt_tokens', 0),
                    'output_tokens': usage.get('completion_tokens', 0),
                },
                'model_id': self.model_id,
                'cached': False
            }

            # Cache result
            self._set_cached(cache_key, result)

            logger.debug(f"LLM response: {len(content)} chars, {result['usage']}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from {base_url}: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Connection error to {base_url}: {e}")
            raise RuntimeError(
                f"Could not connect to LLM at {base_url}. "
                f"Make sure the LLM server is running."
            ) from e
        except Exception as e:
            logger.error(f"Error invoking LLM: {e}")
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
        messages = [{"role": "user", "content": user_message}]
        result = self.invoke(system, messages, temperature, max_tokens)
        return result['content']

    def close(self):
        """Close HTTP client connections."""
        if self._http_client:
            self._http_client.close()
            self._http_client = None
