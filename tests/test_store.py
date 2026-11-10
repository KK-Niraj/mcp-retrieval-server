"""Corpus and ranking tests."""

from __future__ import annotations

from mcp_retrieval.store import DocumentStore, build_blocks, tokenize


def test_corpus_expands_into_blocks():
    blocks = build_blocks()
    assert len(blocks) == 36, "expected six documents of three sections each"
    assert all(b.block_id and b.path and b.text for b in blocks)


def test_block_ids_are_unique():
    ids = [b.block_id for b in build_blocks()]
    assert len(ids) == len(set(ids))


def test_citation_reads_as_a_locator():
    block = build_blocks()[0]
    assert block.citation.startswith(block.doc_title)
    assert " > " in block.citation


def test_tokenize_drops_stopwords():
    assert tokenize("What is the retention period?") == ["retention", "period"]


def test_search_finds_the_retention_clause():
    store = DocumentStore()
    hits = store.search("how long is customer data retained after termination", limit=3)
    assert hits, "expected at least one hit"
    assert "Vendor Master Agreement" in hits[0]["citation"] or "Retention" in hits[0]["citation"]


def test_search_respects_limit():
    store = DocumentStore()
    assert len(store.search("data", limit=2)) <= 2


def test_search_scores_are_ordered():
    store = DocumentStore()
    scores = [h["score"] for h in store.search("payment terms invoice", limit=5)]
    assert scores == sorted(scores, reverse=True)


def test_search_returns_nothing_for_unrelated_terms():
    store = DocumentStore()
    assert store.search("zebra quantum harmonica") == []


def test_get_returns_the_block_or_none():
    store = DocumentStore()
    first = store.blocks[0]
    assert store.get(first.block_id) == first
    assert store.get("nope#999") is None


def test_outline_covers_every_document():
    outline = DocumentStore().outline()
    assert len(outline) == 6
    assert all(doc["sections"] for doc in outline)
