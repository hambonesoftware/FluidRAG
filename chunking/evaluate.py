"""Evaluation CLI for chunking improvements."""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Mapping, Sequence, Tuple

from .instrumentation import (
    APPENDIX_BLOCK_RE,
    APPENDIX_HEADING_RE,
    MAIN_HEADING_RE,
    first_non_artifact_line,
    instrument_doc,
    is_artifact,
    summarize_chunks,
    token_count,
)
from .rules import apply_rules
from .views import build_views

STAGES = ["raw_chunking", "standard_chunks", "fluid_chunks", "hep_chunks"]


@dataclass
class EvaluationResult:
    baseline: Dict[str, float]
    improved: Dict[str, float]
    deltas: Dict[str, float]


SPEC_TOKEN_RE = re.compile(
    r"\b(?:\d+(?:\.\d+)?|mm|in|kA|vac|psig|nfpa|iso|ul|plc|eoat|mdr|cdlr|shall|must)\b",
    re.IGNORECASE,
)


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def load_doc_stages(doc_dir: Path) -> Dict[str, List[Dict]]:
    stages: Dict[str, List[Dict]] = {}
    for stage in STAGES:
        file_path = doc_dir / f"{stage}.json"
        if not file_path.exists():
            raise FileNotFoundError(f"Missing stage file {file_path}")
        with file_path.open("r", encoding="utf-8") as fh:
            stages[stage] = json.load(fh)
    return stages


def recompute_hep_entropy(chunks: Sequence[Dict]) -> None:
    values: List[float] = []
    for chunk in chunks:
        value = _hep_entropy(chunk.get("text", ""))
        chunk.setdefault("meta", {})["hep_entropy"] = value
        values.append(value)
    if not values:
        return
    avg = mean(values)
    std = pstdev(values) or 1.0
    for chunk, value in zip(chunks, values):
        chunk.setdefault("meta", {})["hep_entropy_z"] = (value - avg) / std


def _hep_entropy(text: str) -> float:
    if not text:
        return 0.0
    counts: Dict[str, int] = {}
    for char in text:
        counts[char] = counts.get(char, 0) + 1
    total = sum(counts.values())
    entropy = -sum((count / total) * math.log((count / total), 2) for count in counts.values())
    spec_density = _spec_token_density(text)
    return entropy * spec_density


def _spec_token_density(text: str) -> float:
    tokens = text.split()
    if not tokens:
        return 0.0
    matches = SPEC_TOKEN_RE.findall(text)
    return len(matches) / len(tokens)


def auto_label_sections(doc_text: str, chunks: Sequence[Dict]) -> Dict[str, Dict]:
    headings = []
    for pattern in (MAIN_HEADING_RE, APPENDIX_HEADING_RE, APPENDIX_BLOCK_RE):
        for match in pattern.finditer(doc_text):
            headings.append((match.group(0).strip(), match.groupdict().get("num") or match.groupdict().get("anum") or match.group(0).strip()))
    headings = list(dict.fromkeys(headings))
    section_map: Dict[str, Dict] = {}
    chunk_first_lines = [first_non_artifact_line(chunk.get("text", "")) for chunk in chunks]
    for order, (label, section_id) in enumerate(headings):
        matches = [idx for idx, line in enumerate(chunk_first_lines) if line.startswith(label)]
        section_map[section_id] = {
            "label": label,
            "order": order,
            "chunks": matches,
            "present": bool(matches),
            "present_at_1": bool(matches and matches[0] == order),
        }
    return section_map


def section_presence_metrics(labels: Mapping[str, Dict]) -> Tuple[float, float]:
    if not labels:
        return 0.0, 0.0
    total = len(labels)
    any_hits = sum(1 for meta in labels.values() if meta["present"])
    top_hits = sum(1 for meta in labels.values() if meta["present_at_1"])
    return top_hits / total * 100.0, any_hits / total * 100.0


