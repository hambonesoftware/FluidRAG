from __future__ import annotations

from pathlib import Path

from fluidrag.config import load_config
from fluidrag.src.chunking.standard import StandardChunker
from fluidrag.src.graph.build import build_graph
from fluidrag.src.retrieval.search import search_standard
from fluidrag.src.scoring.features import compute_scores


SAMPLE_TEXT = """
1. Scope
The panel shall comply with NFPA 79 for all wiring practices.

2. Ratings
Provide short circuit current rating of 65 kA at 480 V.
"""


def test_end_to_end_pipeline(tmp_path: Path):
    config = load_config()
    chunker = StandardChunker()
    chunks = chunker.chunk_text(SAMPLE_TEXT, "sample.txt", "sample")
    assert chunks, "Chunker should return chunks"
    compute_scores(chunks, config)
    build_graph("sample", chunks, tmp_path, config)
    hits = search_standard("SCCR 65 kA labeling per UL 508A", chunks, config, view="hep", topk=5)
    assert hits, "Retrieval should return hits"
    assert all(hit.chunk.scores["hep_score"] <= 1 for hit in hits)
