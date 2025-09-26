from backend.chunking.token_chunker import (
    MICRO_MAX_TOKENS,
    MICRO_OVERLAP_TOKENS,
    micro_chunks_by_tokens,
)
from backend.retrieval.utils import MAX_CONTEXT_TOKENS, trim_context_snippets


def _total_tokens(snippets):
    from tokens import encode

    return sum(len(encode(snippet)) for snippet in snippets)


def test_micro_chunk_token_limit():
    text = "Lorem ipsum dolor sit amet, " * 1000
    chunks = micro_chunks_by_tokens(text)
    assert chunks, "expected chunks to be produced"
    assert all(chunk["token_count"] <= MICRO_MAX_TOKENS for chunk in chunks)


def test_micro_chunk_overlap_windows():
    text = "A" * (MICRO_MAX_TOKENS * 5)
    chunks = micro_chunks_by_tokens(text)
    spans = [chunk.get("token_span") for chunk in chunks if chunk.get("token_span")]
    assert spans, "expected hard-wrapped spans"
    for first, second in zip(spans, spans[1:]):
        assert first is not None and second is not None
        assert first[1] >= first[0]
        assert second[1] >= second[0]
        assert first[1] - second[0] == MICRO_OVERLAP_TOKENS


def test_trim_context_snippets_respects_budget():
    snippets = ["token budget test " * 200 for _ in range(50)]
    trimmed = trim_context_snippets(snippets)
    assert _total_tokens(trimmed) <= MAX_CONTEXT_TOKENS
    assert len(trimmed) <= len(snippets)
    assert all(trimmed)
