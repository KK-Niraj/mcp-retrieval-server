"""End-to-end demo: spawn the server, handshake, search, then read a hit in full.

Run it with no arguments and no setup:

    python3 demo.py

It is also the shortest way to see what MCP looks like on the wire: every call
below is a JSON-RPC request written to the server's stdin and answered on its
stdout.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from mcp_retrieval.client import StdioClient  # noqa: E402


def show(label: str, value: object) -> None:
    print(f"\n{label}")
    print(json.dumps(value, indent=2, ensure_ascii=False))


def main() -> int:
    command = [sys.executable, "-m", "mcp_retrieval.server"]
    with StdioClient(command, cwd=str(ROOT)) as client:
        info = client.initialize()
        print("connected to", info["serverInfo"]["name"], info["serverInfo"]["version"])
        print("protocol", info["protocolVersion"])
        print("capabilities", info["capabilities"])
        print("\ninstructions:", info["instructions"])

        print("\n--- tools/list ---")
        for tool in client.list_tools():
            summary = (tool.get("description") or "").split(".")[0]
            print(f"  {tool['name']:<18} {summary}")

        query = "how long is customer data retained after termination"
        print(f"\n--- tools/call search_documents({query!r}) ---")
        result = client.call_tool("search_documents", {"query": query, "limit": 3})
        for hit in result["structuredContent"]["hits"]:
            print(f"  {hit['score']:>6}  {hit['citation']}")
            print(f"          {hit['snippet'][:96]}...")

        top = result["structuredContent"]["hits"][0]
        print(f"\n--- tools/call get_block({top['block_id']!r}) ---")
        block = client.call_tool("get_block", {"block_id": top["block_id"]})
        print("  citation:", block["structuredContent"]["citation"])
        print("  text    :", block["structuredContent"]["text"])

        print("\n--- tools/call get_block('does-not-exist') ---")
        missing = client.call_tool("get_block", {"block_id": "does-not-exist"})
        print("  isError:", missing.get("isError", False))
        print("  message:", missing["content"][0]["text"])

        print("\n--- tools/call on an unknown tool (protocol error) ---")
        try:
            client.call_tool("delete_everything", {})
        except Exception as exc:  # the client raises on JSON-RPC errors
            print("  raised:", exc)

    print("\nserver exited cleanly")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
