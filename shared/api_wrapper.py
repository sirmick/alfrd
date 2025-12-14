"""
Thin wrapper to call FastAPI endpoint functions directly.

This module provides:
1. Introspection of FastAPI routes to extract metadata
2. A simple way to call any endpoint function with kwargs
3. Foundation for auto-generating CLI and MCP tools

Usage:
    from shared.api_wrapper import APIWrapper

    api = APIWrapper()
    await api.connect()

    # Call any endpoint by name
    result = await api.call('search', q='electricity', limit=20)
    result = await api.call('list_documents', status='completed', limit=10)
    result = await api.call('get_document', document_id='abc-123')
"""

import asyncio
import inspect
import json
from typing import Any, Dict, List, Optional, get_type_hints
from dataclasses import dataclass, field
from fastapi.params import Query as QueryParam, Path as PathParam
from fastapi.routing import APIRoute

from shared.database import AlfrdDatabase
from shared.config import Settings


@dataclass
class ParamInfo:
    """Information about a function parameter."""
    name: str
    type: type
    required: bool
    default: Any
    description: str = ""


@dataclass
class EndpointInfo:
    """Information about an API endpoint."""
    name: str
    path: str
    method: str
    description: str
    params: List[ParamInfo] = field(default_factory=list)
    func: callable = None

    @property
    def summary(self) -> str:
        """First line of docstring - short summary."""
        if not self.description:
            return ""
        return self.description.strip().split('\n')[0]

    def to_mcp_tool(self) -> dict:
        """Convert to MCP tool definition format."""
        properties = {}
        required = []

        for p in self.params:
            prop = {"description": p.description or f"Parameter {p.name}"}

            # Map Python types to JSON Schema types
            if p.type == bool:
                prop["type"] = "boolean"
            elif p.type == int:
                prop["type"] = "integer"
            elif p.type == float:
                prop["type"] = "number"
            elif p.type == list or (hasattr(p.type, '__origin__') and p.type.__origin__ == list):
                prop["type"] = "array"
                prop["items"] = {"type": "string"}
            else:
                prop["type"] = "string"

            # Add default if it's a simple serializable value
            if not p.required and p.default is not None:
                try:
                    json.dumps(p.default)  # Test if serializable
                    prop["default"] = p.default
                except (TypeError, ValueError):
                    pass  # Skip non-serializable defaults

            properties[p.name] = prop
            if p.required:
                required.append(p.name)

        return {
            "name": self.name,
            "description": self.summary,
            "inputSchema": {
                "type": "object",
                "properties": properties,
                "required": required
            }
        }

    def to_cli_help(self) -> str:
        """Generate CLI help text."""
        lines = [self.summary]
        if len(self.description.strip().split('\n')) > 1:
            # Add full description if there's more
            lines.append("")
            lines.append(self.description.strip())
        return '\n'.join(lines)

    def to_llm_doc(self) -> str:
        """Generate compact documentation for LLM context."""
        params_str = ", ".join(
            f"{p.name}{'?' if not p.required else ''}: {p.type.__name__}"
            for p in self.params
        )
        return f"{self.name}({params_str}) - {self.summary}"


