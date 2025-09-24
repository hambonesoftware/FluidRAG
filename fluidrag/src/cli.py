from __future__ import annotations

import argparse
import json
from pathlib import Path

from fluidrag.config import load_config
from fluidrag.src.chunking.standard import Chunk, StandardChunker
from fluidrag.src.graph.build import build_graph
from fluidrag.src.graph.query import augment_with_graph
from fluidrag.src.qa.report import QAReport
from fluidrag.src.retrieval.search import search_standard
from fluidrag.src.routing.router import Router
from fluidrag.src.scoring.features import compute_scores


def _load_chunk_records(path: Path):
    result = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            payload = json.loads(line)
            result.append(Chunk(**payload))
    return result


def cmd_chunk(args: argparse.Namespace) -> None:
    config = load_config()
    chunker = StandardChunker()
    chunks = chunker.chunk_file(args.doc, args.doc_id)
    output_dir = Path(args.output or f"fluidrag/data/artifacts/chunks/{args.doc_id}.standard.jsonl")
    chunker.write_chunks(chunks, output_dir)
    print(f"Wrote {len(chunks)} chunks to {output_dir}")


def cmd_score(args: argparse.Namespace) -> None:
    config = load_config()
    path = Path(args.input or f"fluidrag/data/artifacts/chunks/{args.doc_id}.standard.jsonl")
    chunks = _load_chunk_records(path)
    compute_scores(chunks, config)
    path.write_text("\n".join(json.dumps(chunk.__dict__, ensure_ascii=False) for chunk in chunks) + "\n", encoding="utf-8")
    print(f"Scored {len(chunks)} chunks")


def cmd_graph(args: argparse.Namespace) -> None:
    config = load_config()
    path = Path(args.input or f"fluidrag/data/artifacts/chunks/{args.doc_id}.standard.jsonl")
    chunks = _load_chunk_records(path)
    compute_scores(chunks, config)
    build_graph(args.doc_id, chunks, Path("fluidrag/data/artifacts/graph"), config)
    print(f"Graph built for {args.doc_id}")


def cmd_search(args: argparse.Namespace) -> None:
    config = load_config()
    path = Path(args.input or f"fluidrag/data/artifacts/chunks/{args.doc_id}.standard.jsonl")
    chunks = _load_chunk_records(path)
    router = Router(config)
    decision = router.decide(args.q)
    view = args.view or decision.view
    hits = search_standard(args.q, chunks, config, view=view, topk=args.topk)
    for hit in hits:
        print(json.dumps({"chunk_id": hit.chunk_id, "score": hit.score, "stage": hit.stage, "text": hit.text[:120]}, ensure_ascii=False))
    if args.use_graph or decision.use_graph:
        context = augment_with_graph(args.q, args.doc_id, Path("fluidrag/data/artifacts/graph"))
        if context:
            print("Graph summaries:")
            for summary in context.summaries:
                print(json.dumps({"node_id": summary.node_id, "summary": summary.attributes.get("summary")}, ensure_ascii=False))


def cmd_qa(args: argparse.Namespace) -> None:
    config = load_config()
    path = Path(args.input or f"fluidrag/data/artifacts/chunks/{args.doc_id}.standard.jsonl")
    chunks = _load_chunk_records(path)
    report = QAReport(Path("fluidrag/data/artifacts/reports"))
    result = report.generate(args.doc_id, chunks)
    print(json.dumps(result, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FluidRAG CLI")
    sub = parser.add_subparsers(dest="command")

    chunk_cmd = sub.add_parser("chunk", help="Chunk a document")
    chunk_cmd.add_argument("--doc", required=True)
    chunk_cmd.add_argument("--doc_id", required=True)
    chunk_cmd.add_argument("--output")
    chunk_cmd.set_defaults(func=cmd_chunk)

    score_cmd = sub.add_parser("score", help="Score chunks")
    score_cmd.add_argument("--doc_id", required=True)
    score_cmd.add_argument("--input")
    score_cmd.set_defaults(func=cmd_score)

    graph_cmd = sub.add_parser("graph", help="Build graph")
    graph_cmd.add_argument("--doc_id", required=True)
    graph_cmd.add_argument("--input")
    graph_cmd.set_defaults(func=cmd_graph)

    search_cmd = sub.add_parser("search", help="Search chunks")
    search_cmd.add_argument("--doc_id", required=True)
    search_cmd.add_argument("--q", required=True)
    search_cmd.add_argument("--view")
    search_cmd.add_argument("--topk", type=int, default=10)
    search_cmd.add_argument("--input")
    search_cmd.add_argument("--use_graph", action="store_true")
    search_cmd.set_defaults(func=cmd_search)

    qa_cmd = sub.add_parser("qa", help="Generate QA report")
    qa_cmd.add_argument("--doc_id", required=True)
    qa_cmd.add_argument("--input")
    qa_cmd.set_defaults(func=cmd_qa)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return
    args.func(args)


if __name__ == "__main__":
    main()
