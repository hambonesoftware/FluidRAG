import pytest

from backend.ragV2.config import CFG
from backend.ragV2.fusion import fuse_scores, intersect_or_tightest_band, zscore
from backend.ragV2.types import EvidenceBand


def test_fuse_scores_weights():
    std = {"a": 0.8, "b": 0.2, "c": 0.5}
    flu = {"a": 0.3, "b": 0.4, "c": 0.5}
    hep = {"a": 0.1, "b": 0.9, "c": 0.5}
    fused = fuse_scores(std, flu, hep)
    std_z = zscore(std)
    flu_z = zscore(flu)
    hep_z = zscore(hep)
    expected_a = (
        CFG.w_std * std_z["a"] + CFG.w_flu * flu_z["a"] + CFG.w_hep * hep_z["a"]
    )
    assert fused["a"].final == pytest.approx(expected_a)
    assert fused["a"].final > fused["b"].final


def test_intersect_or_tightest_band_prefers_intersection():
    band_a = EvidenceBand("seed", 0, 2, 0.9, [], [], "A", ["1", "2", "3"])
    band_b = EvidenceBand("seed", 1, 3, 0.8, [], [], "B", ["2", "3", "4"])
    band_c = EvidenceBand("seed", 0, 1, 0.7, [], [], "C", ["2"])
    chosen = intersect_or_tightest_band([band_a, band_b, band_c], [])
    assert chosen.method == "C"


def test_intersect_or_tightest_band_uses_tightest_when_no_overlap():
    band_a = EvidenceBand("seed", 0, 3, 0.6, [], [], "A", ["1", "2", "3", "4"])
    band_b = EvidenceBand("seed", 0, 1, 0.8, [], [], "B", ["5", "6"])
    chosen = intersect_or_tightest_band([band_a, band_b], [])
    assert chosen.method == "B"
