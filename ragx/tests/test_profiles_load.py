import yaml


def test_profiles_schema():
    data = yaml.safe_load(open("ragx/config/profiles.yaml", "r", encoding="utf-8"))
    assert "passes" in data
    for name, profile in data["passes"].items():
        assert "segmentation" in profile
        assert "retrieval" in profile
        assert "fluid_merge" in profile
        assert "hep_scoring" in profile
        assert "graphrag" in profile
        assert "cascade" in profile["retrieval"]
