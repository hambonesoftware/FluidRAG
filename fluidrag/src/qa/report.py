from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from fluidrag.src.chunking.standard import Chunk


@dataclass
class QAStats:
    chunk_count: int
    avg_length: float
    signals_complete: float
    fluid_above: float
    hep_above: float


class QAReport:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate(self, doc_id: str, chunks: Sequence[Chunk]) -> Dict[str, object]:
        chunk_lengths = [len(chunk.text.split()) for chunk in chunks]
        chunk_count = len(chunk_lengths)
        avg_length = float(sum(chunk_lengths) / chunk_count) if chunk_count else 0.0
        signals_complete = 0
        for chunk in chunks:
            if all(key in chunk.signals for key in [
                "entropy",
                "entropy_smooth",
                "d_entropy",
                "emb_drift",
                "cluster_switch",
                "regex_prior",
                "numbering_score",
                "layout_score",
            ]):
                signals_complete += 1
        signals_ratio = (signals_complete / chunk_count * 100.0) if chunk_count else 0.0
        fluid_above = sum(1 for chunk in chunks if chunk.scores.get("fluid_above_threshold"))
        hep_above = sum(1 for chunk in chunks if chunk.scores.get("hep_above_threshold"))
        fluid_ratio = (fluid_above / chunk_count * 100.0) if chunk_count else 0.0
        hep_ratio = (hep_above / chunk_count * 100.0) if chunk_count else 0.0

        report = {
            "doc_id": doc_id,
            "chunk_count": chunk_count,
            "avg_length": avg_length,
            "signals_complete_percent": signals_ratio,
            "fluid_above_threshold_percent": fluid_ratio,
            "hep_above_threshold_percent": hep_ratio,
        }

        report_path = self.output_dir / f"{doc_id}_report.json"
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
        return report


__all__ = ["QAReport", "QAStats"]
