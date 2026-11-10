"""A small document corpus with section structure, and BM25 over its blocks.

Kept dependency-free on purpose: the point of this repository is the protocol,
not the ranking. Any retrieval library would do the same job here, and adding
one would only hide where the interesting code is.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

_WORD = re.compile(r"[a-z0-9]+")

STOPWORDS = frozenset(
    "a an and are as at be by for from has have how in is it its of on or that the "
    "this to was were what when where which who will with".split()
)


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens, stopwords removed."""
    return [w for w in _WORD.findall(text.lower()) if w not in STOPWORDS]


@dataclass(frozen=True)
class Block:
    """One retrieval unit: a section heading or a paragraph under it."""

    block_id: str
    doc_id: str
    doc_title: str
    path: tuple[str, ...]
    kind: str
    text: str

    @property
    def citation(self) -> str:
        """Human-readable locator, e.g. 'Vendor Master Agreement > Payment Terms'."""
        trail = " > ".join((self.doc_title, *self.path))
        return trail

    def to_dict(self) -> dict:
        return {
            "block_id": self.block_id,
            "doc_id": self.doc_id,
            "doc_title": self.doc_title,
            "path": list(self.path),
            "kind": self.kind,
            "text": self.text,
            "citation": self.citation,
        }


# (doc_id, title, [(section path, kind, text)])
_RAW_CORPUS: list[tuple[str, str, list[tuple[tuple[str, ...], str, str]]]] = [
    (
        "vendor-agreement",
        "Vendor Master Agreement",
        [
            (("1. Definitions",), "heading", "1. Definitions"),
            (
                ("1. Definitions",),
                "paragraph",
                "Terms used in this agreement have the meanings given in Schedule A.",
            ),
            (("2. Payment Terms",), "heading", "2. Payment Terms"),
            (
                ("2. Payment Terms",),
                "paragraph",
                "Invoices are payable within forty-five (45) days of receipt of a valid "
                "invoice. Late payment attracts interest at 1.5% per month.",
            ),
            (("3. Data Handling",), "heading", "3. Data Handling"),
            (
                ("3. Data Handling",),
                "paragraph",
                "Customer data is retained for 730 days after termination, then deleted "
                "from primary storage and backups.",
            ),
        ],
    ),
    (
        "data-processing-addendum",
        "Data Processing Addendum",
        [
            (("1. Scope",), "heading", "1. Scope"),
            (
                ("1. Scope",),
                "paragraph",
                "This addendum applies to all personal data processed on behalf of the "
                "controller, including data held by sub-processors.",
            ),
            (("2. Sub-processors",), "heading", "2. Sub-processors"),
            (
                ("2. Sub-processors",),
                "paragraph",
                "The processor must notify the controller thirty (30) days before "
                "engaging a new sub-processor.",
            ),
            (("3. Retention",), "heading", "3. Retention"),
            (
                ("3. Retention",),
                "paragraph",
                "Personal data must not be retained beyond thirty-six (36) months from "
                "collection unless a statutory obligation requires otherwise.",
            ),
        ],
    ),
    (
        "service-level-agreement",
        "Service Level Agreement",
        [
            (("1. Uptime",), "heading", "1. Uptime"),
            (
                ("1. Uptime",),
                "paragraph",
                "The service is available 99.9% of the time per calendar month, "
                "excluding scheduled maintenance windows notified five days in advance.",
            ),
            (("2. Support Response",), "heading", "2. Support Response"),
            (
                ("2. Support Response",),
                "paragraph",
                "Priority 1 incidents receive an initial response within thirty (30) "
                "minutes; Priority 3 incidents within two business days.",
            ),
            (("3. Credits",), "heading", "3. Credits"),
            (
                ("3. Credits",),
                "paragraph",
                "Failure to meet the uptime target entitles the customer to a service "
                "credit of 10% of monthly fees per full percentage point missed.",
            ),
        ],
    ),
    (
        "security-policy",
        "Security Policy",
        [
            (("1. Access Control",), "heading", "1. Access Control"),
            (
                ("1. Access Control",),
                "paragraph",
                "Access follows least privilege. Privileged access is reviewed every "
                "quarter and revoked within 24 hours of a role change.",
            ),
            (("2. Encryption",), "heading", "2. Encryption"),
            (
                ("2. Encryption",),
                "paragraph",
                "Data is encrypted at rest with AES-256 and in transit with TLS 1.3. "
                "Keys rotate every 90 days.",
            ),
            (("3. Incident Response",), "heading", "3. Incident Response"),
            (
                ("3. Incident Response",),
                "paragraph",
                "Confirmed breaches are escalated to the security lead immediately and "
                "reported to the regulator within 72 hours.",
            ),
        ],
    ),
    (
        "expense-policy",
        "Expense Policy",
        [
            (("1. Reimbursement",), "heading", "1. Reimbursement"),
            (
                ("1. Reimbursement",),
                "paragraph",
                "Expense claims must be submitted within 30 days of the expense date, "
                "with itemised receipts attached.",
            ),
            (("2. Approval Limits",), "heading", "2. Approval Limits"),
            (
                ("2. Approval Limits",),
                "paragraph",
                "Individual expenses above 50,000 require written approval from a "
                "director before the commitment is made.",
            ),
            (("3. Travel",), "heading", "3. Travel"),
            (
                ("3. Travel",),
                "paragraph",
                "Economy class is standard for flights under six hours; premium economy "
                "is permitted beyond that.",
            ),
        ],
    ),
    (
        "procurement-policy",
        "Procurement Policy",
        [
            (("1. Thresholds",), "heading", "1. Thresholds"),
            (
                ("1. Thresholds",),
                "paragraph",
                "Purchases above 500,000 require three competitive quotes and a "
                "business case approved by the procurement committee.",
            ),
            (("2. Vendor Onboarding",), "heading", "2. Vendor Onboarding"),
            (
                ("2. Vendor Onboarding",),
                "paragraph",
                "New vendors complete a security questionnaire and a sanctions check "
                "before any contract is signed.",
            ),
            (("3. Renewals",), "heading", "3. Renewals"),
            (
                ("3. Renewals",),
                "paragraph",
                "Contracts must be reviewed 90 days before expiry to decide whether to "
                "renew, renegotiate or terminate.",
            ),
        ],
    ),
]


