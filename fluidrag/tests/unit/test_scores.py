from __future__ import annotations

from fluidrag.config import load_config
from fluidrag.src.chunking.standard import Chunk
from fluidrag.src.scoring.features import compute_scores


def _make_chunk(text: str) -> Chunk:
    return Chunk(
        chunk_id="doc:s001",
        document="doc",
        section_number="1",
        section_name="Section",
        page_start=1,
        page_end=1,
        text=text,
    )


def test_scores_within_bounds():
    config = load_config()
    chunks = [_make_chunk("Shall comply with ISO 13849 and provide 65 kA SCCR."), _make_chunk("Narrative overview of the system.")]
    compute_scores(chunks, config)
    for chunk in chunks:
        assert 0.0 <= chunk.scores["fluid_score"] <= 1.0
        assert 0.0 <= chunk.scores["hep_score"] <= 1.0
        assert 0.0 <= chunk.scores["break_score"] <= 1.0


def test_threshold_flags():
    config = load_config()
    chunks = [_make_chunk("Shall comply with ISO 13849 and provide 65 kA SCCR.")]
    compute_scores(chunks, config)
    assert "fluid_above_threshold" in chunks[0].scores
    assert "hep_above_threshold" in chunks[0].scores
