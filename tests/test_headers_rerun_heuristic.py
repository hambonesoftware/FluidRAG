from flask import Flask

from backend.state import PIPELINE_STATES, PipelineState
from backend.routes import headers as headers_route


def test_determine_headers_heuristic_only(monkeypatch, tmp_path):
    session_id = "session123"
    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    pdf_path = uploads_dir / f"{session_id}.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setenv("UPLOAD_FOLDER", str(uploads_dir))

    state = PipelineState(
        tmpdir=str(tmp_path),
        filename="doc.pdf",
        file_path=str(pdf_path),
    )
    state.file_hash = "hash123"
    PIPELINE_STATES[session_id] = state

    layout = {
        "pages_linear": [
            "Header A\\nBody text\\n",
            "Header B\\nMore text\\n",
        ],
        "pages_lines": [
            ["Header A", "Body text"],
            ["Header B", "More text"],
        ],
        "page_line_styles": [
            [{"font_size": 14}, {"font_size": 11}],
            [{"font_size": 14}, {"font_size": 11}],
        ],
    }

    def fake_extract_pages_with_layout(*args, **kwargs):
        return layout

    def fake_select_candidates(lines, styles):
        return [
            {
                "line_idx": 0,
                "text": lines[0],
                "section_number": "1" if "A" in lines[0] else "2",
                "level": 1,
                "score": 3.5,
                "style": styles[0] if styles else {},
            }
        ]

    def fake_sections_from_headers(pages_lines, detected):
        sections = []
        for page_block in detected:
            page = page_block.get("page")
            headers = page_block.get("headers") or []
            if not page or not headers:
                continue
            header = headers[0]
            page_index = page - 1
            body_lines = pages_lines[page_index]
            section_text = body_lines[0]
            content = [section_text]
            if len(body_lines) > 1:
                content.append(body_lines[1])
            sections.append(
                {
                    "title": header.get("text", section_text),
                    "id": header.get("section_number") or str(len(sections) + 1),
                    "section_number": header.get("section_number") or "",
                    "content": content,
                    "page_start": page,
                    "heading_level": header.get("level"),
                }
            )
        return sections

    monkeypatch.setattr(headers_route, "extract_pages_with_layout", fake_extract_pages_with_layout)
    monkeypatch.setattr(headers_route, "select_candidates", fake_select_candidates)
    monkeypatch.setattr(headers_route, "_sections_from_detected_headers", fake_sections_from_headers)
    monkeypatch.setattr(headers_route, "get_headers_cache", lambda *_: None)
    monkeypatch.setattr(headers_route, "save_headers_cache", lambda *_, **__: None)
    monkeypatch.setattr(headers_route, "clear_headers_cache", lambda *_, **__: None)
    monkeypatch.setattr(headers_route, "dump_appendix_audit", lambda *_, **__: None)
    monkeypatch.setattr(headers_route, "write_header_debug_manifest", lambda *_, **__: None)
    monkeypatch.setattr(headers_route, "write_page_debug", lambda *_, **__: None)

    app = Flask(__name__)
    app.register_blueprint(headers_route.bp)

    try:
        with app.test_client() as client:
            response = client.post(
                "/api/determine-headers",
                json={"session_id": session_id, "force_refresh": True},
            )
        assert response.status_code == 200
        payload = response.get_json()
        assert payload["ok"] is True
        debug = payload.get("debug", {})
        heuristics = debug.get("heuristics")
        assert heuristics["heuristic_only"] is True
        assert "llm_debug" not in debug
        assert payload["cache"]["hit"] is False
        assert payload["sections"] == 2
        assert len(payload.get("preview", [])) == 2
        assert PIPELINE_STATES[session_id].headers is not None
    finally:
        PIPELINE_STATES.pop(session_id, None)
