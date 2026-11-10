"""An MCP server exposing document retrieval tools over stdio.

Pure standard library: no dependencies, no API keys, no network.
"""

from __future__ import annotations

from .protocol import LATEST_PROTOCOL_VERSION, RpcError
from .store import Block, BM25, DocumentStore, build_blocks

# Defined here rather than in server.py: the package must not import the server
# module, or `python -m mcp_retrieval.server` warns about a double import.
__version__ = "0.1.0"
SERVER_NAME = "mcp-retrieval-server"
SERVER_VERSION = __version__

__all__ = [
    "Block",
    "BM25",
    "DocumentStore",
    "LATEST_PROTOCOL_VERSION",
    "RpcError",
    "SERVER_NAME",
    "SERVER_VERSION",
    "__version__",
    "build_blocks",
]
