"""Tool behaviour, including the two different kinds of failure."""

from __future__ import annotations

import pytest

from mcp_retrieval.protocol import INVALID_PARAMS, RpcError
from mcp_retrieval.store import DocumentStore
from mcp_retrieval.tools import TOOL_DEFINITIONS, call_tool, list_tools


@pytest.fixture()
def store() -> DocumentStore:
    return DocumentStore()


def test_three_tools_are_declared():
    names = {tool["name"] for tool in list_tools()["tools"]}
    assert names == {"search_documents", "get_block", "list_documents"}


def test_every_tool_has_a_described_object_schema():
    for tool in TOOL_DEFINITIONS:
        assert tool["description"], f"{tool['name']} needs a description"
        assert tool["inputSchema"]["type"] == "object"


def test_search_returns_content_and_structured_data(store):
    result = call_tool(store, "search_documents", {"query": "encryption at rest"})
    assert result["content"][0]["type"] == "text"
    hits = result["structuredContent"]["hits"]
    assert hits
    assert {"block_id", "citation", "score", "snippet", "kind"} <= set(hits[0])


def test_search_with_no_matches_is_not_an_error(store):
    result = call_tool(store, "search_documents", {"query": "zebra quantum harmonica"})
    assert "isError" not in result
    assert result["structuredContent"]["hits"] == []


def test_get_block_returns_full_text(store):
    block_id = store.blocks[0].block_id
    result = call_tool(store, "get_block", {"block_id": block_id})
    assert result["structuredContent"]["block_id"] == block_id
    assert result["structuredContent"]["text"] == store.blocks[0].text


def test_get_block_missing_is_a_tool_error_not_a_protocol_error(store):
    result = call_tool(store, "get_block", {"block_id": "does-not-exist"})
    assert result["isError"] is True
    assert "search_documents" in result["content"][0]["text"]


def test_unknown_tool_is_a_protocol_error(store):
    with pytest.raises(RpcError) as excinfo:
        call_tool(store, "delete_everything", {})
    assert excinfo.value.code == INVALID_PARAMS
    assert "delete_everything" in str(excinfo.value)


def test_missing_query_is_invalid_params(store):
    with pytest.raises(RpcError) as excinfo:
        call_tool(store, "search_documents", {})
    assert excinfo.value.code == INVALID_PARAMS


def test_blank_query_is_invalid_params(store):
    with pytest.raises(RpcError):
        call_tool(store, "search_documents", {"query": "   "})


def test_limit_out_of_range_is_invalid_params(store):
    with pytest.raises(RpcError):
        call_tool(store, "search_documents", {"query": "data", "limit": 500})


def test_limit_must_be_an_integer(store):
    with pytest.raises(RpcError):
        call_tool(store, "search_documents", {"query": "data", "limit": "5"})


def test_boolean_is_not_accepted_as_an_integer(store):
    # bool is a subclass of int; the schema says integer, so reject it.
    with pytest.raises(RpcError):
        call_tool(store, "search_documents", {"query": "data", "limit": True})


def test_list_documents_returns_every_document(store):
    result = call_tool(store, "list_documents", {})
    assert len(result["structuredContent"]["documents"]) == 6
