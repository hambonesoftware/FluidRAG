"""RAG passes controller."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

from backend.app.adapters.llm import LLMClient
from backend.app.contracts.chunking import Chunk
from backend.app.contracts.passes import PassResult, RetrievalHit
from backend.app.util.errors import AppError

from .packages.compose.context import compose_window
from .packages.emit.results import write_pass_results
from .packages.prompts import controls, electrical, mechanical, project_mgmt, software
from .packages.rank.fluid import flow_score
from .packages.rank.graph import graph_score
from .packages.rank.hep import energy_score
from .packages.retrieval.hybrid import retrieve_ranked


class PassJobsInternal(BaseModel):
    doc_id: str
    passes: List[PassResult]


def _load_chunks(chunks_path: Path) -> Dict[str, Chunk]:
    chunks: Dict[str, Chunk] = {}
    if not chunks_path.exists():
        return chunks
    for line in chunks_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        chunk = Chunk(**payload)
        chunks[chunk.chunk_id] = chunk
    return chunks


def _load_embeddings(path: Path) -> Dict[str, List[float]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _load_sections(path: Path) -> Dict[str, List[str]]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("sections", {})


def _summarize(prompt: str, context: str, client: LLMClient) -> str:
    messages = [
        {"role": "system", "content": "You are a precise technical summarizer."},
        {"role": "user", "content": f"{prompt}\n\nContext:\n{context}"},
    ]
    response = client.chat(model="stub-model", messages=messages)
    choice = response.get("choices", [{}])[0]
    message = choice.get("message", {})
    return message.get("content", "")


def run_all(*, doc_id: str, rechunk_artifact: str) -> PassJobsInternal:
    artifact_path = Path(rechunk_artifact)
    base_dir = artifact_path.parent
    chunks = _load_chunks(base_dir / "chunks.jsonl")
    embeddings = _load_embeddings(base_dir / "embeddings.json")
    sections = _load_sections(artifact_path)
    chunk_texts = {cid: chunk.text for cid, chunk in chunks.items()}

    prompts = [
        mechanical.Prompt(),
        electrical.Prompt(),
        software.Prompt(),
        controls.Prompt(),
        project_mgmt.Prompt(),
    ]

    client = LLMClient()
    pass_results: List[PassResult] = []
    for prompt_obj in prompts:
        retrieved = retrieve_ranked(query=prompt_obj.question, chunk_texts=chunk_texts, embeddings=embeddings, limit=5)
        hits: List[RetrievalHit] = []
        for chunk_id, base_score in retrieved:
            chunk = chunks.get(chunk_id)
            if not chunk:
                continue
            aggregated = (base_score + flow_score(chunk) + energy_score(chunk) + graph_score(chunk)) / 4
            hits.append(
                RetrievalHit(
                    chunk_id=chunk_id,
                    score=aggregated,
                    text=chunk.text,
                    metadata={"section": next((name for name, ids in sections.items() if chunk_id in ids), "Document")},
                )
            )
        hits = sorted(hits, key=lambda hit: hit.score, reverse=True)[:5]
        context = compose_window(chunks, [hit.chunk_id for hit in hits])
        answer = _summarize(prompt_obj.question, context, client)
        pass_results.append(PassResult(name=prompt_obj.name, hits=hits, answer={"text": answer}))

    write_pass_results(doc_id, pass_results)
    return PassJobsInternal(doc_id=doc_id, passes=pass_results)


def handle_pass_errors(e: Exception) -> None:
    if isinstance(e, AppError):
        raise e
    raise AppError(str(e)) from e
