"""The three tools this server exposes, and the dispatch that runs them.

Error policy follows the MCP spec deliberately:

  * An unknown tool or malformed arguments is a *protocol* error, returned as a
    JSON-RPC error object -- the client called the API wrong.
  * A tool that ran but could not fulfil the request (no block with that id)
    returns isError: true inside a normal result, so the model can read the
    message and correct itself instead of the call disappearing into an
    exception.
"""

from __future__ import annotations

import json
from typing import Any, Callable

from .protocol import INVALID_PARAMS, RpcError
from .store import DocumentStore

# Schemas are plain JSON Schema, as MCP requires. The descriptions matter more
# than the types: they are what the model reads when choosing a tool.
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "search_documents",
        "description": (
            "Search the policy and contract corpus by keyword. Returns ranked "
            "blocks with a citation for each. Use this first for any question "
            "about what a document says."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Keywords to search for, e.g. 'data retention period'.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of blocks to return.",
                    "minimum": 1,
                    "maximum": 20,
                    "default": 5,
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_block",
        "description": (
            "Fetch the full text of one block by its block_id, as returned by "
            "search_documents. Use this to read a hit in full before quoting it."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "block_id": {
                    "type": "string",
                    "description": "Identifier such as 'security-policy#5'.",
                }
            },
            "required": ["block_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_documents",
        "description": (
            "List every document in the corpus with its section headings. Use "
            "this when you do not know which document would contain an answer."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def _require_str(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RpcError(INVALID_PARAMS, f"'{key}' must be a non-empty string")
    return value.strip()


def _require_int(arguments: dict[str, Any], key: str, default: int, low: int, high: int) -> int:
    value = arguments.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise RpcError(INVALID_PARAMS, f"'{key}' must be an integer")
    if not low <= value <= high:
        raise RpcError(INVALID_PARAMS, f"'{key}' must be between {low} and {high}")
    return value


def _text_payload(payload: Any) -> list[dict[str, Any]]:
    """Wrap a result as MCP content blocks: readable text plus structured data."""
    return [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}]


def _search_documents(store: DocumentStore, arguments: dict[str, Any]) -> dict[str, Any]:
    query = _require_str(arguments, "query")
    limit = _require_int(arguments, "limit", default=5, low=1, high=20)
    hits = store.search(query, limit=limit)

    if not hits:
        return {
            "content": _text_payload({"query": query, "hits": []}),
            "structuredContent": {"query": query, "hits": []},
        }
    return {
        "content": _text_payload({"query": query, "hits": hits}),
        "structuredContent": {"query": query, "hits": hits},
    }


def _get_block(store: DocumentStore, arguments: dict[str, Any]) -> dict[str, Any]:
    block_id = _require_str(arguments, "block_id")
    block = store.get(block_id)

    if block is None:
        # Ran correctly, found nothing: a tool-level failure, not a protocol one.
        message = f"No block with id '{block_id}'. Use search_documents to find valid ids."
        return {
            "content": [{"type": "text", "text": message}],
            "isError": True,
        }

    return {
        "content": _text_payload(block.to_dict()),
        "structuredContent": block.to_dict(),
    }


def _list_documents(store: DocumentStore, arguments: dict[str, Any]) -> dict[str, Any]:
    documents = store.outline()
    return {
        "content": _text_payload({"documents": documents}),
        "structuredContent": {"documents": documents},
    }


_HANDLERS: dict[str, Callable[[DocumentStore, dict[str, Any]], dict[str, Any]]] = {
    "search_documents": _search_documents,
    "get_block": _get_block,
    "list_documents": _list_documents,
}


def list_tools() -> dict[str, Any]:
    """The tools/list result payload."""
    return {"tools": TOOL_DEFINITIONS}


def call_tool(store: DocumentStore, name: str, arguments: dict[str, Any] | None) -> dict[str, Any]:
    """Run one tool and return a CallToolResult."""
    handler = _HANDLERS.get(name)
    if handler is None:
        raise RpcError(
            INVALID_PARAMS,
            f"Unknown tool: {name}",
            data={"available": sorted(_HANDLERS)},
        )
    if arguments is None:
        arguments = {}
    if not isinstance(arguments, dict):
        raise RpcError(INVALID_PARAMS, "arguments must be an object")
    return handler(store, arguments)
