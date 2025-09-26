from fluidrag.backend.core.extraction.atomic_spans import extract_atomic
from fluidrag.backend.core.extraction.dedupe import dedupe
from fluidrag.backend.core.validators.conflicts import find_conflicts
from fluidrag.backend.core.validators.inequalities import extract_inequalities, normalize_op
from fluidrag.backend.core.validators.ranges import within_range
from fluidrag.backend.core.validators.units import dimension_sanity, parse_units


def test_units_and_ops_parsed():
    parsed = parse_units("SCCR shall be ≥ 65 kA at 480 VAC.")
    assert parsed["value"] == 65
    assert parsed["unit"].lower() in {"ka", "vac"}
    assert normalize_op(parsed["op"]) in {"≥", "="}
    assert dimension_sanity(parsed["unit"])


def test_units_tolerance_and_range_detection():
    tol = parse_units("Maintain 24 VDC ± 1 V")
    assert tol["tol"] == 1.0
    assert tol["unit"].lower() in {"vdc", "v"}

    rng = parse_units("Operate between 50-60 psi under load")
    assert rng["range"] == (50.0, 60.0)
    assert rng["unit"].lower() == "psi"


def test_extract_inequalities():
    ops = extract_inequalities("Pressure shall be >= 50 psi and <= 80 psi")
    assert ops == [">=", "<="]


def test_within_range():
    assert within_range(60, 50, 80)
    assert not within_range(45, 50, 80)


def test_find_conflicts():
    records = [
        {"component": "Pump", "property": "Pressure", "value": 60, "op": "≥"},
        {"component": "Pump", "property": "Pressure", "value": 50, "op": "≤"},
    ]
    conflicts = find_conflicts(records)
    assert conflicts and conflicts[0]["reason"] == "range_inconsistent"


def test_atomic_extraction_and_dedupe():
    chunk = {
        "section_id": "S1",
        "text": "The system shall provide 24 VDC power. The system shall provide 24 VDC power.",
        "page": 2,
        "offsets": {"start": 0, "end": 80},
    }
    records = extract_atomic(chunk)
    assert len(records) == 2
    deduped = dedupe(records)
    assert len(deduped) == 1
