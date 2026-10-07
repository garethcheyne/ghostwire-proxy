"""The JSON-RPC layer of the MCP endpoint.

A port of ghostwire-load's `src/lib/mcp/protocol.ts`, kept deliberately small and hand-written: a
stateless, tools-only Streamable HTTP server only needs initialize, ping, tools/list and
tools/call. Shapes follow the 2025-06-18 specification; tests/test_mcp_protocol.py pins them.

Nothing here knows about the proxy. Tools are handed in.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

# Newest first: the first entry is what we answer with when asked for one we do not know.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
LATEST_PROTOCOL_VERSION = SUPPORTED_PROTOCOL_VERSIONS[0]


class RPC:
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


ToolResult = dict[str, Any]
Handler = Callable[[dict[str, Any]], Awaitable[ToolResult]]


@dataclass
class McpTool:
    name: str
    title: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    # The API-key scope the tool needs; shown in its description.
    scope: str = "read"
    annotations: dict[str, bool] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        described = {
            "name": self.name,
            "title": self.title,
            "description": self.description,
            "inputSchema": self.input_schema,
        }
        if self.annotations:
            described["annotations"] = self.annotations
        return described


@dataclass
class ServerInfo:
    name: str
    title: str
    version: str
    instructions: Optional[str] = None


class ToolError(Exception):
    """A failure the model should read and act on (reported as isError, not a protocol fault)."""


def ok(id_: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": id_, "result": result}


def rpc_error(id_: Any, code: int, message: str, data: Any = None) -> dict[str, Any]:
    error: dict[str, Any] = {"code": code, "message": message}
    if data:
        error["data"] = data
    return {"jsonrpc": "2.0", "id": id_, "error": error}


def is_notification(message: dict[str, Any]) -> bool:
    """A message with no id is a notification: acknowledged, never answered."""
    return message.get("id") is None


def text_result(text: str, *, structured: Optional[dict] = None, is_error: bool = False) -> ToolResult:
    result: ToolResult = {"content": [{"type": "text", "text": text}]}
    if structured is not None:
        result["structuredContent"] = structured
    if is_error:
        result["isError"] = True
    return result


async def handle_message(
    message: Any, *, tools: list[McpTool], info: ServerInfo
) -> Optional[dict[str, Any]]:
    """Handle one JSON-RPC message. None means no reply (the route answers 202)."""
    if not isinstance(message, dict):
        return rpc_error(None, RPC.INVALID_REQUEST, "Not a JSON-RPC 2.0 request.")

    method = message.get("method")
    params = message.get("params") or {}
    id_ = message.get("id")

    if message.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return None if is_notification(message) else rpc_error(id_, RPC.INVALID_REQUEST, "Not a JSON-RPC 2.0 request.")

    # Notifications are acknowledged whatever they are; replying to one is a protocol error.
    if is_notification(message):
        return None

    if not isinstance(params, dict):
        return rpc_error(id_, RPC.INVALID_PARAMS, "params must be an object.")

    if method == "initialize":
        asked = params.get("protocolVersion")
        version = asked if asked in SUPPORTED_PROTOCOL_VERSIONS else LATEST_PROTOCOL_VERSION
        result: dict[str, Any] = {
            "protocolVersion": version,
            # Only tools: claiming a capability we do not serve invites calls that can only fail.
            "capabilities": {"tools": {}},
            "serverInfo": {"name": info.name, "title": info.title, "version": info.version},
        }
        if info.instructions:
            result["instructions"] = info.instructions
        return ok(id_, result)

    if method == "ping":
        return ok(id_, {})

    if method == "tools/list":
        return ok(id_, {"tools": [t.describe() for t in tools]})

    if method == "tools/call":
        name = params.get("name")
        tool = next((t for t in tools if t.name == name), None)
        if tool is None:
            return rpc_error(id_, RPC.INVALID_PARAMS, f'No tool named "{name}".', {"available": [t.name for t in tools]})
        arguments = params.get("arguments") or {}
        if not isinstance(arguments, dict):
            return rpc_error(id_, RPC.INVALID_PARAMS, "arguments must be an object.")
        try:
            return ok(id_, await tool.handler(arguments))
        except ToolError as e:
            return ok(id_, text_result(str(e), is_error=True))
        except Exception as e:  # a thrown tool is still a successful call at the protocol level
            return ok(id_, text_result(str(e) or "The tool failed.", is_error=True))

    return rpc_error(id_, RPC.METHOD_NOT_FOUND, f'Unsupported method "{method}".')
