# mcp-retrieval-server

An MCP server that exposes document retrieval as tools, implemented against the
[Model Context Protocol](https://modelcontextprotocol.io) specification
`2025-06-18`. Pure standard library: no dependencies, no API keys, no network.

An agent connected to this server can search a corpus, read a block in full, and
quote a citation for whatever it claims. That last part is the point.

```bash
python3 demo.py                      # end-to-end walkthrough, no setup
python3 -m pytest tests/ -q          # 40 tests
```

## What it does

```
$ python3 demo.py
connected to mcp-retrieval-server 0.1.0
protocol 2025-06-18
capabilities {'tools': {'listChanged': False}}

--- tools/list ---
  search_documents   Search the policy and contract corpus by keyword
  get_block          Fetch the full text of one block by its block_id
  list_documents     List every document in the corpus with its section headings

--- tools/call search_documents('how long is customer data retained after termination') ---
  11.6708  Vendor Master Agreement > 3. Data Handling
          Customer data is retained for 730 days after termination, then deleted from primary storage and ...
   3.6949  Data Processing Addendum > 3. Retention
          Personal data must not be retained beyond thirty-six (36) months from collection unless a statut...

--- tools/call get_block('vendor-agreement#6') ---
  citation: Vendor Master Agreement > 3. Data Handling
  text    : Customer data is retained for 730 days after termination, then deleted from primary storage and backups.

--- tools/call get_block('does-not-exist') ---
  isError: True
  message: No block with id 'does-not-exist'. Use search_documents to find valid ids.

--- tools/call on an unknown tool (protocol error) ---
  raised: [-32602] Unknown tool: delete_everything
```

## Three decisions worth explaining

**1. Stdio framing is newline-delimited JSON, not `Content-Length` headers.**

MCP's stdio transport sends exactly one JSON-RPC object per line, and messages
must not contain embedded newlines. That is different from LSP, which many
people have seen first and assume is the same. It also means the server holds no
framing state: read a line, answer a line. `protocol.encode()` enforces it with
compact separators, and there is a test that indented JSON cannot slip through.

**2. Protocol errors and tool errors are different things.**

The spec draws this distinction and it is easy to collapse by accident:

| Situation | Response |
|---|---|
| Unknown tool, missing/ill-typed argument | JSON-RPC error (`-32602`) |
| Tool ran, but nothing matched or no such block | normal result with `isError: true` |

The reason is behavioural: a JSON-RPC error is a fault the *client* has to handle,
while `isError` is visible to the *model*, which can read "no block with that id,
use search_documents" and correct itself on the next turn. An empty search is not
an error at all -- it returns `hits: []`.

**3. The handshake is enforced, not decorative.**

`tools/list` before `initialize` returns `-32600`. The lifecycle spec asks for
this and it is cheap to get right; a server that answers anyway teaches clients
that the handshake does not matter.

## Two smaller details

**Notifications get no reply.** A request without an `id` is a notification.
Replying to one desynchronises the client -- it reads the stray response while
waiting for the answer to the next request. There is a test that would fail if
the server ever answered one.

**Schema descriptions are written for a model, not a human.** The `description`
on each tool is what an LLM reads when deciding which tool to call, so they say
when to use it ("Use this to read a hit in full before quoting it") rather than
restating the parameter types.

## Using it from a real MCP client

```json
{
  "mcpServers": {
    "retrieval": {
      "command": "python3",
      "args": ["-m", "mcp_retrieval.server"],
      "cwd": "/absolute/path/to/mcp-retrieval-server"
    }
  }
}
```

## What is not implemented

Being specific about this is more useful than implying completeness:

- **Resources, prompts and sampling** -- only the `tools` capability is
  advertised, and the server returns `-32601` for anything else.
- **HTTP/SSE transport** -- stdio only. The transport is the one part that is not
  a pure function of the spec, so it is the part most worth doing one way well.
- **Auth** -- a stdio server is a child process of its client, so there is no
  trust boundary to authenticate across. This becomes real with HTTP transport.
- **Progress and cancellation** -- `notifications/cancelled` is accepted and
  ignored; calls are fast enough that cancellation has nothing to interrupt.
- **Pagination** -- `tools/list` has no cursor. Three tools do not need one.
- **Batching** -- JSON-RPC batching was removed in `2025-06-18`, so it is
  deliberately absent rather than forgotten.

## The corpus

Six short policy and contract documents (vendor agreement, data processing
addendum, service level agreement, security policy, expense policy, procurement
policy), split into 36 section-addressed blocks. Ranking is BM25 over each
block's text plus its citation path, so a query naming a section still matches
blocks whose body never repeats the heading.

The corpus is synthetic and small on purpose: this repository is about the
protocol and the error model, not about winning a retrieval benchmark. If you
want the retrieval numbers, that is a different repository.

## Layout

```
mcp_retrieval/
  protocol.py    JSON-RPC framing, error codes, notification handling
  store.py       corpus, blocks, BM25
  tools.py       tool schemas and dispatch
  server.py      the MCP loop over stdin/stdout
  client.py      a client that spawns and drives a server
tests/
  test_protocol.py     framing and validation
  test_store.py        corpus and ranking
  test_tools.py        tool behaviour and both kinds of failure
  test_integration.py  real subprocess, real pipes
demo.py                the walkthrough above
```

`client.py` exists so the integration tests and the demo run the same code. If
the demo works, the transport works.

## Requirements

Python 3.12, which is what this was developed and tested on; the code targets
3.10 or newer syntax but no older interpreter was used to verify that. `pytest`
for the tests, and nothing else at runtime -- no dependencies are declared
because there are none.
