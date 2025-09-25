"""Build an enriched requirements register from stage JSON and raw CSV data."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .register_utils import (
    canonical_pass,
    compute_anchor,
    detect_atomicity,
    extract_machine_fields,
    generate_req_id,
    infer_eval_bucket,
    infer_schedule_fields,
    infer_tags,
)


@dataclass
class StageChunk:
    chunk_id: str
    pass_name: str
    section_id: str
    section_title: str
    header_anchor: str
    page_start: Optional[int]
    page_end: Optional[int]
    text: str
    order: int


class StageIndex:
    """Lightweight index that exposes contextual lookups for stage chunks."""

    def __init__(self) -> None:
        self._chunks: Dict[str, StageChunk] = {}
        self._order: List[str] = []

    def add_chunk(self, chunk: StageChunk) -> None:
        self._chunks[chunk.chunk_id] = chunk
        self._order.append(chunk.chunk_id)

    def get(self, chunk_id: str) -> Optional[StageChunk]:
        return self._chunks.get(chunk_id)

    def context(self, chunk_id: str, window: int = 2) -> str:
        if chunk_id not in self._chunks:
            return ""
        idx = self._order.index(chunk_id)
        start = max(0, idx - window)
        end = min(len(self._order), idx + window + 1)
        context_chunks = [self._chunks[self._order[i]].text for i in range(start, end)]
        return "\n".join(context_chunks)

    @property
    def chunks(self) -> Iterable[StageChunk]:
        for chunk_id in self._order:
            yield self._chunks[chunk_id]


def _load_stage_file(path: Path, counter: int) -> Tuple[List[StageChunk], int]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if isinstance(payload, dict):
        items = payload.get("chunks", [])
    else:
        items = payload
    chunks: List[StageChunk] = []
    for item in items:
        chunk_id = item.get("chunk_id") or item.get("id") or f"chunk-{counter}"
        section_id = str(item.get("section_id", ""))
        section_title = item.get("section_title") or item.get("title") or ""
        header_anchor = item.get("header_anchor") or compute_anchor(section_title or chunk_id)
        page_start = item.get("page_start")
        page_end = item.get("page_end")
        text = item.get("text", "")
        pass_name = canonical_pass(item.get("pass") or item.get("stage") or "Header")
        chunks.append(
            StageChunk(
                chunk_id=chunk_id,
                pass_name=pass_name,
                section_id=section_id,
                section_title=section_title,
                header_anchor=header_anchor,
                page_start=page_start,
                page_end=page_end,
                text=text,
                order=counter,
            )
        )
        counter += 1
    return chunks, counter


def load_stage_index(stage_dir: Path) -> StageIndex:
    index = StageIndex()
    counter = 0
    for path in sorted(stage_dir.glob("*.json")):
        chunks, counter = _load_stage_file(path, counter)
        for chunk in chunks:
            index.add_chunk(chunk)
    return index


COLUMN_ORDER = [
    "ReqID",
    "ParentReqID",
    "Atomicity",
    "Pass",
    "Tags",
    "SourceDoc",
    "SectionID",
    "SectionTitle",
    "PageStart",
    "PageEnd",
    "ChunkID",
    "HeaderAnchor",
    "Anchor",
    "Specification",
    "ReqType",
    "Metric",
    "Operator",
    "TargetValue",
    "Units",
    "TestMethod",
    "AcceptanceWindow",
    "EvalBucket",
    "Milestone",
    "Week",
    "PaymentTerm",
]


def build_register(stage_index: StageIndex, raw_csv: Path) -> pd.DataFrame:
    raw_df = pd.read_csv(raw_csv)
    expected_columns = {"Specification", "Pass", "SourceDoc", "ChunkID"}
    missing = expected_columns.difference(raw_df.columns)
    if missing:
        raise ValueError(f"Raw CSV is missing required columns: {sorted(missing)}")

    raw_df["Pass"] = raw_df["Pass"].apply(canonical_pass)
    raw_df = raw_df.drop_duplicates(subset=["Specification", "Pass", "SourceDoc"]).reset_index(drop=True)

    records: List[Dict[str, object]] = []
    last_section_by_doc: Dict[str, Tuple[str, str, Optional[int], Optional[int], str]] = {}
    for entry in raw_df.itertuples(index=False):
        chunk = stage_index.get(entry.ChunkID)
        if chunk:
            section_id = chunk.section_id
            section_title = chunk.section_title
            page_start = chunk.page_start
            page_end = chunk.page_end
            header_anchor = chunk.header_anchor
            last_section_by_doc[entry.SourceDoc] = (
                section_id,
                section_title,
                page_start,
                page_end,
                header_anchor,
            )
        else:
            section_id, section_title, page_start, page_end, header_anchor = last_section_by_doc.get(
                entry.SourceDoc,
                ("", "", None, None, compute_anchor(entry.Specification)),
            )

        machine_fields = extract_machine_fields(entry.Specification, entry.Pass)
        req_type = machine_fields["ReqType"]
        milestone, week, payment_term = infer_schedule_fields(entry.Specification, req_type)

        record: Dict[str, object] = {
            "ReqID": generate_req_id(section_id, entry.Specification),
            "ParentReqID": "",
            "Atomicity": detect_atomicity(entry.Specification),
            "Pass": canonical_pass(entry.Pass),
            "Tags": infer_tags(entry.Specification),
            "SourceDoc": entry.SourceDoc,
            "SectionID": section_id,
            "SectionTitle": section_title,
            "PageStart": int(page_start) if isinstance(page_start, (int, float)) else None,
            "PageEnd": int(page_end) if isinstance(page_end, (int, float)) else None,
            "ChunkID": entry.ChunkID,
            "HeaderAnchor": header_anchor,
            "Anchor": compute_anchor(entry.Specification),
            "Specification": entry.Specification.strip(),
            "ReqType": req_type,
            "Metric": machine_fields["Metric"],
            "Operator": machine_fields["Operator"],
            "TargetValue": machine_fields["TargetValue"],
            "Units": machine_fields["Units"],
            "TestMethod": machine_fields["TestMethod"],
            "AcceptanceWindow": machine_fields["AcceptanceWindow"],
            "EvalBucket": infer_eval_bucket(req_type),
            "Milestone": milestone,
            "Week": week,
            "PaymentTerm": payment_term,
        }
        records.append(record)

    df = pd.DataFrame.from_records(records, columns=COLUMN_ORDER)
    df = df.sort_values(["Pass", "SectionID", "ReqID"]).reset_index(drop=True)
    return df
