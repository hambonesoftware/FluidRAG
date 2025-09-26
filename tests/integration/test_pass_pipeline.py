from fluidrag.backend.core.embedding.encoder import EmbeddingEncoder
from fluidrag.backend.core.extraction.atomic_spans import extract_atomic
from fluidrag.backend.core.extraction.dedupe import dedupe
from fluidrag.backend.core.retrieval.chunk_recall import recall_chunks
from fluidrag.backend.core.retrieval.fuse_scores import fuse
from fluidrag.backend.core.retrieval.section_filter import prefilter_sections


def test_pipeline_end_to_end_smoke():
    encoder = EmbeddingEncoder(dim=24)

    sections = [
        {"sec_id": "S000", "title": "Performance", "text": "Section about power requirements."},
        {"sec_id": "S001", "title": "Safety", "text": "Section about safety requirements."},
    ]
    section_vectors = encoder.embed_texts([s["title"] for s in sections])

    chunks_by_section = {
        "S000": encoder.embed_texts(["The system shall provide 24 VDC power."]),
        "S001": encoder.embed_texts(["The guard shall remain closed."]),
    }
    chunk_meta = {
        "S000": [
            {
                "chunk_id": "C000",
                "section_id": "S000",
                "text": "The system shall provide 24 VDC power.",
                "page": 5,
                "offsets": {"start": 0, "end": 40},
                "E": 0.6,
                "F": 0.5,
                "H": 0.4,
            }
        ],
        "S001": [
            {
                "chunk_id": "C001",
                "section_id": "S001",
                "text": "The guard shall remain closed.",
                "page": 6,
                "offsets": {"start": 0, "end": 35},
                "E": 0.2,
                "F": 0.3,
                "H": 0.5,
            }
        ],
    }

    query = encoder.embed_texts(["Performance power requirements"])[0]
    top_sections = prefilter_sections(query, section_vectors, sections, top_m=2)
    assert top_sections[0]["sec_id"] == "S000"

    chunks = recall_chunks(query, {sec["sec_id"]: chunks_by_section[sec["sec_id"]] for sec in top_sections}, chunk_meta, top_kprime=5)
    weights = {"alpha": 0.5, "beta": 0.2, "gamma": 0.2, "delta": 0.1}
    for candidate in chunks:
        candidate["fused"] = fuse(candidate["S"], candidate.get("E", 0), candidate.get("F", 0), candidate.get("H", 0), weights)

    chunks.sort(key=lambda item: -item["fused"])
    chosen = chunks[:2]
    extractions = dedupe([record for chunk in chosen for record in extract_atomic(chunk, section_hint="Performance")])
    assert extractions
    assert any(record.get("unit") for record in extractions)
