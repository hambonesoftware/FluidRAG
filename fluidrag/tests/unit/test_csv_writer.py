from __future__ import annotations

import csv
from pathlib import Path

from fluidrag.src.extraction.writer import CsvWriter, ExtractionRecord


def test_csv_writer_quotes_fields(tmp_path: Path):
    writer = CsvWriter(tmp_path / "output.csv")
    records = [
        ExtractionRecord(discipline="Mechanical", section="1", subsection="1.1", specification="Line with, comma"),
        ExtractionRecord(discipline="Other", section="2", subsection="2.1", specification="Needs repair"),
    ]
    stats = writer.write(records)
    assert stats["written"] == 2
    with (tmp_path / "output.csv").open() as f:
        reader = csv.reader(f)
        rows = list(reader)
    assert rows[0] == ["Discipline", "Section", "SubSection", "Specification"]
    assert rows[1][0] == "Mechanical"
    assert rows[1][3] == "Line with, comma"
