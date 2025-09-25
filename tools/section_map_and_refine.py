"""Populate section metadata and refine suspect requirements into atomic rows."""
from __future__ import annotations

import argparse
import json
import logging
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd
from jsonschema import ValidationError, validate
from rapidfuzz import fuzz, process

from tools.llm_client import LLMClient
from tools.refine_prompts import SYSTEM_PROMPT, get_granularity_guide


LOGGER = logging.getLogger(__name__)

SECTION_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)*)(?:\)|\.)?\s+(.{3,})$", re.MULTILINE)

ALLOWED_OPERATORS = {">=", "<=", "="}
ALLOWED_TEST_METHODS = {
    "FAT": "FAT",
    "SAT": "SAT",
    "MEASUREMENT": "Measurement",
    "VISUALINSPECT": "VisualInspect",
    "DOCREVIEW": "DocReview",
}
ALLOWED_UNITS = {"%", "cpm", "in", "mm", "lb", "kg", "A", "V", "Hz", "kA", "°C", "ms"}
UNIT_CANONICAL_MAP = {
    "%": "%",
    "percent": "%",
    "percentage": "%",
    "cpm": "cpm",
    "in": "in",
    "inch": "in",
    "inches": "in",
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "kg": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "a": "A",
    "amp": "A",
    "amps": "A",
    "ampere": "A",
    "amperes": "A",
    "v": "V",
    "volt": "V",
    "volts": "V",
    "hz": "Hz",
    "hertz": "Hz",
    "ka": "kA",
    "°c": "°C",
    "degc": "°C",
    "ms": "ms",
}


def canonical_unit(unit: str) -> str:
    """Return a canonical unit string when recognised."""

    normalized = unit.strip()
    if not normalized:
        return ""
    return UNIT_CANONICAL_MAP.get(normalized.lower(), normalized)


def canonical_test_method(value: str) -> str:
    """Normalise test method names to the allowed vocabulary."""

    normalized = value.strip()
    if not normalized:
        return ""
    return ALLOWED_TEST_METHODS.get(normalized.upper(), normalized)


@dataclass
class SectionRecord:
    """Metadata describing a section and the chunks that belong to it."""

    section_id: str
    section_title: str
    pass_name: str
    header_anchor: Optional[str] = None
    chunk_ids: List[str] = field(default_factory=list)


@dataclass
class ChunkRecord:
    """Text chunk from the staged JSON corpus."""

    chunk_id: str
    text: str
    pass_name: str
    section: Optional[SectionRecord]


class StageIndex:
    """Index of staged chunks keyed by chunk id and organised by section."""

    def __init__(self) -> None:
        self.chunk_by_id: Dict[str, ChunkRecord] = {}
        self.section_by_key: Dict[Tuple[str, str, str], SectionRecord] = {}

    def add_chunk(
        self,
        *,
        chunk_id: str,
        text: str,
        pass_name: str,
        section_id: Optional[str],
        section_title: Optional[str],
        header_anchor: Optional[str],
    ) -> None:
        """Register a chunk with the correct section metadata."""

        pass_key = (pass_name or "Header").strip() or "Header"
        section: Optional[SectionRecord] = None
        if section_id and section_title:
            key = (pass_key, section_id, section_title)
            section = self.section_by_key.get(key)
            if section is None:
                section = SectionRecord(
                    section_id=section_id,
                    section_title=section_title,
                    pass_name=pass_key,
                    header_anchor=header_anchor,
                )
                self.section_by_key[key] = section
            else:
                if not section.header_anchor and header_anchor:
                    section.header_anchor = header_anchor
            section.chunk_ids.append(chunk_id)

        chunk = ChunkRecord(
            chunk_id=chunk_id,
            text=text,
            pass_name=pass_key,
            section=section,
        )
        self.chunk_by_id[chunk_id] = chunk

    def get_section_for_chunk(self, chunk_id: str) -> Optional[SectionRecord]:
        chunk = self.chunk_by_id.get(chunk_id)
        return chunk.section if chunk else None

    def iter_chunks_for_pass(self, pass_name: Optional[str]) -> Iterable[ChunkRecord]:
        if pass_name:
            normalized = str(pass_name).strip()
            if not normalized:
                normalized = "Header"
            normalized_lower = normalized.lower()
            return [
                c for c in self.chunk_by_id.values() if c.pass_name.lower() == normalized_lower
            ]
        return list(self.chunk_by_id.values())


