import json
import hashlib
from pathlib import Path

from chunking.evaluate import load_config, run_evaluation

EXPECTED_HASHES = {
    "rfq_alpha::baseline:baseline": "df9cc53b8b9f3399f960ba49904477ed81116631",
    "rfq_bravo::baseline:baseline": "d8cc99bb063d5aaa4de32dfb174ee3b32c552c88",
    "rfq_charlie::baseline:baseline": "b7a901a8ebe3de8b30fef4b4d404302e98e24ff5",
    "rfq_alpha::improved:improved": "37dd559f8e31d1ba18f9a53a73bd35c1eff4b095",
    "rfq_bravo::improved:improved": "7d5f22cc20011b7a24023681a30d5f71265f1104",
    "rfq_charlie::improved:improved": "b3c017cfe2ed77d1f5e407879cf249f82fb4fae8",
}


def _compute_hash(record: dict) -> str:
    payload = []
    for stage, metrics in sorted(record["stages"].items()):
        coverage = tuple(sorted(metrics.get("section_coverage", [])))
        artifact = round(metrics.get("pct_page_artifact_lines", 0.0), 4)
        cross = sum(1 for chunk in record["chunks"][stage] if chunk.get("cross_heading"))
        payload.append(f"{stage}:{coverage}:{artifact}:{cross}")
    return hashlib.sha1("|".join(payload).encode()).hexdigest()


def test_evaluation_pipeline(tmp_path):
    config = load_config(Path("chunking/config.yaml"))
    summary = run_evaluation(Path("data/corpus"), config, tmp_path)

    for metrics in summary.values():
        assert metrics["SectionPresence@Any"].deltas["value"] >= 5.0
        assert metrics["NoBleed%"].deltas["value"] >= 15.0

    inst_dir = tmp_path / "instrumentation"
    for folder in ("baseline", "improved"):
        for path in (inst_dir / folder).glob("*.jsonl"):
            with path.open() as fh:
                record = json.loads(fh.readline())
            key = f"{path.stem}:{folder}"
            assert _compute_hash(record) == EXPECTED_HASHES[key]
