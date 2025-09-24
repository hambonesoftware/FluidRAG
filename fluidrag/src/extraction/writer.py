from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

VALID_PASSES = {"Mechanical", "Electrical", "Controls", "Software", "Project Management"}


@dataclass
class ExtractionRecord:
    discipline: str
    section: str
    subsection: str
    specification: str

    def is_valid(self) -> bool:
        return self.discipline in VALID_PASSES and bool(self.section and self.specification)


class CsvWriter:
    def __init__(self, output_path: str | Path) -> None:
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

    def write(self, records: Iterable[ExtractionRecord]) -> dict:
        valid_records: List[ExtractionRecord] = []
        repaired: List[ExtractionRecord] = []
        dropped = 0
        for record in records:
            if record.is_valid():
                valid_records.append(record)
                continue
            if record.discipline not in VALID_PASSES and record.discipline:
                repaired_record = ExtractionRecord(
                    discipline="Project Management",
                    section=record.section or "",
                    subsection=record.subsection or "",
                    specification=record.specification,
                )
                if repaired_record.is_valid():
                    repaired.append(repaired_record)
                    continue
            dropped += 1

        with self.output_path.open("w", newline="", encoding="utf-8") as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
            writer.writerow(["Discipline", "Section", "SubSection", "Specification"])
            for record in valid_records + repaired:
                writer.writerow([record.discipline, record.section, record.subsection, record.specification])

        total = len(valid_records) + len(repaired)
        total_input = total + dropped
        return {
            "total_input": total_input,
            "written": total,
            "repaired": len(repaired),
            "dropped": dropped,
            "valid_percent": (total / total_input * 100.0) if total_input else 0.0,
        }


__all__ = ["CsvWriter", "ExtractionRecord", "VALID_PASSES"]
