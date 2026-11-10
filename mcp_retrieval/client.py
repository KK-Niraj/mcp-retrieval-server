"""A minimal MCP client that speaks to a server over stdin/stdout.

It exists so the protocol can be exercised end to end in a test: the same code
runs the demo, so if the demo works, the transport works.
"""

from __future__ import annotations

import json
import subprocess
from typing import Any

from .protocol import LATEST_PROTOCOL_VERSION, encode, notification


class McpClientError(RuntimeError):
    """The server answered with a JSON-RPC error object."""

    def __init__(self, code: int, message: str, data: Any = None) -> None:
        super().__init__(f"[{code}] {message}")
        self.code = code
        self.message = message
        self.data = data


class StdioClient:
    """Drives a subprocess speaking MCP over stdio."""

    def __init__(self, command: list[str], cwd: str | None = None) -> None:
        self._process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._next_id = 0

    # ---- transport -------------------------------------------------------

    def _send(self, message: dict[str, Any]) -> None:
        if self._process.stdin is None:
            raise RuntimeError("server stdin is closed")
        self._process.stdin.write(encode(message))
        self._process.stdin.flush()

    def _read(self) -> dict[str, Any]:
        """Read one line. Responses are not requests, so no method check here."""
        if self._process.stdout is None:
            raise RuntimeError("server stdout is closed")
        while True:
            line = self._process.stdout.readline()
            if line == "":
                stderr = ""
                if self._process.stderr is not None:
                    stderr = self._process.stderr.read()
                raise RuntimeError(f"server closed stdout unexpectedly. stderr: {stderr}")
            text = line.strip()
            if text:
                return json.loads(text)

    # ---- requests --------------------------------------------------------

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        self._next_id += 1
        request_id = self._next_id
        message: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            message["params"] = params
        self._send(message)

        while True:
            reply = self._read()
            if reply.get("id") != request_id:
                continue  # a server notification; not ours to answer
            if "error" in reply:
                error = reply["error"]
                raise McpClientError(
                    error.get("code", 0), error.get("message", ""), error.get("data")
                )
            return reply["result"]

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        self._send(notification(method, params))

    # ---- convenience -----------------------------------------------------

    def initialize(self, client_name: str = "mcp-retrieval-client") -> dict[str, Any]:
        result = self.request(
            "initialize",
            {
                "protocolVersion": LATEST_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": client_name, "version": "0.1.0"},
            },
        )
        self.notify("notifications/initialized")
        return result

    def list_tools(self) -> list[dict[str, Any]]:
        return self.request("tools/list")["tools"]

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("tools/call", {"name": name, "arguments": arguments or {}})

    # ---- lifecycle -------------------------------------------------------

    def close(self) -> None:
        if self._process.stdin is not None:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)

    def __enter__(self) -> "StdioClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
