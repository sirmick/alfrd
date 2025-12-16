"""Chat service for ALFRD AI assistant.

Provides tool-based chat with multi-provider LLM support:
- AWS Bedrock (native Converse API with tools)
- LM Studio (OpenAI-compatible with tool calling)
- OpenAI (native tool calling)

Adapted from scripts/alfrd-chat for HTTP API use.
"""

import json
import logging
import re
from typing import Optional, List, Dict, Any
from uuid import UUID

import httpx
import pandas as pd

from shared.database import AlfrdDatabase
from shared.config import Settings
from shared.json_flattener import flatten_dict

logger = logging.getLogger(__name__)


class ChatSession:
    """Represents a single chat conversation with history."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.conversation_history: List[Dict[str, Any]] = []

    def add_user_message(self, content: str):
        """Add a user message to history."""
        self.conversation_history.append({
            "role": "user",
            "content": content
        })
        # Keep history manageable
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

    def add_assistant_message(self, content: str):
        """Add an assistant message to history."""
        self.conversation_history.append({
            "role": "assistant",
            "content": content
        })

    def clear(self):
        """Clear conversation history."""
        self.conversation_history = []


class ChatService:
    """AI chat service with tool-based document queries.

    Supports multiple LLM providers:
    - bedrock: Uses AWS Bedrock Converse API with native tool support
    - lmstudio: Uses OpenAI-compatible API with tool calling
    - openai: Uses OpenAI API with native tool support
    """

    # In-memory session storage (could be Redis in production)
    _sessions: Dict[str, ChatSession] = {}

    def __init__(self, db: AlfrdDatabase):
        self.db = db
        self.settings = Settings()
        self.provider = self.settings.llm_provider

        # Initialize provider-specific clients
        self._bedrock_client = None
        self._http_client = None

        if self.provider == "bedrock":
            self._init_bedrock()
        else:
            self._http_client = httpx.AsyncClient(timeout=120.0)

        logger.info(f"ChatService initialized with provider: {self.provider}")

        # Tool definitions for the LLM
        self.tools = [
            {
                "name": "search",
                "description": "Unified search across documents, files, and series. Use this to find anything matching a query.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Search query (searches document text, file summaries/tags, and series entities/titles)"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum results per type to return (default: 10)",
                            "default": 10
                        }
                    },
                    "required": ["query"]
                }
            },
            {
                "name": "list_series",
                "description": "List all document series (recurring documents from same entity like monthly bills).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum series to return",
                            "default": 20
                        }
                    }
                }
            },
            {
                "name": "get_series_details",
                "description": "Get details about a specific series including all its documents.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "series_id": {
                            "type": "string",
                            "description": "UUID of the series"
                        }
                    },
                    "required": ["series_id"]
                }
            },
            {
                "name": "get_series_data_table",
                "description": "Get structured data from a series as a table. Useful for analyzing amounts, dates, etc.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "series_id": {
                            "type": "string",
                            "description": "UUID of the series"
                        }
                    },
                    "required": ["series_id"]
                }
            },
            {
                "name": "list_document_types",
                "description": "List all document types in the system.",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "list_documents_by_type",
                "description": "List documents filtered by type (e.g., 'utility_bill', 'insurance', 'rent').",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "document_type": {
                            "type": "string",
                            "description": "Document type to filter by"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum documents to return",
                            "default": 20
                        }
                    },
                    "required": ["document_type"]
                }
            },
            {
                "name": "get_document",
                "description": "Get full details of a specific document by ID.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "document_id": {
                            "type": "string",
                            "description": "UUID of the document"
                        }
                    },
                    "required": ["document_id"]
                }
            },
            {
                "name": "get_stats",
                "description": "Get overall statistics about the document database.",
                "input_schema": {
                    "type": "object",
                    "properties": {}
                }
            },
            {
                "name": "list_files",
                "description": "List files (tag-based groups of related documents).",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum files to return",
                            "default": 20
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by tags"
                        }
                    }
                }
            },
            {
                "name": "get_file",
                "description": "Get details about a specific file including its summary.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "file_id": {
                            "type": "string",
                            "description": "UUID of the file"
                        }
                    },
                    "required": ["file_id"]
                }
            },
            {
                "name": "list_tags",
                "description": "List all tags in the system with usage counts.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "limit": {
                            "type": "integer",
                            "description": "Maximum tags to return",
                            "default": 50
                        }
                    }
                }
            }
        ]

    def get_or_create_session(self, session_id: Optional[str] = None) -> ChatSession:
        """Get existing session or create a new one."""
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        import uuid
        new_id = session_id or str(uuid.uuid4())
        session = ChatSession(new_id)
        self._sessions[new_id] = session
        return session

    def _init_bedrock(self):
        """Initialize AWS Bedrock client."""
        from shared.aws_clients import AWSClientManager
        aws_manager = AWSClientManager(enable_cache=True)
        self._bedrock_client = aws_manager._bedrock_client
        self._model_id = self.settings.bedrock_model_id

    def _get_openai_tools(self) -> List[Dict]:
        """Convert tools to OpenAI format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool["input_schema"]
                }
            }
            for tool in self.tools
        ]

    def _get_bedrock_tool_config(self) -> Dict:
        """Convert tools to Bedrock Converse format."""
        return {
            "tools": [
                {
                    "toolSpec": {
                        "name": tool["name"],
                        "description": tool["description"],
                        "inputSchema": {
                            "json": tool["input_schema"]
                        }
                    }
                }
                for tool in self.tools
            ]
        }

    def delete_session(self, session_id: str) -> bool:
        """Delete a chat session."""
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """Execute a tool and return the result as a string."""
        try:
            if tool_name == "search":
                results = await self.db.search(
                    query=tool_input["query"],
                    limit=tool_input.get("limit", 10),
                    include_documents=True,
                    include_files=True,
                    include_series=True
                )
                return json.dumps(results, indent=2, default=str)

            elif tool_name == "list_series":
                results = await self.db.list_series(limit=tool_input.get("limit", 20))
                simplified = []
                for s in results:
                    simplified.append({
                        "id": str(s["id"]),
                        "entity": s.get("entity"),
                        "title": s.get("title"),
                        "document_count": s.get("document_count", 0),
                        "series_type": s.get("series_type")
                    })
                return json.dumps(simplified, indent=2, default=str)

            elif tool_name == "get_series_details":
                series_id = UUID(tool_input["series_id"])
                series = await self.db.get_series(series_id)
                if not series:
                    return json.dumps({"error": "Series not found"})
                docs = await self.db.get_series_documents(series_id)
                return json.dumps({
                    "series": series,
                    "documents": docs[:10],
                    "total_documents": len(docs)
                }, indent=2, default=str)

            elif tool_name == "get_series_data_table":
                series_id = UUID(tool_input["series_id"])
                docs = await self.db.get_series_documents(series_id)

                flattened_rows = []
                for doc in docs:
                    if doc.get("structured_data"):
                        row = {"document_id": str(doc["id"])}
                        flat_data = flatten_dict(doc["structured_data"])
                        row.update(flat_data)
                        flattened_rows.append(row)

                if not flattened_rows:
                    return json.dumps({"error": "No structured data found in series"})

                try:
                    df = pd.DataFrame(flattened_rows)
                    return df.to_markdown(index=False)
                except Exception:
                    return json.dumps(flattened_rows[:5], indent=2, default=str)

            elif tool_name == "list_document_types":
                results = await self.db.get_document_types(active_only=True)
                return json.dumps([{"name": dt.get("type_name") or dt.get("name"), "description": dt.get("description", "")} for dt in results], indent=2)

            elif tool_name == "list_documents_by_type":
                results = await self.db.list_documents(
                    status="completed",
                    document_type=tool_input["document_type"],
                    limit=tool_input.get("limit", 20)
                )
                simplified = []
                for d in results:
                    simplified.append({
                        "id": str(d["id"]),
                        "filename": d.get("filename"),
                        "document_type": d.get("document_type"),
                        "summary": (d.get("summary") or "")[:200],
                        "created_at": str(d.get("created_at"))
                    })
                return json.dumps(simplified, indent=2, default=str)

            elif tool_name == "get_document":
                doc_id = UUID(tool_input["document_id"])
                doc = await self.db.get_document_full(doc_id)
                if not doc:
                    return json.dumps({"error": "Document not found"})
                return json.dumps({
                    "id": str(doc["id"]),
                    "filename": doc.get("filename"),
                    "document_type": doc.get("document_type"),
                    "status": doc.get("status"),
                    "summary": doc.get("summary"),
                    "structured_data": doc.get("structured_data"),
                    "extracted_text": (doc.get("extracted_text") or "")[:2000],
                    "created_at": str(doc.get("created_at"))
                }, indent=2, default=str)

            elif tool_name == "get_stats":
                stats = await self.db.get_stats()
                return json.dumps(stats, indent=2, default=str)

            elif tool_name == "list_files":
                results = await self.db.list_files(
                    limit=tool_input.get("limit", 20),
                    tags=tool_input.get("tags")
                )
                simplified = []
                for f in results:
                    simplified.append({
                        "id": str(f["id"]),
                        "tags": f.get("tags", []),
                        "document_count": f.get("document_count", 0),
                        "status": f.get("status"),
                        "summary": (f.get("summary_text") or "")[:200]
                    })
                return json.dumps(simplified, indent=2, default=str)

            elif tool_name == "get_file":
                file_id = UUID(tool_input["file_id"])
                file = await self.db.get_file(file_id)
                if not file:
                    return json.dumps({"error": "File not found"})
                return json.dumps({
                    "id": str(file["id"]),
                    "tags": file.get("tags", []),
                    "document_count": file.get("document_count", 0),
                    "status": file.get("status"),
                    "summary": file.get("summary_text"),
                }, indent=2, default=str)

            elif tool_name == "list_tags":
                results = await self.db.get_all_tags(limit=tool_input.get("limit", 50))
                simplified = []
                for t in results:
                    simplified.append({
                        "name": t.get("tag_name"),
                        "usage_count": t.get("usage_count", 0)
                    })
                return json.dumps(simplified, indent=2, default=str)

            else:
                return json.dumps({"error": f"Unknown tool: {tool_name}"})

        except Exception as e:
            logger.error(f"Tool execution error: {e}")
            return json.dumps({"error": str(e)})

    async def _build_system_prompt(self) -> str:
        """Build the system prompt with dynamic context."""
        # Load base prompt from database
        prompt_record = await self.db.get_active_prompt('chat_system')
        if prompt_record:
            base_prompt = prompt_record['prompt_text']
        else:
            base_prompt = """You are ALFRD, an AI assistant for a personal document management system.

You help users query and analyze their documents (bills, insurance, receipts, etc.).

## Available Data

### Document Series
{{SERIES}}

### Files (Tag-Based Groups)
{{FILES}}

### Tags
{{TAGS}}

### Document Types
{{DOCUMENT_TYPES}}

Use the tools available to help the user query their documents."""

        # Gather dynamic context
        series_list = await self.db.list_series(limit=20)
        files_list = await self.db.list_files(limit=20)
        tags_list = await self.db.get_all_tags(limit=30)
        doc_types = await self.db.get_document_types(active_only=True)

        # Format series context
        series_text = ""
        for s in series_list:
            series_text += f"- {s.get('entity', 'Unknown')}: {s.get('title', '')} ({s.get('document_count', 0)} docs) [ID: {s['id']}]\n"
        if not series_text:
            series_text = "No document series found.\n"

        # Format files context
        files_text = ""
        for f in files_list:
            tags = ", ".join(f.get('tags', []))
            files_text += f"- Tags: [{tags}] ({f.get('document_count', 0)} docs) [ID: {f['id']}]\n"
        if not files_text:
            files_text = "No files found.\n"

        # Format tags context
        tags_text = ""
        for t in tags_list:
            tags_text += f"- {t.get('tag_name', '')} ({t.get('usage_count', 0)} uses)\n"
        if not tags_text:
            tags_text = "No tags found.\n"

        # Format document types context
        doc_types_text = ""
        for dt in doc_types:
            name = dt.get('name', dt.get('type_name', str(dt)))
            doc_types_text += f"- {name}\n"
        if not doc_types_text:
            doc_types_text = "No document types found.\n"

        # Replace template variables
        prompt = base_prompt.replace('{{SERIES}}', series_text)
        prompt = prompt.replace('{{FILES}}', files_text)
        prompt = prompt.replace('{{TAGS}}', tags_text)
        prompt = prompt.replace('{{DOCUMENT_TYPES}}', doc_types_text)

        return prompt

    async def chat(self, user_message: str, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Process a user message and return the response.

        Routes to the appropriate provider-specific chat implementation.

        Args:
            user_message: The user's message
            session_id: Optional session ID for conversation continuity

        Returns:
            Dict with:
                - response: The assistant's response text
                - session_id: The session ID for this conversation
                - tool_calls: List of tools that were called (for debugging)
        """
        session = self.get_or_create_session(session_id)
        session.add_user_message(user_message)

        system_prompt = await self._build_system_prompt()

        if self.provider == "bedrock":
            return await self._chat_bedrock(session, system_prompt)
        elif self.provider == "lmstudio" and not self.settings.lmstudio_native_tools:
            # Use prompt-based tool calling for models that don't support native tools
            return await self._chat_prompt_tools(session, system_prompt)
        else:
            return await self._chat_openai_compatible(session, system_prompt)

    async def _chat_bedrock(self, session: ChatSession, system_prompt: str) -> Dict[str, Any]:
        """Chat using AWS Bedrock Converse API with native tool support."""
        tool_calls_made = []
        tool_config = self._get_bedrock_tool_config()

        # Format messages for Bedrock
        messages = []
        for msg in session.conversation_history:
            messages.append({
                "role": msg["role"],
                "content": [{"text": msg["content"]}] if isinstance(msg["content"], str) else msg["content"]
            })

        # Call Bedrock with tools
        response = self._bedrock_client.converse(
            modelId=self._model_id,
            system=[{"text": system_prompt}],
            messages=messages,
            toolConfig=tool_config
        )

        # Process response - may need multiple rounds for tool calls
        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            output = response.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])

            # Check for tool use
            tool_uses = [c for c in content if "toolUse" in c]

            if not tool_uses:
                # No tool calls, extract final text response
                text_parts = [c.get("text", "") for c in content if "text" in c]
                final_response = "\n".join(text_parts)

                session.add_assistant_message(final_response)

                return {
                    "response": final_response,
                    "session_id": session.session_id,
                    "tool_calls": tool_calls_made
                }

            # Process tool calls
            assistant_content = content
            tool_results = []

            for tool_use in tool_uses:
                tu = tool_use["toolUse"]
                tool_name = tu["name"]
                tool_input = tu["input"]
                tool_use_id = tu["toolUseId"]

                logger.debug(f"Tool call: {tool_name} with {tool_input}")
                tool_calls_made.append({"name": tool_name, "input": tool_input})

                # Execute the tool
                result = await self.execute_tool(tool_name, tool_input)

                tool_results.append({
                    "toolResult": {
                        "toolUseId": tool_use_id,
                        "content": [{"text": result}]
                    }
                })

            # Add assistant message with tool uses
            messages.append({
                "role": "assistant",
                "content": assistant_content
            })

            # Add tool results
            messages.append({
                "role": "user",
                "content": tool_results
            })

            # Continue conversation
            response = self._bedrock_client.converse(
                modelId=self._model_id,
                system=[{"text": system_prompt}],
                messages=messages,
                toolConfig=tool_config
            )

        # Max iterations reached
        return self._max_iterations_response(session, tool_calls_made)

    async def _chat_openai_compatible(self, session: ChatSession, system_prompt: str) -> Dict[str, Any]:
        """Chat using OpenAI-compatible API (LM Studio, OpenAI) with tool support."""
        tool_calls_made = []
        tools = self._get_openai_tools()

        # Determine API settings based on provider
        if self.provider == "lmstudio":
            base_url = self.settings.lmstudio_base_url
            model = self.settings.lmstudio_model
            api_key = "lm-studio"
        else:  # openai
            base_url = self.settings.openai_base_url
            model = self.settings.openai_model
            api_key = self.settings.openai_api_key

        # Format messages for OpenAI
        messages = [{"role": "system", "content": system_prompt}]
        for msg in session.conversation_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            # Make API request
            request_body = {
                "model": model,
                "messages": messages,
                "tools": tools,
                "tool_choice": "auto",
                "temperature": 0.0
            }

            logger.info(f"Sending {len(messages)} messages to LLM (iteration {iteration})")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Messages: {json.dumps(messages, indent=2, default=str)[:2000]}")

            try:
                response = await self._http_client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=request_body
                )
                response.raise_for_status()
                data = response.json()
            except httpx.ConnectError as e:
                logger.error(f"Connection error to {base_url}: {e}")
                error_msg = f"Could not connect to LLM at {base_url}. Make sure the LLM server is running."
                session.add_assistant_message(error_msg)
                return {
                    "response": error_msg,
                    "session_id": session.session_id,
                    "tool_calls": tool_calls_made
                }
            except Exception as e:
                logger.error(f"Error calling LLM: {e}")
                raise

            # Extract the response
            choice = data.get("choices", [{}])[0]
            message = choice.get("message", {})
            finish_reason = choice.get("finish_reason", "")

            # Check for tool calls
            tool_calls = message.get("tool_calls", [])

            if not tool_calls or finish_reason == "stop":
                # No tool calls, return the response
                final_response = message.get("content", "")
                session.add_assistant_message(final_response)

                return {
                    "response": final_response,
                    "session_id": session.session_id,
                    "tool_calls": tool_calls_made
                }

            # Process tool calls
            # First, add the assistant message with tool calls
            messages.append(message)

            for tc in tool_calls:
                tool_name = tc["function"]["name"]
                try:
                    tool_input = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    tool_input = {}

                tool_call_id = tc["id"]

                logger.info(f"Tool call: {tool_name} with {tool_input}")
                tool_calls_made.append({"name": tool_name, "input": tool_input})

                # Execute the tool
                result = await self.execute_tool(tool_name, tool_input)
                # Truncate very large results to avoid context overflow
                if len(result) > 8000:
                    result = result[:8000] + "\n... (truncated)"

                logger.info(f"Tool result length: {len(result)} chars")

                # Add tool result message
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result
                })

        # Max iterations reached
        return self._max_iterations_response(session, tool_calls_made)

    def _max_iterations_response(self, session: ChatSession, tool_calls_made: List) -> Dict[str, Any]:
        """Return error response when max iterations reached."""
        error_response = "I apologize, but I wasn't able to complete the request. Please try rephrasing your question."
        session.add_assistant_message(error_response)

        return {
            "response": error_response,
            "session_id": session.session_id,
            "tool_calls": tool_calls_made
        }

    def _get_tools_prompt_section(self) -> str:
        """Generate a prompt section describing available tools."""
        tools_desc = "## Available Tools\n\nYou can use the following tools by outputting a JSON block with the tool name and arguments:\n\n"
        for tool in self.tools:
            tools_desc += f"### {tool['name']}\n"
            tools_desc += f"{tool['description']}\n"
            props = tool['input_schema'].get('properties', {})
            required = tool['input_schema'].get('required', [])
            if props:
                tools_desc += "Arguments:\n"
                for prop_name, prop_def in props.items():
                    req_marker = " (required)" if prop_name in required else ""
                    tools_desc += f"  - {prop_name}: {prop_def.get('description', prop_def.get('type', 'any'))}{req_marker}\n"
            tools_desc += "\n"

        tools_desc += """## How to Use Tools

To use a tool, output EXACTLY this format:
```tool
{"tool": "tool_name", "args": {"arg1": "value1"}}
```

After receiving the tool result, provide your final answer to the user.
Only use ONE tool at a time. Wait for the result before using another tool.
If you don't need a tool, just respond directly to the user.
"""
        return tools_desc

    async def _chat_prompt_tools(self, session: ChatSession, system_prompt: str) -> Dict[str, Any]:
        """Chat using prompt-based tool calling (for models without native tool support)."""
        tool_calls_made = []

        # Add tools description to system prompt
        tools_section = self._get_tools_prompt_section()
        enhanced_prompt = system_prompt + "\n\n" + tools_section

        # Determine API settings
        if self.provider == "lmstudio":
            base_url = self.settings.lmstudio_base_url
            model = self.settings.lmstudio_model
            api_key = "lm-studio"
        else:
            base_url = self.settings.openai_base_url
            model = self.settings.openai_model
            api_key = self.settings.openai_api_key

        # Format messages
        messages = [{"role": "system", "content": enhanced_prompt}]
        for msg in session.conversation_history:
            messages.append({
                "role": msg["role"],
                "content": msg["content"]
            })

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }

        max_iterations = 5
        iteration = 0

        while iteration < max_iterations:
            iteration += 1

            request_body = {
                "model": model,
                "messages": messages,
                "temperature": 0.0
            }

            logger.info(f"Sending {len(messages)} messages to LLM (prompt-tools, iteration {iteration})")

            try:
                response = await self._http_client.post(
                    f"{base_url}/chat/completions",
                    headers=headers,
                    json=request_body
                )
                response.raise_for_status()
                data = response.json()
            except httpx.ConnectError as e:
                logger.error(f"Connection error to {base_url}: {e}")
                error_msg = f"Could not connect to LLM at {base_url}. Make sure the LLM server is running."
                session.add_assistant_message(error_msg)
                return {
                    "response": error_msg,
                    "session_id": session.session_id,
                    "tool_calls": tool_calls_made
                }
            except Exception as e:
                logger.error(f"Error calling LLM: {e}")
                raise

            # Extract response
            choice = data.get("choices", [{}])[0]
            message_content = choice.get("message", {}).get("content", "")

            # Check for tool call in response
            tool_match = re.search(r'```tool\s*\n?(.*?)\n?```', message_content, re.DOTALL)

            if not tool_match:
                # No tool call, return the response
                session.add_assistant_message(message_content)
                return {
                    "response": message_content,
                    "session_id": session.session_id,
                    "tool_calls": tool_calls_made
                }

            # Parse and execute tool call
            try:
                tool_json = json.loads(tool_match.group(1).strip())
                tool_name = tool_json.get("tool")
                tool_args = tool_json.get("args", {})

                logger.info(f"Prompt-based tool call: {tool_name} with {tool_args}")
                tool_calls_made.append({"name": tool_name, "input": tool_args})

                # Execute the tool
                result = await self.execute_tool(tool_name, tool_args)
                if len(result) > 8000:
                    result = result[:8000] + "\n... (truncated)"

                logger.info(f"Tool result length: {len(result)} chars")

                # Add assistant message and tool result to conversation
                messages.append({"role": "assistant", "content": message_content})
                messages.append({"role": "user", "content": f"Tool result for {tool_name}:\n{result}"})

            except (json.JSONDecodeError, KeyError) as e:
                logger.warning(f"Failed to parse tool call: {e}")
                # Return the response as-is if we can't parse the tool call
                session.add_assistant_message(message_content)
                return {
                    "response": message_content,
                    "session_id": session.session_id,
                    "tool_calls": tool_calls_made
                }

        # Max iterations reached
        return self._max_iterations_response(session, tool_calls_made)
