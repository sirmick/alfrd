"""Unified LLM client with multiple provider support.

Supports:
- AWS Bedrock (Claude, Nova)
- LM Studio (local, OpenAI-compatible)
- OpenAI API

Usage:
    from shared.llm_client import LLMClient

    # Uses provider from config (LLM_PROVIDER env var)
    llm = LLMClient()

    # Or specify provider explicitly
    llm = LLMClient(provider="lmstudio")

    # Simple call
    response = await llm.invoke("You are helpful", "What is 2+2?")

    # Full call with message history
    response = await llm.invoke_messages(
        system="You are helpful",
        messages=[{"role": "user", "content": "Hello"}],
        temperature=0.0
    )
"""

import json
import logging
import hashlib
from typing import Dict, Any, List, Optional
from pathlib import Path

import httpx

from shared.config import Settings

logger = logging.getLogger(__name__)


class LLMClient:
    """Unified LLM client supporting multiple providers.

    Automatically routes to the configured provider (Bedrock, LM Studio, OpenAI).
    Includes request caching for all providers.
    """

    def __init__(
        self,
        provider: Optional[str] = None,
        enable_cache: Optional[bool] = None,
    ):
        """Initialize LLM client.

        Args:
            provider: Override provider ("bedrock", "lmstudio", "openai").
                     If None, uses LLM_PROVIDER from config.
            enable_cache: Enable request caching. If None, uses AWS_CACHE_ENABLED.
        """
        self.settings = Settings()
        self.provider = provider or self.settings.llm_provider

        # Cache settings
        if enable_cache is None:
            enable_cache = self.settings.aws_cache_enabled
        self._cache_enabled = enable_cache
        self._cache_dir = self.settings.documents_path.parent / "cache" / "llm"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

        # Provider-specific initialization
        self._bedrock_client = None
        self._http_client = None

        logger.info(f"LLMClient initialized (provider: {self.provider}, cache: {enable_cache})")

    def _get_bedrock_client(self):
        """Lazy-load Bedrock client."""
        if self._bedrock_client is None:
            from shared.aws_clients import AWSClientManager
            self._bedrock_client = AWSClientManager()
        return self._bedrock_client

    def _get_http_client(self) -> httpx.AsyncClient:
        """Lazy-load HTTP client for OpenAI-compatible APIs."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(timeout=120.0)
        return self._http_client

    def _cache_key(self, provider: str, **kwargs) -> str:
        """Generate cache key from request parameters."""
        cache_data = {'provider': provider, **kwargs}
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
                logger.debug(f"LLM cache hit: {cache_key[:8]}")
                return data
            except Exception as e:
                logger.debug(f"Cache read error: {e}")
                cache_file.unlink(missing_ok=True)
        return None

    def _set_cached(self, cache_key: str, response: Dict) -> None:
        """Cache a response."""
        if not self._cache_enabled:
            return

        cache_file = self._cache_dir / f"{cache_key}.json"
        try:
            with open(cache_file, 'w') as f:
                json.dump(response, f, indent=2)
            logger.debug(f"LLM cache save: {cache_key[:8]}")
        except Exception as e:
            logger.debug(f"Cache write error: {e}")

    async def invoke(
        self,
        system: str,
        user_message: str,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> str:
        """Simple invoke with system prompt and user message.

        Args:
            system: System prompt
            user_message: User message content
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            use_cache: Use cache if available

        Returns:
            Response text content
        """
        result = await self.invoke_messages(
            system=system,
            messages=[{"role": "user", "content": user_message}],
            temperature=temperature,
            max_tokens=max_tokens,
            use_cache=use_cache
        )
        return result['content']

    async def invoke_messages(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """Invoke LLM with full message history.

        Args:
            system: System prompt
            messages: List of message dicts with 'role' and 'content'
            temperature: Sampling temperature (0-1)
            max_tokens: Maximum tokens to generate
            use_cache: Use cache if available

        Returns:
            Dict with:
                - content: Response text
                - provider: Provider used
                - model: Model used
                - usage: Token usage (if available)
                - cached: Whether response was from cache
        """
        if self.provider == "bedrock":
            return await self._invoke_bedrock(
                system, messages, temperature, max_tokens, use_cache
            )
        elif self.provider == "lmstudio":
            return await self._invoke_openai_compatible(
                base_url=self.settings.lmstudio_base_url,
                model=self.settings.lmstudio_model,
                api_key="lm-studio",  # LM Studio doesn't require a real key
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )
        elif self.provider == "openai":
            return await self._invoke_openai_compatible(
                base_url=self.settings.openai_base_url,
                model=self.settings.openai_model,
                api_key=self.settings.openai_api_key,
                system=system,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                use_cache=use_cache
            )
        else:
            raise ValueError(f"Unknown LLM provider: {self.provider}")

    async def _invoke_bedrock(
        self,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        use_cache: bool
    ) -> Dict[str, Any]:
        """Invoke AWS Bedrock."""
        bedrock = self._get_bedrock_client()

        result = bedrock.invoke_bedrock(
            system=system,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens or self.settings.bedrock_max_tokens,
            use_cache=use_cache
        )

        return {
            'content': result['content'],
            'provider': 'bedrock',
            'model': result.get('model_id', self.settings.bedrock_model_id),
            'usage': result.get('usage', {}),
            'cached': result.get('cached', False)
        }

    async def _invoke_openai_compatible(
        self,
        base_url: str,
        model: str,
        api_key: str,
        system: str,
        messages: List[Dict[str, str]],
        temperature: float,
        max_tokens: Optional[int],
        use_cache: bool
    ) -> Dict[str, Any]:
        """Invoke OpenAI-compatible API (LM Studio, OpenAI, etc.)."""

        # Check cache
        if use_cache and self._cache_enabled:
            cache_key = self._cache_key(
                'openai_compatible',
                base_url=base_url,
                model=model,
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
            "model": model,
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
            logger.debug(f"Invoking {base_url} with model {model}")

            response = await client.post(
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
                'provider': 'lmstudio' if 'localhost' in base_url else 'openai',
                'model': model,
                'usage': {
                    'input_tokens': usage.get('prompt_tokens', 0),
                    'output_tokens': usage.get('completion_tokens', 0),
                },
                'cached': False
            }

            # Cache result
            if use_cache and self._cache_enabled:
                self._set_cached(cache_key, result)

            logger.debug(f"LLM response: {len(content)} chars, {usage}")
            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error from {base_url}: {e.response.status_code} - {e.response.text}")
            raise
        except httpx.ConnectError as e:
            logger.error(f"Connection error to {base_url}: {e}")
            raise RuntimeError(
                f"Could not connect to LLM at {base_url}. "
                f"Make sure LM Studio is running with a model loaded."
            ) from e
        except Exception as e:
            logger.error(f"Error invoking LLM: {e}")
            raise

    async def close(self):
        """Close HTTP client connections."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None


# Convenience function for simple calls
async def llm_invoke(system: str, user_message: str, **kwargs) -> str:
    """Make a simple LLM call using configured provider.

    Usage:
        response = await llm_invoke("You are helpful", "What is 2+2?")
    """
    client = LLMClient()
    try:
        return await client.invoke(system, user_message, **kwargs)
    finally:
        await client.close()
