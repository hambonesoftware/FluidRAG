"""Retrieval cascade implementation."""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .context import RAGContext
from .utils import normalize_text


def _apply_boost(text: str, boosts: Iterable[str]) -> float:
    text_lower = (text or "").lower()
    return sum(1.0 for token in boosts if token.lower() in text_lower)


def _lexical_overlap(query: str, text: str) -> float:
    q_tokens = {normalize_text(tok) for tok in query.split() if tok.strip()}
    t_tokens = {normalize_text(tok) for tok in text.split() if tok.strip()}
    if not q_tokens or not t_tokens:
        return 0.0
    overlap = len(q_tokens & t_tokens)
    return overlap / math.sqrt(len(q_tokens) * len(t_tokens))


def _hyde_hypotheses(query: str, hints: str) -> List[str]:
    hints = (hints or "").strip()
    if not hints:
        return [query]
    template_a = f"{hints} Query: {query}".strip()
    template_b = f"{hints} Focus: {query}".strip()
    return [template_a, template_b][:2]


def _colbert_emulation(query: str, text: str, boosts: Sequence[str]) -> float:
    query_tokens = [normalize_text(tok) for tok in query.split() if tok]
    text_tokens = [normalize_text(tok) for tok in text.split() if tok]
    if not query_tokens or not text_tokens:
        return 0.0
    boost_set = {normalize_text(tok) for tok in boosts}
    score = 0.0
    for qtok in query_tokens:
        token_match = 0.0
        for ttok in text_tokens:
            if not ttok:
                continue
            if qtok == ttok:
                token_match = max(token_match, 1.0)
            elif qtok in ttok or ttok in qtok:
                token_match = max(token_match, 0.5)
        if qtok in boost_set:
            token_match *= 1.25
        score += token_match
    return score / len(query_tokens)


def _cross_encoder_score(query: str, text: str) -> float:
    # Lightweight proxy using combined lexical overlap and length penalty.
    overlap = _lexical_overlap(query, text)
    if not text:
        return 0.0
    penalty = min(len(text.split()) / 200.0, 1.0)
    return overlap * (1.0 - 0.2 * penalty)


def _score_documents(docs: Iterable[Dict[str, Any]], scores: Iterable[float]) -> List[Tuple[Dict[str, Any], float]]:
    return [(doc, score) for doc, score in zip(docs, scores)]


def retrieve(query, indexes, profile, context: RAGContext, budget=None):
    cfg = profile.get("retrieval", {})
    cascade = cfg.get("cascade", ["sparse"])
    boosts = cfg.get("boosts_sparse", [])
    colbert_tokens = cfg.get("colbert_token_boosts", [])

    stage_rank = {stage: idx for idx, stage in enumerate(cascade)}
    combined: Dict[str, Dict[str, Any]] = {}

    for stage in cascade:
        docs = []
        scores: List[float] = []
        if stage == "sparse":
            docs = list(indexes.get("sparse", []))
            for doc in docs:
                base = float(doc.get("score", 0.0))
                bonus = _apply_boost(doc.get("text", ""), boosts)
                scores.append(base + bonus)
        elif stage == "dense_hyde":
            docs = list(indexes.get("dense", []))
            hypos = _hyde_hypotheses(query, cfg.get("hyde_hints", ""))
            for doc in docs:
                text = doc.get("text", "")
                hypo_score = max(_lexical_overlap(hypo, text) for hypo in hypos)
                scores.append(float(doc.get("score", 0.0)) * 0.3 + hypo_score)
        elif stage == "colbert":
            docs = list(indexes.get("colbert", []))
            for doc in docs:
                text = doc.get("text", "")
                scores.append(_colbert_emulation(query, text, colbert_tokens))
        elif stage == "cross":
            docs = list(indexes.get("cross", [])) or list(indexes.get("colbert", []))
            for doc in docs:
                text = doc.get("text", "")
                scores.append(_cross_encoder_score(query, text))
        else:
            continue

        for doc, score in _score_documents(docs, scores):
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
                    "stage_tag": stage,
                },
            )
            entry["text"] = entry["text"] or doc.get("text", "")
            entry["anchors"] = entry.get("anchors") or doc.get("anchors", [])
            entry["pages"] = entry.get("pages") or doc.get("pages", [])
            entry["provenance"] = entry.get("provenance") or doc.get("provenance", [])
            entry["parent"] = entry.get("parent") or doc.get("parent")
            entry["stage_scores"][stage] = max(score, entry["stage_scores"].get(stage, 0.0))
            if stage_rank.get(stage, 0) >= stage_rank.get(entry["stage_tag"], -1):
                entry["stage_tag"] = stage

    for entry in combined.values():
        entry["score"] = sum(entry["stage_scores"].values())

    ranked = sorted(combined.values(), key=lambda x: (x["score"], -stage_rank.get(x["stage_tag"], 0)), reverse=True)
    if budget is not None:
        ranked = ranked[:budget]

    parent_guard: List[Dict[str, Any]] = []
    seen_ids = {hit["id"] for hit in ranked}
    for hit in list(ranked):
        parent_id = hit.get("parent")
        if not parent_id or parent_id in seen_ids:
            continue
        parent_doc = (indexes.get("meso") or {}).get(parent_id)
        if not parent_doc:
            continue
        guard_entry = {
            "id": parent_id,
            "text": parent_doc.get("section_name", ""),
            "anchors": parent_doc.get("anchors", []),
            "pages": [parent_doc.get("page_start"), parent_doc.get("page_end")],
            "resolution": "meso",
            "provenance": [parent_doc.get("section_id")],
            "parent": None,
            "stage_scores": {"parent_guard": hit["score"]},
            "score": hit["score"],
            "stage_tag": "parent_guard",
        }
        parent_guard.append(guard_entry)
        seen_ids.add(parent_id)

    ranked.extend(parent_guard)
    return ranked
