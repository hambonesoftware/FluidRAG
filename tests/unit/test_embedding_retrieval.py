import numpy as np

from fluidrag.backend.core.embedding.encoder import EmbeddingEncoder
from fluidrag.backend.core.retrieval.chunk_recall import recall_chunks
from fluidrag.backend.core.retrieval.fuse_scores import fuse
from fluidrag.backend.core.retrieval.section_filter import prefilter_sections


def test_embed_shape_and_normalization():
    encoder = EmbeddingEncoder(dim=32)
    vectors = encoder.embed_texts(["alpha", "beta", "gamma"])
    assert vectors.shape == (3, 32)
    norms = np.linalg.norm(vectors, axis=1)
    assert np.allclose(norms, 1.0, atol=1e-6)


def test_section_prefilter_recalls_relevant_sections():
    encoder = EmbeddingEncoder(dim=16)
    texts = ["Performance requirements", "Safety requirements", "Appendix"]
    section_vectors = encoder.embed_texts(texts)
    query = section_vectors[0]
    meta = [{"sec_id": f"S{i:03d}"} for i in range(len(texts))]
    top = prefilter_sections(query, section_vectors, meta, top_m=2)
    assert top[0]["sec_id"] == "S000"


def test_chunk_recall_scoped_to_sections():
    encoder = EmbeddingEncoder(dim=8)
    section_a = encoder.embed_texts(["Chunk A1", "Chunk A2"])
    section_b = encoder.embed_texts(["Chunk B1", "Chunk B2"])
    query = encoder.embed_texts(["Chunk A1"])[0]
    meta = {
        "S1": [{"chunk_id": "C1"}, {"chunk_id": "C2"}],
        "S2": [{"chunk_id": "C3"}, {"chunk_id": "C4"}],
    }
    candidates = recall_chunks(query, {"S1": section_a, "S2": section_b}, meta, top_kprime=3)
    assert all(candidate["section_id"] in {"S1", "S2"} for candidate in candidates)
    assert candidates[0]["section_id"] == "S1"


def test_fusion_respects_weights():
    weights = {"alpha": 0.5, "beta": 0.3, "gamma": 0.1, "delta": 0.1}
    fused_a = fuse(0.6, 0.9, 0.2, 0.1, weights)
    fused_b = fuse(0.6, 0.1, 0.9, 0.9, weights)
    assert fused_a > fused_b


def test_selection_limits_per_section():
    candidates = [
        {"section_id": "S1", "fused": 0.9},
        {"section_id": "S1", "fused": 0.8},
        {"section_id": "S1", "fused": 0.7},
        {"section_id": "S2", "fused": 0.85},
        {"section_id": "S3", "fused": 0.5},
    ]
    result = []
    per_section_cap = 2
    for candidate in sorted(candidates, key=lambda item: -item["fused"]):
        if sum(1 for item in result if item["section_id"] == candidate["section_id"]) >= per_section_cap:
            continue
        result.append(candidate)
    assert all(sum(1 for item in result if item["section_id"] == sid) <= per_section_cap for sid in {"S1", "S2", "S3"})
