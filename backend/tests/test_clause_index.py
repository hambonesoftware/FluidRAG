from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.indexes.clause_index import ClauseIndex


def build_index() -> ClauseIndex:
    index = ClauseIndex()
    index.put("ISO_10218-1", "5.3.1", "iso-531")
    index.put("29 CFR", "1910.212", "osha-1910-212")
    index.put("NFPA 79", "12.3", "nfpa-123")
    return index


def test_clause_index_variants_resolve():
    index = build_index()
    for query in ["5.3.1", "§5.3.1", "clause 5.3.1"]:
        hits = index.get_any(query)
        assert hits == ["iso-531"]


def test_clause_index_mixed_standard_clause_keys():
    index = build_index()
    assert index.get_any("ISO_10218-1|5.3.1") == ["iso-531"]
    assert index.get_any("ISO 10218-1 §5.3.1") == ["iso-531"]
    assert index.get_any("29 CFR 1910.212") == ["osha-1910-212"]
    assert index.get_any("NFPA 79:12.3") == ["nfpa-123"]
