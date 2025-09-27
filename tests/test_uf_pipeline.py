from __future__ import annotations
from pathlib import Path

from backend.pipeline.uf_pipeline import run_pipeline


class _FakeLLM:
    async def chat(self, messages, **kwargs):  # pragma: no cover - exercised via asyncio.run
        return {
            "json": {
                "headers": [
                    {
                        "level": 1,
                        "label": "1)",
                        "text": "Scope",
                        "page": 1,
                        "confidence": 0.92,
                    },
                    {
                        "level": 1,
                        "label": "A1.",
                        "text": "Appendix",
                        "page": 1,
                        "confidence": 0.85,
                    },
                ]
            }
        }


def test_run_pipeline_builds_chunks_and_headers(tmp_path):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n% placeholder")

    csv_path = tmp_path / "table.csv"
    csv_path.write_text("Item,Value\nSpeed,120 m/s\n", encoding="utf-8")

    layout = {
        "pages_linear": ["1) Scope\nA1. Appendix\nThe system shall operate at 120 m/s."],
        "pages_lines": [["1) Scope", "A1. Appendix", "The system shall operate at 120 m/s."]],
        "page_line_styles": [
            [
                {"font_size": 13, "bold": True, "bbox": [10, 10, 200, 28]},
                {"font_size": 12, "bold": True, "bbox": [10, 40, 220, 56]},
                {"font_size": 10, "bbox": [10, 70, 400, 86]},
            ]
        ],
        "layout_blocks": [
            {"page": 1, "bbox": [10, 10, 200, 28], "text": "1) Scope"},
            {"page": 1, "bbox": [10, 40, 220, 56], "text": "A1. Appendix"},
        ],
        "tables": [
            {"page": 1, "index": 0, "csv": str(csv_path), "rows": 2},
        ],
    }

    result = run_pipeline(
        str(pdf_path),
        doc_id="doc-1",
        session_id="session-1",
        sidecar_dir=tmp_path,
        llm_client=_FakeLLM(),
        pre_extracted=layout,
    )

    assert result.uf_chunks, "Expected UF chunks to be generated"
    assert result.headers.headers, "Verified headers should not be empty"
    assert result.headers.pages and result.headers.pages[0]["headers"], "Page headers should be grouped"
    assert result.tables and result.tables[0]["parameter_supports"], "Table linking should provide supporters"
    assert result.retrieval.micro_index_size == len(result.uf_chunks)

    summary = result.summary()
    assert summary["chunk_count"] == len(result.uf_chunks)
    assert summary["header_count"] == len(result.headers.headers)

    for key, path in result.artifacts.items():
        assert Path(path).exists(), f"artifact {key} should exist"

    repeat = run_pipeline(
        str(pdf_path),
        doc_id="doc-1",
        session_id="session-1",
        sidecar_dir=tmp_path,
        llm_client=_FakeLLM(),
        pre_extracted=layout,
    )

    assert [chunk["micro_id"] for chunk in repeat.uf_chunks] == [
        chunk["micro_id"] for chunk in result.uf_chunks
    ], "UF chunk ordering should be deterministic"
    assert repeat.summary() == summary, "Pipeline summaries should remain stable across runs"

    header_audit = result.audits.get("headers")
    assert header_audit, "Header audit payload should be populated"
    assert header_audit.get("heuristic_candidates"), "Heuristic candidates should be recorded"
    assert header_audit.get("llm", {}).get("payload"), "LLM payload should include raw response data"
    verification_rows = header_audit.get("verification") or []
    verified_rows = [row for row in verification_rows if row.get("result") == "verified"]
    assert verified_rows, "Verification audit should include verified rows"
    for row in verified_rows:
        assert "score_breakdown" in row and "score_total" in row, "Verified rows must include scoring details"

