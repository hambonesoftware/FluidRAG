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
    assert data["doc_meta"]["doc_id"] == "doc-1"
    assert (
        data["header_pass"]["llm"]["prompt_used"]
        == "Please list all header sections of this document and provide the results in a json format"
    )
    assert data["header_pass"]["llm"]["parse_error"] is None

    final = result["final_headers"]
    assert len(final) == 1
    assert final[0].title.lower().startswith("introduction")
    assert final[0].sources == ["heuristic", "llm"]


def test_pipeline_handles_llm_parse_error(tmp_path, monkeypatch):
    heuristics = [
        {
            "text": "1 Scope",
            "page": 1,
            "font_size": 13.5,
            "is_bold": True,
            "level": 1,
            "level_numbering": 1,
            "level_font": 1,
        }
    ]

    monkeypatch.setattr(llm_header_pass, "call_llm", lambda _text: "not json")

    audit_path = tmp_path / "Epf_Co.preprocess.json"
    result = run_header_pipeline(
        "1 Scope\nBody text",
        heuristics,
        doc_meta={"doc_id": "doc-parse-error"},
        audit_path=str(audit_path),
    )

    assert audit_path.exists()
    data = json.loads(audit_path.read_text(encoding="utf-8"))
    llm_block = data["header_pass"]["llm"]
    assert llm_block["raw_response"] == "not json"
    assert llm_block["parse_error"]
    assert llm_block["prompt_used"] == "Please list all header sections of this document and provide the results in a json format"

    final_headers = result["final_headers"]
    assert len(final_headers) == 1
    assert final_headers[0].sources == ["heuristic"]
