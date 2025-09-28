"""Header controller."""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel

from backend.app.contracts.chunking import Chunk
from backend.app.contracts.headers import Header
from backend.app.util.errors import AppError

from .packages.heur.regex_bank import find_header_candidates
from .packages.join.stitcher import stitch_headers
from .packages.rechunk.by_headers import rechunk_by_headers
from .packages.repair.sequence import repair_sequence
from .packages.score.typo_features import score_typo


class HeaderJoinInternal(BaseModel):
    doc_id: str
    headers: List[Header]
    sections: Dict[str, List[str]]


def _load_chunks(chunks_artifact: str) -> List[Chunk]:
    path = Path(chunks_artifact)
    chunks: List[Chunk] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        chunks.append(Chunk(**payload))
    return chunks


def join_and_rechunk(*, doc_id: str, chunks_artifact: str) -> HeaderJoinInternal:
    chunks = _load_chunks(chunks_artifact)
    candidates = find_header_candidates(chunks)
    scored = [score_typo(candidate) for candidate in candidates]
    stitched = stitch_headers(scored)
    repaired = repair_sequence(stitched)
    sections = rechunk_by_headers(repaired, chunks)
    header_payload = {
        "doc_id": doc_id,
        "headers": [asdict(header) for header in repaired],
        "sections": sections,
    }
    Path(chunks_artifact).parent.joinpath("headers.json").write_text(
        json.dumps(header_payload, indent=2, sort_keys=True), encoding="utf-8"
    )
    return HeaderJoinInternal(doc_id=doc_id, headers=repaired, sections=sections)


def handle_header_errors(e: Exception) -> None:
    if isinstance(e, AppError):
        raise e
    raise AppError(str(e)) from e
