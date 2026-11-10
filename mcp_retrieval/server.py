"""The MCP server: a JSON-RPC loop over stdin/stdout.

Implements the three methods a working tool server needs -- initialize,
tools/list and tools/call -- plus ping. Everything else is refused with
METHOD_NOT_FOUND, which is more useful than pretending to implement it.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any, TextIO

from . import SERVER_NAME, SERVER_VERSION
from . import tools
from .protocol import (
    LATEST_PROTOCOL_VERSION,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    RpcError,
    decode,
    encode,
    is_notification,
    result_response,
)
from .store import DocumentStore

INSTRUCTIONS = (
    "Search a corpus of six policy and contract documents. Call "
    "search_documents with keywords, then get_block to read a hit in full "
    "before quoting it. Every hit carries a citation -- quote it, because an "
    "answer without a source cannot be checked."
)


class McpServer:
    """Protocol-level behaviour, with no assumption about where bytes come from."""

    def __init__(self, store: DocumentStore | None = None) -> None:
        self.store = store or DocumentStore()
        self._initialised = False
        self._handlers = {
            "initialize": self._initialize,
            "ping": self._ping,
            "tools/list": self._list_tools,
            "tools/call": self._call_tool,
        }
        # Notifications the spec defines; accepted and ignored.
        self._notifications = {"notifications/initialized", "notifications/cancelled"}

    # ---- method handlers -------------------------------------------------

    def _initialize(self, params: dict[str, Any]) -> dict[str, Any]:
        requested = params.get("protocolVersion")
        if not isinstance(requested, str):
            raise RpcError(INVALID_REQUEST, "initialize requires params.protocolVersion")

        self._initialised = True
        return {
            "protocolVersion": LATEST_PROTOCOL_VERSION,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            "instructions": INSTRUCTIONS,
        }

    def _ping(self, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    def _list_tools(self, params: dict[str, Any]) -> dict[str, Any]:
        return tools.list_tools()

    def _call_tool(self, params: dict[str, Any]) -> dict[str, Any]:
        name = params.get("name")
        if not isinstance(name, str) or not name:
            raise RpcError(INVALID_REQUEST, "tools/call requires params.name")
        return tools.call_tool(self.store, name, params.get("arguments"))

    # ---- dispatch --------------------------------------------------------

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle one decoded message; return a response, or None if silent."""
        method = message["method"]
        silent = is_notification(message)
        params = message.get("params") or {}
        if not isinstance(params, dict):
            if silent:
                return None
            raise RpcError(INVALID_REQUEST, "params must be an object")

        if method in self._notifications:
            return None

        handler = self._handlers.get(method)
        if handler is None:
            if silent:
                return None
            raise RpcError(METHOD_NOT_FOUND, f"Method not found: {method}")

        # Refuse work before the handshake, as the lifecycle spec requires.
        if method != "initialize" and not self._initialised:
            if silent:
                return None
            raise RpcError(
                INVALID_REQUEST,
                "Server not initialised: send 'initialize' first",
            )

        result = handler(params)
        if silent:
            return None
        return result_response(message.get("id"), result)

    def serve(self, stdin: TextIO, stdout: TextIO) -> None:
        """Read lines until EOF, answering each request in order."""
        for raw in stdin:
            if not raw.strip():
                continue
            try:
                message = decode(raw)
                response = self.handle(message)
            except RpcError as error:
                request_id = None
                try:
                    request_id = decode(raw).get("id")
                except RpcError:
                    request_id = None
                response = error.to_response(request_id)
            except Exception as exc:  # never let one bad call kill the server
                response = RpcError(-32603, f"Internal error: {exc}").to_response(None)

            if response is not None:
                stdout.write(encode(response))
                stdout.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=SERVER_NAME,
        description="MCP server exposing document retrieval tools over stdio.",
    )
    parser.add_argument(
        "--selftest",
        action="store_true",
        help="Run an in-process handshake and exit, without touching stdin.",
    )
    args = parser.parse_args(argv)

    server = McpServer()
    if args.selftest:
        tools_list = server.handle(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": LATEST_PROTOCOL_VERSION},
            }
        )
        print(f"ok: {tools_list['result']['serverInfo']['name']} handshakes")
        return 0

    server.serve(sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