def build_blocks() -> list[Block]:
    """Expand the raw corpus into indexed blocks, in document order."""
    blocks: list[Block] = []
    for doc_id, title, sections in _RAW_CORPUS:
        for index, (path, kind, text) in enumerate(sections, start=1):
            blocks.append(
                Block(
                    block_id=f"{doc_id}#{index}",
                    doc_id=doc_id,
                    doc_title=title,
                    path=path,
                    kind=kind,
                    text=text,
                )
            )
    return blocks


class BM25:
    """Okapi BM25 over a fixed list of documents (here: blocks)."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.docs = docs
        self.size = len(docs)
        self.avg_len = sum(len(d) for d in docs) / max(1, self.size)
        self.term_freqs = [Counter(d) for d in docs]

        doc_freq: Counter[str] = Counter()
        for doc in docs:
            doc_freq.update(set(doc))
        self.idf = {
            term: math.log(1 + (self.size - freq + 0.5) / (freq + 0.5))
            for term, freq in doc_freq.items()
        }

    def scores(self, query: str) -> list[float]:
        terms = tokenize(query)
        results: list[float] = []
        for index, freqs in enumerate(self.term_freqs):
            length = len(self.docs[index])
            total = 0.0
            for term in terms:
                count = freqs.get(term)
                if not count:
                    continue
                norm = self.k1 * (1 - self.b + self.b * length / max(1.0, self.avg_len))
                total += self.idf.get(term, 0.0) * (count * (self.k1 + 1)) / (count + norm)
            results.append(total)
        return results


class DocumentStore:
    """The corpus plus its index: what the tools actually query."""

    def __init__(self, blocks: list[Block] | None = None) -> None:
        self.blocks = blocks if blocks is not None else build_blocks()
        self._by_id = {b.block_id: b for b in self.blocks}
        # Index body text together with the section path, so a query naming a
        # section still matches blocks whose body never repeats the heading.
        self._bm25 = BM25([tokenize(f"{b.text} {b.citation}") for b in self.blocks])

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Ranked blocks for a query, best first."""
        scores = self._bm25.scores(query)
        ranked = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[dict] = []
        for index in ranked[:limit]:
            if scores[index] <= 0:
                continue
            block = self.blocks[index]
            hits.append(
                {
                    "block_id": block.block_id,
                    "citation": block.citation,
                    "kind": block.kind,
                    "score": round(scores[index], 4),
                    "snippet": block.text[:180],
                }
            )
        return hits

    def get(self, block_id: str) -> Block | None:
        return self._by_id.get(block_id)

    def outline(self) -> list[dict]:
        """Every document with its sections, for orienting a reader."""
        docs: dict[str, dict] = {}
        for block in self.blocks:
            entry = docs.setdefault(
                block.doc_id,
                {"doc_id": block.doc_id, "title": block.doc_title, "sections": []},
            )
            section = " > ".join(block.path)
            if section not in entry["sections"]:
                entry["sections"].append(section)
        return list(docs.values())
