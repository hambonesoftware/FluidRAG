from __future__ import annotations

from pathlib import Path

from fluidrag.config import load_config
from fluidrag.src.chunking.standard import StandardChunker
from fluidrag.src.qa.report import QAReport
from fluidrag.src.scoring.features import compute_scores


TEXT = """
1. Intro
General overview of the system layout.

2. Requirements
The builder shall ensure a 10 mm clearance around live parts.
"""


def test_qa_report_generation(tmp_path: Path):
    config = load_config()
    chunker = StandardChunker()
    chunks = chunker.chunk_text(TEXT, "doc.txt", "qa")
    compute_scores(chunks, config)
    reporter = QAReport(tmp_path)
    report = reporter.generate("qa", chunks)
    assert report["chunk_count"] == len(chunks)
    output_file = tmp_path / "qa_report.json"
    assert output_file.exists()
