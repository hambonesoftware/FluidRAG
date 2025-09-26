from fluidrag.backend.core.sectioning.header_features import compute_features
from fluidrag.backend.core.sectioning.header_match import classify_line
from fluidrag.backend.core.sectioning.header_score import THRESHOLD, score_candidate
from fluidrag.backend.core.sectioning.header_select import select_headers


def _units_present(text: str) -> bool:
    return any(token in text for token in ("mm", "psi", "°C", " A", " V", " rpm", " Hz"))


def _line(text: str, **kwargs):
    base = {
        "page": 1,
        "line_idx": 1,
        "text_norm": text,
        "caps_ratio": kwargs.get("caps_ratio", 0.6),
    }
    base.update({key: kwargs[key] for key in ("bold", "font_sigma_rank", "font_size", "font_size_z") if key in kwargs})
    features = compute_features({"text_norm": text, **kwargs}, [("SEC.PERFORMANCE", 0.8)])
    base["features"] = features
    return base


def test_numeric_header_detects_and_scores():
    line = _line("3) Performance Requirements", bold=True, font_sigma_rank=0.9, font_size_z=0.85)
    cls = classify_line(line["text_norm"], line["caps_ratio"])
    assert cls["kind"] == "numeric"
    score, _ = score_candidate(cls["kind"], line["features"])
    assert score >= THRESHOLD


def test_appendix_header_unicode_variants():
    line_a5 = _line("A5. Utilities & Consumption", bold=True, font_sigma_rank=0.88, font_size_z=0.83)
    line_a6 = _line("A6. Performance", bold=True, font_sigma_rank=0.87, font_size_z=0.81)
    selected = select_headers([line_a5, line_a6], _units_present)
    texts = {entry["text_norm"] for entry in selected}
    assert texts == {"A5. Utilities & Consumption", "A6. Performance"}


def test_label_caps_fallback_rejects_sentences():
    line = _line("specified orientation.", bold=False, font_sigma_rank=0.2, font_size_z=0.1, caps_ratio=0.1)
    selected = select_headers([line], _units_present)
    assert selected == []


def test_no_promote_under_threshold():
    line = _line(
        "Residual discussion",
        bold=False,
        font_sigma_rank=0.1,
        font_size_z=0.1,
        caps_ratio=0.3,
    )
    # Ensure prototype assist is negligible so the score remains below the gate.
    line["features"]["proto_sim_max"] = 0.05
    line["features"]["p_header"] = 0.0
    selected = select_headers([line], _units_present)
    assert selected == []


def test_units_penalty_not_applied_to_numeric():
    line = _line("10) Pressure (psi) Requirements", bold=True, font_sigma_rank=0.9, font_size_z=0.86)
    selected = select_headers([line], _units_present)
    assert selected[0]["partials"].get("units_penalty") is None
    assert selected[0]["partials"].get("units_penalty_applied") is False


def test_label_units_penalty_applies():
    line = _line("UTILITIES PRESSURE 45 PSI", bold=False, font_sigma_rank=0.4, font_size_z=0.3, caps_ratio=0.9)
    line["features"]["proto_sim_max"] = 0.0
    line["features"]["p_header"] = 0.0
    selected = select_headers([line], _units_present)
    # Label should be rejected after penalty drops score below threshold.
    assert selected == []


def test_units_penalty_skipped_for_unicode_appendix():
    text = "A5․ Utilities 45 psi"
    line = _line(text, bold=True, font_sigma_rank=0.92, font_size_z=0.88, caps_ratio=0.82)
    selected = select_headers([line], _units_present)
    assert selected
    assert selected[0]["partials"].get("units_penalty") is None
    assert selected[0]["partials"].get("units_penalty_applied") is False


def test_numeric_fallback_requires_bold_or_sigma():
    line = _line("12) Flow Requirements", bold=False, font_sigma_rank=0.6, font_size_z=0.2)
    line["features"]["proto_sim_max"] = 0.0
    line["features"]["p_header"] = 0.0
    selected = select_headers([line], _units_present)
    assert selected
    assert selected[0]["decision"] == "selected_fallback"
    assert selected[0]["meets_threshold"] is False


def test_prototype_similarity_lifts_ocr_header():
    line = _line("12) Acceptance", bold=False, font_sigma_rank=0.2, font_size_z=0.1)
    line["features"]["proto_sim_max"] = 0.95
    line["features"]["p_header"] = 0.9
    selected = select_headers([line], _units_present)
    assert selected
    assert selected[0]["score"] >= THRESHOLD
