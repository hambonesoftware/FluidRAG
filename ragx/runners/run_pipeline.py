"""Run the full RAG pipeline."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from ..core.context import RAGContext
from ..core.fluid import merge_fluid
from ..core.graphrag import micrograph
from ..core.hep import select_hep_passages
from ..core.retrieval import retrieve
from ..core.router import pick_profile
from ..core.segmentation import detect_headers


def _load_profiles(path: Path) -> Dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hash_config(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()


def _build_indexes(sections, hep_passages):
    sparse = []
    meso_map = {}
    for sec in sections:
        meso_map[sec["section_id"]] = sec
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
    indexes = {
        "sparse": sparse + micro,
        "dense": micro,
        "colbert": micro,
        "cross": micro,
        "meso": meso_map,
    }
    return indexes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True)
    parser.add_argument("--pass", dest="ppass", required=True)
    parser.add_argument("--intent", default="RETRIEVE")
    parser.add_argument("--query", default="")
    parser.add_argument("--profiles", default="ragx/config/profiles.yaml")
    parser.add_argument("--graph", action="store_true")
    args = parser.parse_args()

    doc = json.loads(Path(args.doc).read_text())
    chunks = doc.get("chunks", [])
    profiles = _load_profiles(Path(args.profiles))
    version = _hash_config(Path(args.profiles))
    context = RAGContext(doc.get("doc_id", "doc"), args.ppass, args.intent, args.ppass, version)
    profile = pick_profile(args.ppass, args.intent, profiles)

    sections = detect_headers(chunks, embeddings=None, clusters=None, profile=profile, context=context)
    fluid = merge_fluid(sections, profile, context)
    hep_passages = select_hep_passages(sections + fluid, profile, context)
    indexes = _build_indexes(sections, hep_passages)
    hits = retrieve(args.query, indexes, profile, context)

    result = {
        "context": context.__dict__,
        "sections": sections,
        "fluid": fluid,
        "hep": hep_passages,
        "hits": hits,
    }

    if args.graph:
        graph = micrograph(args.query, sections + fluid, profile, context)
        result["graph"] = graph

    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
