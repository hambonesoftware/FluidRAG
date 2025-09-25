import copy
import csv
from pathlib import Path

from backend.parse import header_config
from backend.parse.header_page_mode import select_candidates, write_page_debug


def _enable_debug(tmp_path: Path):
    prev = {
        "debug": header_config.CONFIG.get("debug"),
        "debug_dir": header_config.CONFIG.get("debug_dir"),
        "debug_flag": header_config.DEBUG_HEADERS,
        "dir_flag": header_config.DEBUG_DIR,
    }
    header_config.DEBUG_HEADERS = True
    header_config.CONFIG["debug"] = True
    header_config.CONFIG["debug_dir"] = str(tmp_path)
    header_config.DEBUG_DIR = str(tmp_path)
    return prev


def _restore_debug(prev):
    header_config.CONFIG["debug"] = prev["debug"]
    header_config.CONFIG["debug_dir"] = prev["debug_dir"]
    header_config.DEBUG_HEADERS = prev["debug_flag"]
    header_config.DEBUG_DIR = prev["dir_flag"]


def test_precandidate_appendix_variants(tmp_path):
    prev = _enable_debug(tmp_path)
    try:
        lines = [
            "A4. Controls & Electrical",
            "A5. Utilities & Consumption",
            "A6. Performance",
            "A7. Layout",
        ]
        styles = [
            {
                "font_size": 14,
                "bold": True,
                "font_sigma_rank": 2.0,
                "caps_ratio": 0.35,
                "bbox": [10, 10, 200, 20],
            }
            for _ in lines
        ]
        doc_id = "doc123"
        candidates, line_records = select_candidates(
            lines,
            styles,
            doc_id=doc_id,
            page_idx=0,
        )
        snapshot = [copy.deepcopy(c) for c in candidates]
        line_snapshot = [copy.deepcopy(r) for r in line_records]
        page_text = "\n".join(lines)
        write_page_debug(doc_id, 0, page_text, snapshot, line_snapshot)

        debug_dir = Path(tmp_path) / header_config.sanitize_component(doc_id) / "page_0000"
        precand_rows = list(csv.DictReader((debug_dir / "precandidates.csv").open()))
        assert len(precand_rows) == 4
        for row in precand_rows:
            assert row["appendix_regex_hit"] == "True"
            assert row["pre_regex_hits"], "expected regex hits"

        scored_rows = list(csv.DictReader((debug_dir / "candidates_scored.csv").open()))
        assert len(scored_rows) == 4
        by_idx = {int(row["line_idx"]): row for row in scored_rows}
        assert set(by_idx.keys()) == {0, 1, 2, 3}
        assert "units" in (by_idx[1]["disqualifiers"] or "")
        assert "units" in (by_idx[2]["disqualifiers"] or "")
    finally:
        _restore_debug(prev)


def test_unicode_normalization_hits_appendix(tmp_path):
    prev = _enable_debug(tmp_path)
    try:
        lines = ["Ａ５．\u00A0Utilities\u200B"]
        styles = [
            {
                "font_size": 13,
                "bold": True,
                "font_sigma_rank": 1.8,
                "caps_ratio": 0.3,
                "bbox": [20, 20, 220, 40],
            }
        ]
        doc_id = "unicode_doc"
        candidates, line_records = select_candidates(
            lines,
            styles,
            doc_id=doc_id,
            page_idx=0,
        )
        snapshot = [copy.deepcopy(c) for c in candidates]
        line_snapshot = [copy.deepcopy(r) for r in line_records]
        write_page_debug(doc_id, 0, "\n".join(lines), snapshot, line_snapshot)

        debug_dir = Path(tmp_path) / header_config.sanitize_component(doc_id) / "page_0000"
        post_norm = list(csv.DictReader((debug_dir / "lines_post_norm.csv").open()))
        assert post_norm[0]["text_norm"].startswith("A5")

        precand_rows = list(csv.DictReader((debug_dir / "precandidates.csv").open()))
        assert precand_rows[0]["appendix_regex_hit"] == "True"
    finally:
        _restore_debug(prev)


def test_prefilter_ledger_records_drop_reason(tmp_path):
    prev = _enable_debug(tmp_path)
    try:
        lines = ["Indented heading"]
        styles = [
            {
                "font_size": 12,
                "bold": False,
                "font_sigma_rank": 0.5,
                "caps_ratio": 0.2,
                "bbox": [500, 10, 650, 25],
            }
        ]
        doc_id = "left_margin_doc"
        select_candidates(lines, styles, doc_id=doc_id, page_idx=0)

        ledger_path = (
            Path(tmp_path)
            / header_config.sanitize_component(doc_id)
            / "page_0000"
            / "prefilter_ledger.csv"
        )
        rows = list(csv.DictReader(ledger_path.open()))
        assert rows[0]["drop_reason"].startswith("left_margin")
    finally:
        _restore_debug(prev)