def parse_stage_file(path: Path, index: StageIndex) -> None:
    """Parse a staged JSON file and populate the stage index."""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc

    if not isinstance(data, list):
        LOGGER.warning("Stage file %s does not contain a list of chunks", path)
        return

    current_section_by_pass: Dict[str, Tuple[str, str, Optional[str]]] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        chunk_id = entry.get("chunk_id")
        text = entry.get("text", "")
        pass_name = entry.get("pass") or entry.get("swimlane") or "Header"
        section_id = entry.get("section_id")
        section_title = entry.get("section_title")
        header_anchor = entry.get("header_anchor")

        if (not section_id or not section_title) and text:
            match = SECTION_PATTERN.search(text)
            if match:
                section_id = section_id or match.group(1)
                section_title = section_title or match.group(2).strip()

        pass_key = pass_name or "Header"
        if section_id and section_title:
            current_section_by_pass[pass_key] = (section_id, section_title, header_anchor)
        else:
            cached = current_section_by_pass.get(pass_key)
            if cached:
                section_id, section_title, header_anchor = cached

        if not chunk_id:
            continue

        index.add_chunk(
            chunk_id=chunk_id,
            text=text,
            pass_name=pass_key,
            section_id=section_id,
            section_title=section_title,
            header_anchor=header_anchor,
        )


def load_stage_index(stage_dir: Path) -> StageIndex:
    """Load every stage JSON under ``stage_dir`` into an index."""

    index = StageIndex()
    for path in sorted(stage_dir.glob("*.json")):
        parse_stage_file(path, index)
    return index


def fuzzy_chunk_lookup(
    *,
    index: StageIndex,
    specification: str,
    pass_name: Optional[str],
) -> Optional[str]:
    """Return the best matching chunk id for a specification when missing."""

    choices = {
        chunk.chunk_id: chunk.text
        for chunk in index.iter_chunks_for_pass(pass_name)
        if chunk.text
    }
    if not choices:
        return None
    match = process.extractOne(
        specification,
        choices,
        scorer=fuzz.WRatio,
    )
    if not match:
        return None
    _, score, chunk_id = match
    return chunk_id if score >= 60 else None


