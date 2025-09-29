"""Phase 3 benchmark harness for upload→parser pipeline."""

from __future__ import annotations

# ruff: noqa: E402
import argparse
import os
import statistics
import sys
import time
from pathlib import Path

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
if str(PACKAGE_ROOT) not in sys.path:
    sys.path.append(str(PACKAGE_ROOT))

from backend.app.config import get_settings
from backend.app.services.parser_service import parse_and_enrich
from backend.app.services.upload_service import ensure_normalized

_SAMPLE_TEXT = (
    "EXECUTIVE SUMMARY\n\n"
    "1. First bullet\n"
    "2. Second bullet\n\n"
    "Data\nYear|Revenue\n2023|100\n\n"
    "[image:chart]\n\n"
    "Visit https://example.com"
)


def run_benchmark(iterations: int = 5) -> dict[str, float]:
    """Run upload→parser benchmark and return stats."""
    original_artifact_root = os.environ.get("ARTIFACT_ROOT")
    os.environ.setdefault("FLUIDRAG_OFFLINE", "true")

    upload_latencies: list[float] = []
    parser_latencies: list[float] = []
    total_latencies: list[float] = []

    for _ in range(max(1, iterations)):
        with tempfile_directory() as artifact_dir:
            os.environ["ARTIFACT_ROOT"] = str(artifact_dir)
            get_settings.cache_clear()
            get_settings()

            sample_path = artifact_dir / "bench-sample.txt"
            sample_path.write_text(_SAMPLE_TEXT, encoding="utf-8")

            start_upload = time.perf_counter()
            normalized = ensure_normalized(file_name=str(sample_path))
            upload_latencies.append(time.perf_counter() - start_upload)

            start_parser = time.perf_counter()
            parse_and_enrich(normalized.doc_id, normalized.normalized_path)
            parser_latencies.append(time.perf_counter() - start_parser)

            total_latencies.append(time.perf_counter() - start_upload)

    if original_artifact_root is not None:
        os.environ["ARTIFACT_ROOT"] = original_artifact_root
    else:
        os.environ.pop("ARTIFACT_ROOT", None)
    get_settings.cache_clear()

    return {
        "upload_p50": statistics.median(upload_latencies),
        "upload_p95": _percentile(upload_latencies, 0.95),
        "parser_p50": statistics.median(parser_latencies),
        "parser_p95": _percentile(parser_latencies, 0.95),
        "total_p50": statistics.median(total_latencies),
        "total_p95": _percentile(total_latencies, 0.95),
    }


def _percentile(samples: list[float], quantile: float) -> float:
    if not samples:
        return 0.0
    sorted_samples = sorted(samples)
    index = int(round((len(sorted_samples) - 1) * quantile))
    return sorted_samples[index]


class tempfile_directory:
    """Context manager creating/removing a temporary directory."""

    _dir: Path

    def __enter__(self) -> Path:
        import tempfile

        self._dir = Path(tempfile.mkdtemp(prefix="fluidrag-bench-"))
        return self._dir

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: D401 - standard context manager signature
        import shutil

        shutil.rmtree(self._dir, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Phase 3 benchmark")
    parser.add_argument("--iterations", type=int, default=5, help="Number of runs")
    args = parser.parse_args()

    stats = run_benchmark(iterations=args.iterations)
    for key, value in stats.items():
        print(f"{key}: {value:.6f} s")


if __name__ == "__main__":
    main()
