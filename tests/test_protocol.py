"""Protocol-level tests: framing, validation and error shapes."""

from __future__ import annotations

import json

import pytest

from mcp_retrieval.protocol import (
    INVALID_REQUEST,
    PARSE_ERROR,
    RpcError,
    decode,
    encode,
    is_notification,
    notification,
    result_response,
)


def test_encode_is_exactly_one_line():
    line = encode({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    assert line.endswith("\n")
    assert line.count("\n") == 1
    assert json.loads(line) == {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}


def test_encode_strips_embedded_newlines_from_whitespace_formatting():
    # Indented JSON would break line framing; separators remove that risk.
    line = encode({"a": [1, 2], "b": "x"})
    assert "\n" not in line.rstrip("\n")


def test_decode_accepts_a_request():
    message = decode('{"jsonrpc": "2.0", "id": 7, "method": "tools/list"}')
    assert message["method"] == "tools/list"
    assert message["id"] == 7


def test_decode_rejects_broken_json():
    with pytest.raises(RpcError) as excinfo:
        decode("{not json")
    assert excinfo.value.code == PARSE_ERROR


def test_decode_rejects_wrong_version():
    with pytest.raises(RpcError) as excinfo:
        decode('{"jsonrpc": "1.0", "id": 1, "method": "ping"}')
    assert excinfo.value.code == INVALID_REQUEST


def test_decode_rejects_missing_method():
    with pytest.raises(RpcError) as excinfo:
        decode('{"jsonrpc": "2.0", "id": 1}')
    assert excinfo.value.code == INVALID_REQUEST


def test_decode_rejects_non_object():
    with pytest.raises(RpcError) as excinfo:
        decode("[1, 2, 3]")
    assert excinfo.value.code == INVALID_REQUEST


def test_decode_rejects_empty_line():
    with pytest.raises(RpcError):
        decode("   ")


def test_notifications_have_no_id():
    note = notification("notifications/initialized")
    assert is_notification(note) is True
    assert is_notification(result_response(1, {})) is False


def test_error_response_shape():
    response = RpcError(PARSE_ERROR, "bad").to_response(4)
    assert response == {
        "jsonrpc": "2.0",
        "id": 4,
        "error": {"code": PARSE_ERROR, "message": "bad"},
    }