def compute_metrics(doc_id: str, baseline: Dict[str, List[Dict]], improved: Dict[str, List[Dict]], config: Dict) -> Dict[str, EvaluationResult]:
    metrics: Dict[str, EvaluationResult] = {}

    raw_text = "\n".join(chunk.get("text", "") for chunk in baseline["raw_chunking"])

    baseline_labels = auto_label_sections(raw_text, baseline["standard_chunks"])
    improved_labels = auto_label_sections(raw_text, improved["standard_chunks"])
    base_sec1, base_sec_any = section_presence_metrics(baseline_labels)
    imp_sec1, imp_sec_any = section_presence_metrics(improved_labels)

    metrics["SectionPresence@1"] = EvaluationResult(
        baseline={"value": base_sec1},
        improved={"value": imp_sec1},
        deltas={"value": imp_sec1 - base_sec1},
    )
    metrics["SectionPresence@Any"] = EvaluationResult(
        baseline={"value": base_sec_any},
        improved={"value": imp_sec_any},
        deltas={"value": imp_sec_any - base_sec_any},
    )

    _, base_fluid_diag = summarize_chunks(baseline["fluid_chunks"])
    _, imp_fluid_diag = summarize_chunks(improved["fluid_chunks"])
    base_bleed = _nobleed_percentage(base_fluid_diag)
    imp_bleed = _nobleed_percentage(imp_fluid_diag)
    metrics["NoBleed%"] = EvaluationResult(
        baseline={"value": base_bleed},
        improved={"value": imp_bleed},
        deltas={"value": imp_bleed - base_bleed},
    )

    base_artifact = _artifact_rate(baseline["fluid_chunks"])
    imp_artifact = _artifact_rate(improved["fluid_chunks"])
    metrics["ArtifactLineRate"] = EvaluationResult(
        baseline={"value": base_artifact},
        improved={"value": imp_artifact},
        deltas={"value": imp_artifact - base_artifact},
    )

    hep_chunks = improved["hep_chunks"]
    views = build_views(hep_chunks, config.get("views", {}), config.get("rules", {}))
    view_metrics = _view_metrics(views, config.get("views", {}), hep_chunks)
    metrics.update(view_metrics)
    return metrics


def _nobleed_percentage(diags: Sequence[instrumentation.ChunkDiagnostics]) -> float:
    if not diags:
        return 0.0
    clean = sum(1 for diag in diags if not diag.cross_heading)
    return clean / len(diags) * 100.0


def _artifact_rate(chunks: Sequence[Dict]) -> float:
    total_lines = 0
    artifact_lines = 0
    for chunk in chunks:
        lines = chunk.get("text", "").splitlines()
        total_lines += len(lines)
        artifact_lines += sum(1 for line in lines if is_artifact(line))
    if not total_lines:
        return 0.0
    return artifact_lines / total_lines * 100.0


def _view_metrics(
    views: Mapping[str, Sequence[Dict]], pass_configs: Mapping[str, Dict], candidates: Sequence[Dict]
) -> Dict[str, EvaluationResult]:
    results: Dict[str, EvaluationResult] = {}
    available_sections = {str(chunk.get("section_number") or "") for chunk in candidates if chunk.get("section_number")}
    for pass_name, chunks in views.items():
        cfg = pass_configs.get(pass_name, {})
        allow = set(cfg.get("section_allowlist", []))
        must = set(cfg.get("must_sections", []))
        token_budget = cfg.get("length_budget_tokens", 10_000)
        tokens = sum(chunk.get("tokens") or token_count(chunk.get("text", "")) for chunk in chunks)
        section_values = [str(chunk.get("section_number") or "") for chunk in chunks]
        hits = sum(1 for section in section_values if not allow or section in allow)
        precision = hits / len(chunks) * 100.0 if chunks else 0.0
        irrelevant_tokens = sum(
            (chunk.get("tokens") or token_count(chunk.get("text", "")))
            for chunk in chunks
            if allow and str(chunk.get("section_number") or "") not in allow
        )
        duplicate_rate = _duplicate_line_rate(chunks)
        sections = set(section_values)
        results[f"view::{pass_name}::precision"] = EvaluationResult(
            baseline={"value": 0.0},
            improved={"value": precision},
            deltas={"value": precision},
        )
        results[f"view::{pass_name}::irrelevant_tokens"] = EvaluationResult(
            baseline={"value": token_budget},
            improved={"value": irrelevant_tokens},
            deltas={"value": token_budget - irrelevant_tokens},
        )
        results[f"view::{pass_name}::duplicate_rate"] = EvaluationResult(
            baseline={"value": 100.0},
            improved={"value": duplicate_rate},
            deltas={"value": 100.0 - duplicate_rate},
        )
        missing_required = [section for section in must if section in available_sections and section not in sections]
        if missing_required:
            raise AssertionError(f"Pass {pass_name} is missing required sections {must}")
        if tokens > token_budget:
            raise AssertionError(f"Pass {pass_name} exceeds token budget {token_budget} with {tokens}")
    return results


