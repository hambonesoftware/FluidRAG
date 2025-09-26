import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chunking.efhg import compute_chunk_scores, run_efhg


def _chunk(text: str, section: str | None = None, modal: bool = True) -> dict:
    lex = {
        "modal_flags": ["shall"] if modal else [],
        "numbers": ["95"] if "95" in text else [],
        "units": ["psi"] if "psi" in text.lower() else [],
        "citation_hint": "api" in text.lower(),
    }
    return {
        "text": text,
        "norm_text": text,
        "page": 2,
        "section_id": section,
        "lex": lex,
        "style": {"indent": 12.0},
    }


def test_compute_chunk_scores_returns_entropy_and_modalness():
    chunks = [_chunk("The system shall maintain 95 psi pressure."), _chunk("Notes and clarifications.", modal=False)]
    scores = compute_chunk_scores(chunks)
    assert len(scores) == 2
    assert scores[0]["S_start"] > scores[1]["S_start"]
    assert scores[0]["modalness"] >= scores[1]["modalness"]


def test_run_efhg_returns_scored_spans():
    chunks = [
        _chunk("1) Scope and purpose.", section="1"),
        _chunk("The controller shall maintain 95 psi in the accumulator."),
        _chunk("Sensors must report diagnostics every 10 s."),
        _chunk("Narrative paragraph without obligations.", modal=False),
    ]
    spans = run_efhg(chunks)
    assert spans, "EFHG should return at least one span"
    top = spans[0]
    assert top["score"] >= top["H"]
    assert 0 <= top["start_index"] <= top["end_index"]
