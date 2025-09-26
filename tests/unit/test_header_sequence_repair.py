from pathlib import Path

import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from backend.parse.header_sequence_repair import aggressive_sequence_repair


def _header(label: str, text: str, page: int, page_texts: list[str]) -> dict:
    blob = page_texts[page - 1]
    target = f"{label} {text}".replace(" .", ".")
    start = blob.find(target)
    if start < 0:
        start = 0
    return {
        "label": label,
        "text": text,
        "page": page,
        "span": (start, start + len(target)),
    }


def test_repair_fills_appendix_gap():
    page_texts = [
        "",
        "",
        "",
        "",
        "",
        "A3. Instrumentation\nA4. Control Panels\nA5. Utilities & Consumption\nA6. Performance",  # page 6
        "A7. Warranty\nA8. Training",  # page 7
    ]
    verified = [
        _header("A3.", "Instrumentation", 6, page_texts),
        _header("A4.", "Control Panels", 6, page_texts),
        _header("A7.", "Warranty", 7, page_texts),
        _header("A8.", "Training", 7, page_texts),
    ]

    merged, repairs = aggressive_sequence_repair(verified, page_texts)

    labels = [header["label"] for header in merged]
    assert "A5." in labels
    assert "A6." in labels
    assert len(repairs) == 2
    confidences = {rep["label"]: rep["confidence"] for rep in repairs}
    assert confidences["A5."] >= 0.5
    assert confidences["A6."] >= 0.5


def test_repair_skips_when_text_missing():
    page_texts = ["", "A1. Scope", "A4. Drawings"]
    verified = [
        _header("A1.", "Scope", 2, page_texts),
        _header("A4.", "Drawings", 3, page_texts),
    ]

    merged, repairs = aggressive_sequence_repair(verified, page_texts)
    assert merged == verified
    assert repairs == []


def test_soft_unwrap_repairs_wrapped_header():
    page_texts = [
        "", "", "", "", "",
        "A3. Instrumentation\nA4. Control Panels\nA5.\nUtilities & Consumption\nA6. Performance",
        "A7. Warranty\nA8. Training",
    ]
    verified = [
        _header("A3.", "Instrumentation", 6, page_texts),
        _header("A4.", "Control Panels", 6, page_texts),
        _header("A7.", "Warranty", 7, page_texts),
        _header("A8.", "Training", 7, page_texts),
    ]

    merged, repairs = aggressive_sequence_repair(verified, page_texts)

    labels = [header["label"] for header in merged]
    assert "A5." in labels
    wrapped = next(rep for rep in repairs if rep["label"] == "A5.")
    assert wrapped["text"].lower() == "utilities & consumption"
    assert wrapped["provenance"]["search"] == "soft_unwrap"
