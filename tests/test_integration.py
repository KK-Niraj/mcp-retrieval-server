"""End-to-end tests: a real subprocess, real framing, real JSON on the wire.

These are the tests that matter. Everything else can pass while the transport is
broken -- spawning the server and talking to it over pipes is the only way to
prove the thing a client would actually use works.
"""

from __future__ import annotations

import pathlib
import sys

import pytest

from mcp_retrieval.client import McpClientError, StdioClient
from mcp_retrieval.protocol import INVALID_REQUEST, METHOD_NOT_FOUND

ROOT = pathlib.Path(__file__).resolve().parents[1]
COMMAND = [sys.executable, "-m", "mcp_retrieval.server"]


@pytest.fixture()
def client():
    instance = StdioClient(COMMAND, cwd=str(ROOT))
    try:
        yield instance
    finally:
        instance.close()


def test_handshake_reports_version_and_capabilities(client):
    info = client.initialize()
    assert info["protocolVersion"] == "2025-06-18"
    assert info["serverInfo"]["name"] == "mcp-retrieval-server"
    assert "tools" in info["capabilities"]
    assert info.get("instructions")


def test_tools_are_listed_over_the_wire(client):
    client.initialize()
    tools = client.list_tools()
    assert {t["name"] for t in tools} == {
        "search_documents",
        "get_block",
        "list_documents",
    }


def test_search_then_read_full_cycle(client):
    client.initialize()
    result = client.call_tool(
        "search_documents", {"query": "data retention period", "limit": 2}
    )
    hits = result["structuredContent"]["hits"]
    assert hits, "expected a hit for a phrase that appears in the corpus"

    block = client.call_tool("get_block", {"block_id": hits[0]["block_id"]})
    assert block["structuredContent"]["citation"]
    assert block["structuredContent"]["text"]


def test_ping_answers(client):
    client.initialize()
    assert client.request("ping") == {}


def test_unknown_method_returns_method_not_found(client):
    client.initialize()
    with pytest.raises(McpClientError) as excinfo:
        client.request("resources/list")
    assert excinfo.value.code == METHOD_NOT_FOUND


def test_tools_are_refused_before_initialize():
    with StdioClient(COMMAND, cwd=str(ROOT)) as fresh:
        with pytest.raises(McpClientError) as excinfo:
            fresh.list_tools()
        assert excinfo.value.code == INVALID_REQUEST


def test_notifications_produce_no_response(client):
    # If the server wrongly answered notifications, the next request would read
    # that stray response instead and fail to match its id.
    client.initialize()
    client.notify("notifications/cancelled", {"requestId": 1})
    assert client.request("ping") == {}
