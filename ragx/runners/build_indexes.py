"""CLI to build per-pass indexes."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict

from ..core.context import RAGContext
from ..core.fluid import merge_fluid
from ..core.router import pick_profile
from ..core.segmentation import detect_headers


def _load_profiles(path: Path) -> Dict[str, Any]:
    import yaml

    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _hash_config(path: Path) -> str:
    digest = hashlib.sha1(path.read_bytes()).hexdigest()
    return digest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--doc", required=True)
    parser.add_argument("--pass", dest="ppass", required=True)
    parser.add_argument("--intent", default="RETRIEVE")
    parser.add_argument("--profiles", default="ragx/config/profiles.yaml")
    parser.add_argument("--out", default="artifacts")
    args = parser.parse_args()

    doc = json.loads(Path(args.doc).read_text())
    chunks = doc.get("chunks", [])
    profiles = _load_profiles(Path(args.profiles))
    version = _hash_config(Path(args.profiles))
    context = RAGContext(doc.get("doc_id", "doc"), args.ppass, args.intent, args.ppass, version)
    profile = pick_profile(args.ppass, args.intent, profiles)

    sections = detect_headers(chunks, embeddings=None, clusters=None, profile=profile, context=context)
    fluid = merge_fluid(sections, profile, context)

    out_dir = Path(args.out) / context.doc_id / context.ppass / args.intent
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "sections.json").write_text(json.dumps(sections, indent=2))
    (out_dir / "fluid.json").write_text(json.dumps(fluid, indent=2))
    print(f"Saved sections and fluid merges to {out_dir}")


if __name__ == "__main__":
    main()
