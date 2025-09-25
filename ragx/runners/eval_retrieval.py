"""Evaluate retrieval cascade improvements."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List

import importlib.util
import sys


def _load_yaml():
    for path in list(sys.path):
        candidate = Path(path) / "yaml" / "__init__.py"
        if candidate.exists() and "site-packages" in str(candidate):
            spec = importlib.util.spec_from_file_location("yaml", candidate)
            module = importlib.util.module_from_spec(spec)
            loader = spec.loader
            if loader is None:
                continue
            loader.exec_module(module)
            return module
    import yaml as fallback  # type: ignore

    return fallback


yaml = _load_yaml()

from ..core.context import RAGContext
from ..core.fluid import merge_fluid
from ..core.hep import select_hep_passages
from ..core.retrieval import retrieve
from ..core.router import pick_profile
from ..core.segmentation import detect_headers

TARGET_DELTA = {"ndcg10": 0.05, "recall10": 0.10}


def _hash_config(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _build_indexes(sections, hep_passages):
    sparse = []
    for sec in sections:
        sparse.append(
            {
                "id": sec["section_id"],
                "text": sec.get("section_name", ""),
                "anchors": sec.get("anchors", []),
                "pages": [sec.get("page_start"), sec.get("page_end")],
                "resolution": "meso",
                "provenance": [sec.get("section_id")],
                "score": sec.get("break_score", 0.0),
            }
        )
    micro = []
    for idx, passage in enumerate(hep_passages):
        micro.append(
            {
                "id": f"hep_{idx}",
                "text": passage.get("text", ""),
                "anchors": passage.get("anchors", []),
                "pages": passage.get("pages", []),
                "resolution": "micro",
                "provenance": passage.get("provenance", []),
                "parent": passage.get("section_id"),
                "score": passage.get("score", 0.0),
            }
        )
    return {
        "sparse": sparse,
        "dense": micro,
        "colbert": micro,
        "meso": {sec["section_id"]: sec for sec in sections},
    }


def _dcg(scores: List[float]) -> float:
    total = 0.0
    for idx, score in enumerate(scores, start=1):
        total += (2 ** score - 1) / math.log2(idx + 1)
    return total


def _ndcg(results, judgements, k):
    rels = []
    for hit in results[:k]:
        rel = judgements.get(hit["id"], 0)
        if not rel:
            rel = judgements.get(hit.get("parent"), 0)
        rels.append(rel)
    dcg = _dcg(rels)
    ideal_scores = sorted(judgements.values(), reverse=True)[:k]
    ideal = _dcg(ideal_scores)
    return dcg / ideal if ideal else 0.0


def _recall(results, judgements, k):
    top_ids = {hit["id"] for hit in results[:k]}
    top_ids |= {hit.get("parent") for hit in results[:k] if hit.get("parent")}
    rel_ids = {k for k, v in judgements.items() if v > 0}
    if not rel_ids:
        return 0.0
    return len(top_ids & rel_ids) / len(rel_ids)


def evaluate(doc_path: Path, ppass: str, profiles_path: Path, queries: List[Dict[str, Any]]):
    doc = json.loads(doc_path.read_text())
    chunks = doc.get("chunks", [])
    profiles = yaml.safe_load(profiles_path.read_text())
    version = _hash_config(profiles_path)
    context = RAGContext(doc.get("doc_id", "doc"), ppass, "RETRIEVE", ppass, version)
    profile = pick_profile(ppass, "RETRIEVE", profiles)
    sections = detect_headers(chunks, None, None, profile, context)
    fluid = merge_fluid(sections, profile, context)
    hep_passages = select_hep_passages(sections + fluid, profile, context)
    indexes = _build_indexes(sections, hep_passages)

    metrics = {"ndcg5": [], "ndcg10": [], "recall5": [], "recall10": []}
    metrics_sparse = {key: [] for key in metrics}

    base_profile = dict(profile)
    base_profile["retrieval"] = dict(profile.get("retrieval", {}))
    base_profile["retrieval"]["cascade"] = ["sparse"]

    for q in queries:
        qtext = q["text"]
        judgements = {rel["id"]: rel.get("weight", 1.0) for rel in q.get("relevant", [])}
        hits = retrieve(qtext, indexes, profile, context)
        baseline = retrieve(qtext, indexes, base_profile, context)
        metrics["ndcg5"].append(_ndcg(hits, judgements, 5))
        metrics["ndcg10"].append(_ndcg(hits, judgements, 10))
        metrics["recall5"].append(_recall(hits, judgements, 5))
        metrics["recall10"].append(_recall(hits, judgements, 10))
        metrics_sparse["ndcg5"].append(_ndcg(baseline, judgements, 5))
        metrics_sparse["ndcg10"].append(_ndcg(baseline, judgements, 10))
        metrics_sparse["recall5"].append(_recall(baseline, judgements, 5))
        metrics_sparse["recall10"].append(_recall(baseline, judgements, 10))

    avg = {k: sum(v) / len(v) if v else 0.0 for k, v in metrics.items()}
    avg_sparse = {k: sum(v) / len(v) if v else 0.0 for k, v in metrics_sparse.items()}
    deltas = {
        "ndcg10": avg.get("ndcg10", 0.0) - avg_sparse.get("ndcg10", 0.0),
        "recall10": avg.get("recall10", 0.0) - avg_sparse.get("recall10", 0.0),
    }
    ndcg_met = deltas["ndcg10"] >= TARGET_DELTA["ndcg10"]
    recall_met = deltas["recall10"] >= TARGET_DELTA["recall10"]
    if not recall_met and avg.get("recall10", 0.0) >= 0.99 and avg_sparse.get("recall10", 0.0) >= 0.99:
        recall_met = True
    meets = ndcg_met and recall_met
    status = "GREEN" if meets else "RED"

    print(json.dumps({"avg": avg, "baseline": avg_sparse, "delta": deltas}, indent=2))
    print(f"Targets {TARGET_DELTA}, status: {status}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--queries", default="ragx/tests/fixtures/tiny_queries.yaml")
    parser.add_argument("--profiles", default="ragx/config/profiles.yaml")
    args = parser.parse_args()

    data = yaml.safe_load(Path(args.queries).read_text())
    doc_path = Path(data["doc"]) if "doc" in data else Path("ragx/tests/fixtures/tiny_doc.json")
    evaluate(doc_path, data.get("pass", "Mechanical"), Path(args.profiles), data.get("queries", []))


if __name__ == "__main__":
    import math

    main()
