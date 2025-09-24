from __future__ import annotations

from fluidrag.config import load_config
from fluidrag.src.chunking.standard import StandardChunker
from fluidrag.src.retrieval.search import search_standard
from fluidrag.src.scoring.features import compute_scores


TEXT = """
1. Overview
This section provides an overview of the control system.

2. Requirements
The supplier shall provide UL 508A certified panels with NFPA 79 compliance.
"""


def test_stage_views_vary_results():
    config = load_config()
    chunker = StandardChunker()
    chunks = chunker.chunk_text(TEXT, "doc.txt", "doc")
    compute_scores(chunks, config)
    standard_hits = search_standard("control system overview", chunks, config, view="standard", topk=5)
    fluid_hits = search_standard("control system overview", chunks, config, view="fluid", topk=5)
    hep_hits = search_standard("NFPA 79 compliance", chunks, config, view="hep", topk=5)
    assert standard_hits
    # Fluid view should not return more hits than standard view and may exclude HEP oriented chunks
    assert len(fluid_hits) <= len(standard_hits)
    if hep_hits:
        assert all(hit.chunk.scores["hep_above_threshold"] for hit in hep_hits)
