import json

from backend.headers import llm_header_pass
from backend.headers.preprocess_pipeline import run_header_pipeline


def test_pipeline_writes_audit(tmp_path, monkeypatch):
    heuristics = [
        {
            "text": "1 Introduction",
            "page": 1,
            "font_size": 14.0,
            "is_bold": True,
            "level": 1,
            "level_numbering": 1,
            "level_font": 1,
        }
    ]
    llm_payload = json.dumps(
        [
            {
                "title": "Introduction",
                "page": 1,
                "confidence": 0.9,
                "level": 1,
                "section_id": "1",
            }
        ]
    )

    monkeypatch.setattr(llm_header_pass, "call_llm", lambda _text: llm_payload)

    audit_path = tmp_path / "Epf_Co.preprocess.json"
    result = run_header_pipeline(
        "1 Introduction\nBody text",
        heuristics,
        doc_meta={"doc_id": "doc-1"},
        audit_path=str(audit_path),
    )

    assert audit_path.exists()
    data = json.loads(audit_path.read_text(encoding="utf-8"))
    assert data["header_pass"]["llm"]["candidates"], "LLM candidates missing"
    assert data["header_pass"]["heuristic"]["candidates"], "heuristic candidates missing"
    assert data["header_pass"]["final"]["headers"], "final headers missing"

    final = result["final_headers"]
    assert len(final) == 1
    assert final[0].title.lower().startswith("introduction")
