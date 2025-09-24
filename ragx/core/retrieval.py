"""Retrieval cascade implementation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .context import RAGContext
from .utils import normalize_text


def _apply_boost(text: str, boosts: Iterable[str]) -> float:
    text_lower = (text or "").lower()
    return sum(1.0 for token in boosts if token.lower() in text_lower)


def _score_documents(docs: Iterable[Dict[str, Any]], query: str, boosts: Iterable[str]) -> List[Tuple[Dict[str, Any], float]]:
    results: List[Tuple[Dict[str, Any], float]] = []
    for doc in docs or []:
        base = float(doc.get("score", 0.0))
        bonus = _apply_boost(doc.get("text", ""), boosts)
        results.append((doc, base + bonus))
    return results


def retrieve(query, indexes, profile, context: RAGContext, budget=None):
    cfg = profile.get("retrieval", {})
    cascade = cfg.get("cascade", ["sparse"])
    boosts = cfg.get("boosts_sparse", [])
    colbert_tokens = cfg.get("colbert_token_boosts", [])

    stage_scores: Dict[str, Dict[str, float]] = {}
    combined: Dict[str, Dict[str, Any]] = {}

    for stage in cascade:
        if stage == "sparse":
            docs = indexes.get("sparse", [])
            scored = _score_documents(docs, query, boosts)
        elif stage == "dense_hyde":
            docs = indexes.get("dense", [])
            hints = cfg.get("hyde_hints", "")
            scored = _score_documents(docs, query + " " + hints, [])
        elif stage == "colbert":
            docs = indexes.get("colbert", [])
            scored = _score_documents(docs, query, colbert_tokens)
        elif stage == "cross":
            docs = indexes.get("cross", [])
            scored = _score_documents(docs, query, [])
        else:
            continue

        stage_scores[stage] = {}
        for doc, score in scored:
            doc_id = doc.get("id") or doc.get("section_id")
            if not doc_id:
                continue
            entry = combined.setdefault(
                doc_id,
                {
                    "id": doc_id,
                    "text": doc.get("text", ""),
                    "anchors": doc.get("anchors", []),
                    "pages": doc.get("pages", []),
                    "resolution": doc.get("resolution", "micro"),
                    "provenance": doc.get("provenance", []),
                    "parent": doc.get("parent"),
                    "stage_scores": {},
                },
            )
            entry["text"] = entry["text"] or doc.get("text", "")
            entry["anchors"] = entry.get("anchors") or doc.get("anchors", [])
            entry["pages"] = entry.get("pages") or doc.get("pages", [])
            entry["provenance"] = entry.get("provenance") or doc.get("provenance", [])
            entry["stage_scores"][stage] = score
            stage_scores[stage][doc_id] = score

    for doc_id, entry in combined.items():
        entry["score"] = sum(entry["stage_scores"].values())

    ranked = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
    if budget is not None:
        ranked = ranked[:budget]

    for hit in ranked:
        if hit.get("parent") and hit["parent"] not in combined:
            parent = indexes.get("meso", {}).get(hit["parent"])
            if parent:
                combined[hit["parent"]] = parent

    return ranked
