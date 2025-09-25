"""Retrieval cascade implementation."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple

from .context import RAGContext


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
        if entry["stage_scores"]:
            best_stage = max(entry["stage_scores"], key=entry["stage_scores"].get)
        else:
            best_stage = "sparse"
        entry["stage_tag"] = best_stage

    ranked = sorted(combined.values(), key=lambda x: x["score"], reverse=True)
    if budget is not None:
        ranked = ranked[:budget]

    meso_index = indexes.get("meso", {})
    expanded: List[Dict[str, Any]] = []
    seen_ids = set()
    for hit in ranked:
        expanded.append(hit)
        seen_ids.add(hit["id"])
        parent_id = hit.get("parent")
        if not parent_id or parent_id in seen_ids:
            continue
        parent_section = meso_index.get(parent_id)
        if not parent_section:
            continue
        parent_hit = {
            "id": parent_id,
            "text": parent_section.get("section_name") or parent_section.get("text", ""),
            "anchors": parent_section.get("anchors", []),
            "pages": [
                page
                for page in [parent_section.get("page_start"), parent_section.get("page_end")]
                if page is not None
            ],
            "resolution": parent_section.get("resolution", "meso"),
            "provenance": [parent_section.get("section_id")],
            "parent": None,
            "stage_scores": {"coverage": hit["stage_scores"].get(hit["stage_tag"], hit.get("score", 0.0))},
            "score": hit.get("score", 0.0),
            "stage_tag": "coverage",
        }
        expanded.append(parent_hit)
        seen_ids.add(parent_id)

    return expanded
