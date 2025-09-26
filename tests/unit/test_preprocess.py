from fluidrag.backend.core.preprocess.line_segmenter import join_split_lines
from fluidrag.backend.core.preprocess.normalize import normalize_text


def test_normalize_maps_spaces_and_dots():
    raw = "A5.\u00A0Utilities\u2024"
    norm, diff = normalize_text(raw)
    assert norm == "A5. Utilities."
    assert "0020->00A0 at pos 3" in diff
    assert any(entry.startswith("002E->2024") for entry in diff)


def test_normalize_is_idempotent():
    text = "A5. Utilities"
    norm, diff = normalize_text(text)
    assert norm == text
    assert diff == []


def test_line_join_header_prefix():
    lines = [
        {"line_idx": 10, "text_norm": "A5.", "bbox": [0, 0, 10, 10]},
        {"line_idx": 11, "text_norm": "Utilities & Consumption", "bbox": [0, 10, 50, 20]},
    ]
    joined = join_split_lines(lines)
    assert len(joined) == 1
    assert joined[0]["text_norm"] == "A5. Utilities & Consumption"
    assert joined[0]["join_from"] == [10, 11]
    assert joined[0]["bbox"] == [0, 0, 50, 20]


def test_line_split_multiple_headers():
    lines = [{"line_idx": 5, "text_norm": "A5. Utilities A6. Performance"}]
    split = join_split_lines(lines)
    assert len(split) == 2
    assert split[0]["text_norm"].startswith("A5.")
    assert split[1]["text_norm"].startswith("A6.")
    assert split[0]["split_of"] == 5
    assert split[1]["split_of"] == 5
