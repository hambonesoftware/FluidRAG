"""Emit pass results."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import List

from backend.app.adapters.storage import storage
from backend.app.contracts.passes import PassResult


def write_pass_results(doc_id: str, results: List[PassResult]) -> Path:
    payload = {
        "doc_id": doc_id,
        "passes": [
            {
                "name": result.name,
                "hits": [asdict(hit) for hit in result.hits],
                "answer": result.answer,
            }
            for result in results
        ],
    }
    return storage.write_json(f"{doc_id}/passes.json", payload)