def _duplicate_line_rate(chunks: Sequence[Dict]) -> float:
    lines = []
    for chunk in chunks:
        lines.extend([line.strip() for line in chunk.get("text", "").splitlines() if line.strip()])
    if not lines:
        return 0.0
    unique = len(set(lines))
    return 1 - (unique / len(lines))


def run_evaluation(corpus: Path, config: Dict, out_dir: Path) -> Dict[str, Dict[str, EvaluationResult]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    instrumentation_dir = out_dir / "instrumentation"
    baseline_dir = instrumentation_dir / "baseline"
    improved_dir = instrumentation_dir / "improved"
    baseline_dir.mkdir(parents=True, exist_ok=True)
    improved_dir.mkdir(parents=True, exist_ok=True)

    metrics_summary: Dict[str, Dict[str, EvaluationResult]] = {}

    for doc_dir in sorted(p for p in corpus.iterdir() if p.is_dir()):
        doc_id = doc_dir.name
        stages = load_doc_stages(doc_dir)
        improved = {
            "raw_chunking": stages["raw_chunking"],
            "standard_chunks": apply_rules(stages["standard_chunks"], config.get("rules", {})),
            "fluid_chunks": apply_rules(stages["fluid_chunks"], config.get("rules", {})),
            "hep_chunks": apply_rules(stages["hep_chunks"], config.get("rules", {})),
        }
        recompute_hep_entropy(improved["hep_chunks"])
        instrument_doc(doc_id + "::baseline", stages, baseline_dir)
        instrument_doc(doc_id + "::improved", improved, improved_dir)
        metrics = compute_metrics(doc_id, stages, improved, config)
        metrics_summary[doc_id] = metrics

    _validate_acceptance(metrics_summary)
    summary_path = out_dir / "metrics.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump({doc: {name: result.__dict__ for name, result in doc_metrics.items()} for doc, doc_metrics in metrics_summary.items()}, fh, indent=2)
    return metrics_summary


def _validate_acceptance(metrics_summary: Mapping[str, Mapping[str, EvaluationResult]]) -> None:
    sec_any_deltas: List[float] = []
    nobleed_deltas: List[float] = []
    for doc_metrics in metrics_summary.values():
        if "SectionPresence@Any" in doc_metrics:
            sec_any_deltas.append(doc_metrics["SectionPresence@Any"].deltas["value"])
        if "NoBleed%" in doc_metrics:
            nobleed_deltas.append(doc_metrics["NoBleed%"].deltas["value"])
    if sec_any_deltas and mean(sec_any_deltas) < 5.0:
        raise AssertionError("SectionPresence@Any improvement below threshold")
    if nobleed_deltas and mean(nobleed_deltas) < 15.0:
        raise AssertionError("NoBleed% improvement below threshold")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate chunking improvements")
    parser.add_argument("--corpus", type=Path, required=True, help="Path to corpus directory")
    parser.add_argument("--config", type=Path, required=True, help="Path to config file")
    parser.add_argument("--out", type=Path, default=Path("out/eval"), help="Output directory")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    config = load_config(args.config)
    run_evaluation(args.corpus, config, args.out)


if __name__ == "__main__":
    main()
