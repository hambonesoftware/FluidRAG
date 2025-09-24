from __future__ import annotations

from pathlib import Path

from fluidrag.config import load_config
from fluidrag.src.chunking.standard import StandardChunker
from fluidrag.src.graph.build import build_graph
from fluidrag.src.graph.query import augment_with_graph
from fluidrag.src.scoring.features import compute_scores


TEXT = """
1. Standards
Panels shall comply with NFPA 79, IEC 60204-1, and UL 508A for safety and control.
"""


def test_graph_summaries_returned(tmp_path: Path):
    config = load_config()
    chunker = StandardChunker()
    chunks = chunker.chunk_text(TEXT, "doc.txt", "graphdoc")
    compute_scores(chunks, config)
    build_graph("graphdoc", chunks, tmp_path, config)
    context = augment_with_graph("Compare NFPA 79 and IEC 60204-1", "graphdoc", tmp_path)
    assert context is not None
    assert context.summaries
