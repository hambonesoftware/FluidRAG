from __future__ import annotations

from dataclasses import asdict

from ...contracts.chunking import Chunk
from ...contracts.headers import Header
from ...contracts.ingest import NormalizedText
from ...contracts.parsing import ParsedDocument, TextBlock
from ...contracts.passes import PassResult, RetrievalHit


def test_contract_shapes() -> None:
    normalized = NormalizedText(doc_id="doc", text="text", pages=["text"], meta={"source": "test"})
    assert normalized.doc_id == "doc"

    block = TextBlock(page=1, content="hello", language="en", order=0)
    parsed = ParsedDocument(doc_id="doc", texts=[block], tables=[], images=[], links=[], meta={})
    assert parsed.texts[0].content == "hello"

    chunk = Chunk(doc_id="doc", chunk_id="doc-1", text="content", start=0, end=7, features={"uppercase_ratio": 0.1})
    header = Header(title="1 Overview", level=1, start_chunk="doc-1", end_chunk="doc-1", confidence=0.8)
    assert header.title.startswith("1")

    hit = RetrievalHit(chunk_id="doc-1", score=0.5, text="content", metadata={})
    rag_pass = PassResult(name="mechanical", hits=[hit], answer={"text": "ok"})
    assert rag_pass.hits[0].score == 0.5

    assert asdict(chunk)["chunk_id"] == "doc-1"
