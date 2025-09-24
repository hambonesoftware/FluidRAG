from backend.ragV2.config import CFG
from backend.ragV2.entropy import (
    entropy_changepoint_band,
    entropy_graph_band,
    entropy_linear_band,
)
from backend.ragV2.graph import GraphIndex
from backend.ragV2.types import Chunk


def _chunk(idx: int, text: str) -> Chunk:
    return Chunk(
        chunk_id=f"c{idx}",
        doc_id="d1",
        section_no="1",
        section_title="Intro",
        page_range=(idx, idx + 1),
        text=text,
    )


def test_entropy_linear_band_stops_on_high_entropy():
    ordered = [_chunk(i, "low variance text") for i in range(3)]
    ordered.append(_chunk(3, "diverse tokens alpha beta gamma"))
    band = entropy_linear_band(0, ordered)
    assert band.end_idx < len(ordered) - 1


def test_entropy_graph_band_collects_neighbors():
    ordered = [_chunk(i, f"node {i} data") for i in range(3)]
    graph = GraphIndex()
    graph.build_from_edges([
        ("c0", "c1", 0.9),
        ("c1", "c2", 0.85),
    ])
    band = entropy_graph_band(ordered[0], ordered, graph)
    assert set(band.band_chunk_ids) >= {"c0", "c1"}


def test_entropy_changepoint_band_respects_change():
    ordered = [
        _chunk(0, "repeat repeat repeat"),
        _chunk(1, "repeat repeat repeat"),
        _chunk(2, "new tokens appear everywhere"),
    ]
    band = entropy_changepoint_band(0, ordered)
    assert band.end_idx <= 1