def ensure_section_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Insert the section columns if missing and return the frame."""

    if "(Sub)Section #" not in df.columns:
        df.insert(1, "(Sub)Section #", "")
    if "(Sub)Section Name" not in df.columns:
        df.insert(2, "(Sub)Section Name", "")
    return df


def detect_suspect(text: str, threshold: int = 120) -> bool:
    """Heuristic detection of non-atomic requirement statements."""

    if not text:
        return False

    lower = text.lower()
    if ";" in text:
        return True
    if "\u201c and \u201d" in text or '" and "' in text:
        return True

    numbers = {match for match in re.findall(r"\d+(?:\.\d+)?", text)}
    if len(numbers) >= 2:
        return True

    if len(text) > threshold and any(conj in lower for conj in [" and ", " or "]):
        return True

    if ":" in text and re.search(r":\s*(?:-\s|\d+\.|•|\u2022|\u2023)", text):
        return True
    if re.search(r"(?:•|\u2022|\u2023| - )", text):
        return True

    return False


def build_context_snippets(section: SectionRecord, chunk_id: str, index: StageIndex) -> List[Dict[str, str]]:
    """Collect the section header and neighbouring chunks for refinement."""

    snippets: List[Dict[str, str]] = []
    header_text = f"{section.section_id} {section.section_title}".strip()
    if header_text:
        snippets.append({"Type": "SectionHeader", "Text": header_text})

    chunk_ids = section.chunk_ids
    try:
        position = chunk_ids.index(chunk_id)
    except ValueError:
        position = 0

    start = max(0, position - 2)
    end = min(len(chunk_ids), position + 3)
    for cid in chunk_ids[start:end]:
        chunk = index.chunk_by_id.get(cid)
        if not chunk:
            continue
        snippets.append({"ChunkID": cid, "Text": chunk.text})
    return snippets


def load_schema(schema_path: Path) -> Dict[str, Any]:
    """Load the strict JSON schema used for validation."""

    with schema_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def validate_operator(value: str) -> bool:
    return value in ALLOWED_OPERATORS


def ensure_artifacts_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def run_pipeline(
    *,
    stage_dir: Path,
    in_csv: Path,
    out_csv: Path,
    atomic_csv: Path,
    artifacts_dir: Path,
    schema_path: Optional[Path] = None,
    threshold: int = 120,
    llm_client: Optional[LLMClient] = None,
) -> None:
    """Execute the two-phase section mapping and refinement pipeline."""

    df = pd.read_csv(in_csv)
    df = ensure_section_columns(df)
    base_columns = list(df.columns)

    index = load_stage_index(stage_dir)

    section_ids: List[str] = []
    section_titles: List[str] = []
    section_records: List[Optional[SectionRecord]] = []
    chunk_ids: List[Optional[str]] = []

    for row in df.itertuples(index=False):
        spec_value = getattr(row, "Specification", "")
        if isinstance(spec_value, float) and math.isnan(spec_value):
            spec_value = ""
        chunk_value = getattr(row, "ChunkID", None)
        if isinstance(chunk_value, float) and math.isnan(chunk_value):
            chunk_value = None
        pass_value = getattr(row, "Pass", None)
        if isinstance(pass_value, float) and math.isnan(pass_value):
            pass_value = None
        if isinstance(pass_value, str):
            pass_value = pass_value.strip() or None

        resolved_chunk = chunk_value if isinstance(chunk_value, str) and chunk_value else None
        if not resolved_chunk:
            resolved_chunk = fuzzy_chunk_lookup(
                index=index,
                specification=str(spec_value),
                pass_name=pass_value,
            )

        section_record = (
            index.get_section_for_chunk(resolved_chunk) if resolved_chunk else None
        )
        section_id = section_record.section_id if section_record else ""
        section_title = section_record.section_title if section_record else ""

        section_ids.append(section_id)
        section_titles.append(section_title)
        section_records.append(section_record)
        chunk_ids.append(resolved_chunk)

    df["(Sub)Section #"] = section_ids
    df["(Sub)Section Name"] = section_titles
    df["ChunkID"] = chunk_ids

    df["Atomicity"] = ["atomic" for _ in range(len(df))]
    df["ParentReqID"] = ""
    df["ParentVerbatim"] = ""
    df["ReqID"] = ""
    df["ReqType"] = ""
    df["Metric"] = ""
    df["Operator"] = ""
    df["TargetValue"] = ""
    df["Units"] = ""
    df["TestMethod"] = ""
    df["AcceptanceWindow"] = ""
    df["Tags"] = ""
    df["RefineError"] = ""

    schema = load_schema(schema_path or Path(__file__).resolve().parents[1] / "schemas" / "refinement_output.schema.json")
    ensure_artifacts_dir(artifacts_dir)

    llm = llm_client or LLMClient()

    section_counters: Dict[str, int] = {}
    output_rows: List[Dict[str, Any]] = []

    extra_columns = [
        "Atomicity",
        "ParentReqID",
        "ParentVerbatim",
        "ReqID",
        "ReqType",
        "Metric",
        "Operator",
        "TargetValue",
        "Units",
        "TestMethod",
        "AcceptanceWindow",
        "Tags",
        "RefineError",
    ]

    for idx, (row, section_record, chunk_id) in enumerate(
        zip(df.to_dict(orient="records"), section_records, chunk_ids)
    ):
        spec_text = row.get("Specification", "")
        section_id = row.get("(Sub)Section #", "")
        section_title = row.get("(Sub)Section Name", "")
        pass_name = row.get("Pass")

        if detect_suspect(spec_text, threshold=threshold) and section_record and chunk_id:
            df.at[idx, "Atomicity"] = "suspect"
            row["Atomicity"] = "suspect"
            seq = section_counters.get(section_id, 0) + 1
            parent_req_id = f"S-{section_id}-{seq:03d}" if section_id else f"S-UNK-{seq:03d}"
            section_counters[section_id or "UNK"] = seq

            payload = {
                "Pass": pass_name,
                "SourceDoc": row.get("SourceDoc"),
                "SectionID": section_id,
                "SectionTitle": section_title,
                "ChunkID": chunk_id,
                "HeaderAnchor": section_record.header_anchor,
                "ParentSpecID": parent_req_id,
                "ParentVerbatimText": spec_text,
                "ContextSnippets": build_context_snippets(section_record, chunk_id, index),
            }

            guide = get_granularity_guide(str(pass_name))
            try:
                response = llm.refine(
                    system_prompt=SYSTEM_PROMPT,
                    user_payload=payload,
                    schema=schema,
                    granularity_guide=guide,
                )
            except NotImplementedError:
                df.at[idx, "RefineError"] = "LLM backend not configured"
                row["RefineError"] = "LLM backend not configured"
                output_rows.append(row)
                continue

            raw_output = getattr(response, "content", response)
            result = raw_output
            if isinstance(result, str):
                try:
                    result = json.loads(result)
                except json.JSONDecodeError:
                    df.at[idx, "RefineError"] = "Invalid JSON returned by LLM"
                    row["RefineError"] = "Invalid JSON returned by LLM"
                    log_path = artifacts_dir / f"{parent_req_id}.json"
                    log_path.write_text(
                        json.dumps({"input": payload, "output": raw_output, "error": "invalid json"}, indent=2),
                        encoding="utf-8",
                    )
                    output_rows.append(row)
                    continue

            try:
                validate(instance=result, schema=schema)
            except ValidationError as exc:
                df.at[idx, "RefineError"] = f"Schema validation failed: {exc.message}"
                row["RefineError"] = f"Schema validation failed: {exc.message}"
                log_path = artifacts_dir / f"{parent_req_id}.json"
                log_path.write_text(
                    json.dumps({"input": payload, "output": result, "error": exc.message}, indent=2),
                    encoding="utf-8",
                )
                output_rows.append(row)
                continue

            children = result.get("children", [])
            if not children:
                df.at[idx, "RefineError"] = "LLM returned no children"
                row["RefineError"] = "LLM returned no children"
                log_path = artifacts_dir / f"{parent_req_id}.json"
                log_path.write_text(
                    json.dumps({"input": payload, "output": result, "error": "no children"}, indent=2),
                    encoding="utf-8",
                )
                output_rows.append(row)
                continue

            invalid_operator = any(
                not validate_operator(str(child.get("operator", ""))) for child in children
            )
            if invalid_operator:
                df.at[idx, "RefineError"] = "Invalid operator in refinement output"
                row["RefineError"] = "Invalid operator in refinement output"
                log_path = artifacts_dir / f"{parent_req_id}.json"
                log_path.write_text(
                    json.dumps({"input": payload, "output": result, "error": "invalid operator"}, indent=2),
                    encoding="utf-8",
                )
                output_rows.append(row)
                continue

            allowed_methods = set(ALLOWED_TEST_METHODS.values())
            invalid_method = False
            invalid_units = False
            for child in children:
                method_value = canonical_test_method(str(child.get("test_method", "")))
                if method_value and method_value not in allowed_methods:
                    invalid_method = True
                    break
                unit_value = canonical_unit(str(child.get("units", "")))
                if unit_value and unit_value not in ALLOWED_UNITS:
                    invalid_units = True
                    break

            if invalid_method:
                df.at[idx, "RefineError"] = "Invalid test method in refinement output"
                row["RefineError"] = "Invalid test method in refinement output"
                log_path = artifacts_dir / f"{parent_req_id}.json"
                log_path.write_text(
                    json.dumps({"input": payload, "output": result, "error": "invalid test method"}, indent=2),
                    encoding="utf-8",
                )
                output_rows.append(row)
                continue

            if invalid_units:
                df.at[idx, "RefineError"] = "Invalid units in refinement output"
                row["RefineError"] = "Invalid units in refinement output"
                log_path = artifacts_dir / f"{parent_req_id}.json"
                log_path.write_text(
                    json.dumps({"input": payload, "output": result, "error": "invalid units"}, indent=2),
                    encoding="utf-8",
                )
                output_rows.append(row)
                continue

            log_path = artifacts_dir / f"{parent_req_id}.json"
            log_path.write_text(
                json.dumps({"input": payload, "output": result}, indent=2),
                encoding="utf-8",
            )

            parent_row = dict(row)
            parent_row["Specification"] = result.get("parent_summary", spec_text)
            parent_row["Atomicity"] = "parent"
            parent_row["ReqID"] = parent_req_id
            parent_row["ParentVerbatim"] = spec_text
            parent_row["ParentReqID"] = ""
            for column in ["ReqType", "Metric", "Operator", "TargetValue", "Units", "TestMethod", "AcceptanceWindow", "Tags"]:
                parent_row[column] = ""
            parent_row["RefineError"] = ""

            output_rows.append(parent_row)

            child_suffix = ord("a")
            for child in children:
                child_row = dict(row)
                child_req_id = f"{parent_req_id}-{chr(child_suffix)}"
                child_suffix += 1
                child_row["Specification"] = child.get("requirement_text", "").strip()
                child_row["Atomicity"] = "atomic"
                child_row["ParentReqID"] = parent_req_id
                child_row["ParentVerbatim"] = spec_text
                child_row["ReqID"] = child_req_id
                child_row["ReqType"] = child.get("req_type", "")
                child_row["Metric"] = child.get("metric", "")
                operator = str(child.get("operator", "")).strip()
                child_row["Operator"] = operator
                target_value = child.get("target_value", "")
                if isinstance(target_value, (int, float)):
                    child_row["TargetValue"] = str(target_value)
                else:
                    child_row["TargetValue"] = str(target_value).strip()
                units = canonical_unit(str(child.get("units", "")))
                child_row["Units"] = units
                method = canonical_test_method(str(child.get("test_method", "")))
                child_row["TestMethod"] = method
                child_row["AcceptanceWindow"] = str(child.get("acceptance_window", "")).strip()
                tags = child.get("tags", [])
                if isinstance(tags, (list, tuple)):
                    child_row["Tags"] = ";".join(str(tag) for tag in tags)
                else:
                    child_row["Tags"] = str(tags)
                child_row["RefineError"] = ""
                output_rows.append(child_row)

            continue

        output_rows.append(row)

    final_columns = base_columns + [col for col in extra_columns if col not in base_columns]
    output_df = pd.DataFrame(output_rows, columns=final_columns)

    output_df.to_csv(out_csv, index=False)

    atomic_df = output_df[output_df["Atomicity"] == "atomic"]
    atomic_df.to_csv(atomic_csv, index=False)


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stages", type=Path, required=True, help="Directory containing staged JSON files")
    parser.add_argument("--in-csv", dest="in_csv", type=Path, required=True, help="Input FluidRAG results CSV")
    parser.add_argument("--out-csv", dest="out_csv", type=Path, required=True, help="Output CSV path")
    parser.add_argument("--atomic-csv", dest="atomic_csv", type=Path, required=True, help="Atomic-only CSV path")
    parser.add_argument("--artifacts-dir", dest="artifacts_dir", type=Path, required=True, help="Directory to store refinement logs")
    parser.add_argument("--threshold", type=int, default=120, help="Character threshold for suspect detection")
    parser.add_argument("--schema", type=Path, default=None, help="Override path to refinement schema")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    args = parse_args(argv)
    run_pipeline(
        stage_dir=args.stages,
        in_csv=args.in_csv,
        out_csv=args.out_csv,
        atomic_csv=args.atomic_csv,
        artifacts_dir=args.artifacts_dir,
        schema_path=args.schema,
        threshold=args.threshold,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()

