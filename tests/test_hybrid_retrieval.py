import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ingest import microchunk_text
from index import BM25Store, EmbeddingStore
from retrieval import HybridRetriever, rerank_by_section_density


@pytest.fixture
def sample_microchunks():
    parts = [
        {
            "doc_id": "controls",
            "section_id": "11.2",
            "section_title": "FAT Performance",
            "chunk_id": "chunk-fat",
            "text": "The FAT performance demonstration shall confirm 95 percent availability under simulated load. "
            * 12,
        },
        {
            "doc_id": "controls",
            "section_id": "11.2",
            "section_title": "FAT Performance",
            "chunk_id": "chunk-dash",
            "text": "Availability dashboards shall highlight downtime root causes and include MTBF metrics for every station. "
            * 6,
        },
        {
            "doc_id": "controls",
            "section_id": "17.1",
            "section_title": "Evaluation",
            "chunk_id": "chunk-eval",
            "text": "Supplier evaluation will consider maintenance training, spare parts, and documentation quality." * 4,
        },
    ]
    return microchunk_text(parts, size=60, overlap=16)


def test_rrf_improves_recall(tmp_path: Path, sample_microchunks):
    embeddings = EmbeddingStore(tmp_path / "embeddings.parquet")
    embeddings.build(sample_microchunks)
    bm25 = BM25Store(tmp_path / "bm25.idx")
    bm25.build(sample_microchunks)

    micro_index = {chunk["micro_id"]: chunk for chunk in sample_microchunks}
    section_map = {"11.2": [chunk["micro_id"] for chunk in sample_microchunks if chunk["section_id"] == "11.2"]}

    header_docs = [
        {
            "micro_id": "header-000",
            "text": "1) FAT Performance FAT performance demonstration shall confirm 95 percent availability.",
            "norm_text": "1) FAT Performance FAT performance demonstration shall confirm 95 percent availability.",
            "micro_ids": [section_map["11.2"][0]],
        }
    ]
    header_embeddings = EmbeddingStore(tmp_path / "header_embeddings.parquet")
    header_embeddings.build(header_docs)
    header_bm25 = BM25Store(tmp_path / "header_bm25.idx")
    header_bm25.build(header_docs)

    table_docs = [
        {
            "micro_id": "table-000",
            "text": "Speed 120 m/s Availability 95 percent",
            "norm_text": "Speed 120 m/s Availability 95 percent",
            "parameter_supports": [section_map["11.2"][0]],
        }
    ]
    table_embeddings = EmbeddingStore(tmp_path / "table_embeddings.parquet")
    table_embeddings.build(table_docs)
    table_bm25 = BM25Store(tmp_path / "table_bm25.idx")
    table_bm25.build(table_docs)

    span_map = {section_map["11.2"][0]: {"score": 3.5}}

    hybrid = HybridRetriever(
        embeddings=embeddings,
        bm25=bm25,
        micro_index=micro_index,
        section_map=section_map,
        header_embeddings=header_embeddings,
        header_bm25=header_bm25,
        header_docs=header_docs,
        table_embeddings=table_embeddings,
        table_bm25=table_bm25,
        table_docs=table_docs,
        span_map=span_map,
        log_path=tmp_path / "retrieval_log.jsonl",
    )

    query = "FAT performance availability"
    bm25_top = [mid for mid, _ in bm25.search(query, k=1)]
    emb_top = [mid for mid, _ in embeddings.search(query, k=1)]
    fused = hybrid.search(query, k=5)

    chunk_results = [res for res in fused if res["type"] == "chunk"]
    chunk_ids = [res["id"] for res in chunk_results]
    assert emb_top[0] in chunk_ids
    if bm25_top and bm25_top[0] not in emb_top:
        assert bm25_top[0] in chunk_ids
    assert any(res["type"] == "header" for res in fused)
    assert any(res["type"] == "table" for res in fused)
    assert chunk_results and chunk_results[0]["boost"] > 0.0


def test_section_density_rerank_clusters_results(sample_microchunks):
    micro_ids = [chunk["micro_id"] for chunk in sample_microchunks]
    sections = {
        "11.2": [mid for mid in micro_ids if any(
            chunk["micro_id"] == mid and chunk["section_id"] == "11.2" for chunk in sample_microchunks
        )],
        "17.1": [mid for mid in micro_ids if any(
            chunk["micro_id"] == mid and chunk["section_id"] == "17.1" for chunk in sample_microchunks
        )],
    }
    ordered = rerank_by_section_density(micro_ids, sections, topk=3)
    leading = ordered[:2]
    count_section = sum(
        1 for mid in leading for chunk in sample_microchunks if chunk["micro_id"] == mid and chunk["section_id"] == "11.2"
    )
    assert count_section >= 2
