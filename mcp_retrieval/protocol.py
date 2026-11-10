"""JSON-RPC 2.0 message handling for MCP's stdio transport.

MCP frames stdio messages as newline-delimited JSON: exactly one JSON-RPC
object per line, with no embedded newlines. That is deliberately simpler than
LSP's Content-Length header framing -- a server just reads a line and writes a
line, so there is no framing state to get wrong.
"""

from __future__ import annotations

import json
from typing import Any

# Standard JSON-RPC 2.0 error codes, per the MCP schema.
PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602
INTERNAL_ERROR = -32603

# The revision this server implements.
LATEST_PROTOCOL_VERSION = "2025-06-18"

# A client may open with an older revision; we always answer with ours and let
# the client decide whether it can continue.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")


class RpcError(Exception):
    """An error that must go back to the client as a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data

    def to_response(self, request_id: Any) -> dict[str, Any]:
        error: dict[str, Any] = {"code": self.code, "message": self.message}
        if self.data is not None:
            error["data"] = self.data
        return {"jsonrpc": "2.0", "id": request_id, "error": error}


def result_response(request_id: Any, result: Any) -> dict[str, Any]:
    """Wrap a successful result in a JSON-RPC response object."""
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def notification(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Build a notification: a request with no id, which must not be answered."""
    message: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
    if params is not None:
        message["params"] = params
    return message


def encode(message: dict[str, Any]) -> str:
    """Serialise one message onto a single line."""
    return json.dumps(message, ensure_ascii=False, separators=(",", ":")) + "\n"


def decode(raw: str) -> dict[str, Any]:
    """Parse one line into a JSON-RPC message, or raise RpcError."""
    text = raw.strip()
    if not text:
        raise RpcError(PARSE_ERROR, "Empty message")

    try:
        message = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RpcError(PARSE_ERROR, f"Invalid JSON: {exc.msg}") from exc

    if not isinstance(message, dict):
        raise RpcError(INVALID_REQUEST, "Message must be a JSON object")
    if message.get("jsonrpc") != "2.0":
        raise RpcError(INVALID_REQUEST, "jsonrpc must be exactly '2.0'")
    if "method" not in message:
        raise RpcError(INVALID_REQUEST, "Missing method")
    if not isinstance(message["method"], str):
        raise RpcError(INVALID_REQUEST, "method must be a string")

    return message


def is_notification(message: dict[str, Any]) -> bool:
    """A message without an id is a notification; the server must stay silent."""
    return "id" not in message
