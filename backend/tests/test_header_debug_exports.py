import copy
import json
from pathlib import Path

import pytest

from backend.parse.header_config import CONFIG
from backend.parse.header_page_mode import (
    write_page_debug,
    write_header_debug_manifest,
)


@pytest.mark.parametrize("llm_selected", [[{"line_idx": 0, "section_name": "Scope", "section_number": "A1"}]])
def test_header_debug_analysis_and_manifest(tmp_path, llm_selected):
    prev_debug = CONFIG.get("debug")
    prev_dir = CONFIG.get("debug_dir")
    CONFIG["debug"] = True
    CONFIG["debug_dir"] = str(tmp_path)

    try:
        candidates = [
            {"line_idx": 0, "text": "A1 Scope", "style": {"font_size": 14, "bold": True}},
            {"line_idx": 1, "text": "A5 Optional Header", "style": {"font_size": 12}},
            {"line_idx": 2, "text": "Random paragraph text", "style": {}},
        ]
        page_text = "\n".join(cand["text"] for cand in candidates)

        write_page_debug(
            "doc-123",
            0,
            page_text,
            copy.deepcopy(candidates),
            llm_prompt="prompt",
            llm_json=llm_selected,
        )

        page_dir = Path(tmp_path) / "doc-123" / "page_0000"
        analysis_path = page_dir / "analysis.json"
        assert analysis_path.exists()

        analysis = json.loads(analysis_path.read_text())
        assert isinstance(analysis, list) and analysis
        first = analysis[0]
        assert "score" in first and "line_idx" in first
        assert first["line_idx"] == 0
        assert first["llm_selected"] is True
        assert any(item["line_idx"] == 1 for item in analysis)

        snapshots = [(0, copy.deepcopy(candidates), page_text)]
        results = [
            {
                "page": 1,
                "headers": [
                    {
                        "line_idx": 0,
                        "text": "A1 Scope",
                        "section_number": "A1",
                        "score": 3.1,
                        "level": 2,
                    }
                ],
            }
        ]
        write_header_debug_manifest(
            "doc-123",
            snapshots,
            results,
            llm_selections={0: llm_selected},
        )

        manifest_path = Path(tmp_path) / "doc-123" / "index.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["pages"][0]["llm_selected"] == [0]
        assert manifest["pages"][0]["final_headers"][0]["line_idx"] == 0
        assert manifest["pages"][0]["top_candidates"][0]["line_idx"] == 0
    finally:
        CONFIG["debug"] = prev_debug
        CONFIG["debug_dir"] = prev_dir