class APIWrapper:
    """
    Wrapper to call FastAPI endpoint functions directly without HTTP.

    Automatically handles:
    - Database connection injection (replaces Depends(get_db))
    - Query/Path parameter defaults
    - Type conversion
    """

    def __init__(self, database_url: str = None):
        self.settings = Settings()
        self.db = AlfrdDatabase(database_url or self.settings.database_url)
        self._endpoints: Dict[str, EndpointInfo] = {}
        self._connected = False

    async def connect(self):
        """Initialize database connection."""
        if not self._connected:
            await self.db.initialize()
            self._connected = True

    async def close(self):
        """Close database connection."""
        if self._connected:
            await self.db.close()
            self._connected = False

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args):
        await self.close()

    def _load_endpoints(self):
        """Load endpoint metadata from FastAPI app."""
        if self._endpoints:
            return

        # Import here to avoid circular imports
        from api_server.main import app

        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue

            func = route.endpoint
            name = route.name or func.__name__

            # Extract parameter info
            params = []
            sig = inspect.signature(func)

            for param_name, param in sig.parameters.items():
                # Skip database dependency - we inject it
                if param_name == 'database':
                    continue

                default = param.default
                required = True
                description = ""
                param_type = str  # default

                # Handle Query() and Path() defaults
                if isinstance(default, (QueryParam, PathParam)):
                    # Check if required - PydanticUndefined or ... means required
                    is_undefined = (
                        default.default is ... or
                        type(default.default).__name__ == 'PydanticUndefinedType'
                    )
                    required = is_undefined
                    description = default.description or ""
                    # Get the actual default value
                    default_val = None if is_undefined else default.default
                elif default is inspect.Parameter.empty:
                    default_val = None
                    required = True
                else:
                    default_val = default
                    required = False

                # Try to get type annotation
                if param.annotation is not inspect.Parameter.empty:
                    param_type = param.annotation

                params.append(ParamInfo(
                    name=param_name,
                    type=param_type,
                    required=required,
                    default=default_val,
                    description=description
                ))

            # Get method
            methods = list(route.methods - {'HEAD', 'OPTIONS'})
            method = methods[0] if methods else 'GET'

            self._endpoints[name] = EndpointInfo(
                name=name,
                path=route.path,
                method=method,
                description=func.__doc__ or "",
                params=params,
                func=func
            )

    def list_endpoints(self) -> List[EndpointInfo]:
        """List all available endpoints."""
        self._load_endpoints()
        return list(self._endpoints.values())

    def get_endpoint(self, name: str) -> Optional[EndpointInfo]:
        """Get info about a specific endpoint."""
        self._load_endpoints()
        return self._endpoints.get(name)

    async def call(self, endpoint_name: str, **kwargs) -> Any:
        """
        Call an endpoint function directly.

        Args:
            endpoint_name: Name of the endpoint function (e.g., 'search', 'list_documents')
            **kwargs: Parameters to pass to the function

        Returns:
            The result from the endpoint function
        """
        if not self._connected:
            await self.connect()

        self._load_endpoints()

        endpoint = self._endpoints.get(endpoint_name)
        if not endpoint:
            raise ValueError(f"Unknown endpoint: {endpoint_name}. Available: {list(self._endpoints.keys())}")

        # Build kwargs with defaults
        call_kwargs = {}
        for param in endpoint.params:
            if param.name in kwargs:
                call_kwargs[param.name] = kwargs[param.name]
            elif not param.required:
                call_kwargs[param.name] = param.default
            else:
                raise ValueError(f"Missing required parameter: {param.name}")

        # Inject database
        call_kwargs['database'] = self.db

        # Call the function
        result = await endpoint.func(**call_kwargs)
        return result


    def get_mcp_tools(self) -> List[dict]:
        """Get all endpoints as MCP tool definitions."""
        self._load_endpoints()
        return [ep.to_mcp_tool() for ep in self._endpoints.values()]

    def get_llm_context(self) -> str:
        """Generate compact documentation for LLM system prompts."""
        self._load_endpoints()
        lines = ["Available ALFRD API tools:"]
        for name in sorted(self._endpoints.keys()):
            ep = self._endpoints[name]
            lines.append(f"  - {ep.to_llm_doc()}")
        return '\n'.join(lines)


# Convenience function for one-off calls
async def api_call(endpoint_name: str, **kwargs) -> Any:
    """
    Make a single API call.

    Usage:
        result = await api_call('search', q='electricity', limit=20)
    """
    async with APIWrapper() as api:
        return await api.call(endpoint_name, **kwargs)


# CLI helper to list available commands
def print_available_endpoints():
    """Print all available API endpoints and their parameters."""
    wrapper = APIWrapper.__new__(APIWrapper)
    wrapper._endpoints = {}
    wrapper._load_endpoints()

    print("\nAvailable API Endpoints:")
    print("=" * 80)

    for name, info in sorted(wrapper._endpoints.items()):
        print(f"\n{info.method} {info.path}")
        print(f"  Function: {name}")
        if info.description:
            # First line of docstring
            desc = info.description.strip().split('\n')[0]
            print(f"  Description: {desc}")
        if info.params:
            print(f"  Parameters:")
            for p in info.params:
                req = "(required)" if p.required else f"(default: {p.default})"
                print(f"    - {p.name}: {p.type.__name__} {req}")
                if p.description:
                    print(f"        {p.description}")
