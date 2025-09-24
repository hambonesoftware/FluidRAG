import yaml

from ragx.core.router import pick_profile


def test_router_cascade_configuration():
    profiles = yaml.safe_load(open("ragx/config/profiles.yaml", "r", encoding="utf-8"))
    for ppass, expected in {
        "Mechanical": ["sparse", "dense_hyde", "colbert", "cross"],
        "Electrical": ["sparse", "dense_hyde", "colbert", "cross"],
        "Controls": ["sparse", "dense_hyde", "colbert"],
        "Software": ["sparse", "dense_hyde", "colbert", "cross"],
        "Project Management": ["sparse", "dense_hyde", "colbert"],
    }.items():
        profile = pick_profile(ppass, "RETRIEVE", profiles)
        assert profile["retrieval"]["cascade"] == expected
        assert profile["retrieval"]["colbert_token_boosts"]
