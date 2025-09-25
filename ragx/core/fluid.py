"""FLUID merging for meso sections."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Sequence, Set

from .context import RAGContext
from .utils import normalize_text


def _cosine_sim(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = sum(a * a for a in vec_a) ** 0.5
    norm_b = sum(b * b for b in vec_b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _section_embedding(section: Dict[str, Any], embeddings=None):
    if embeddings is None:
        return None
    prov = section.get("provenance_embeddings")
    if prov is not None:
        return prov
    idx = section.get("start_idx")
    if idx is None:
        return None
    if idx < len(embeddings):
        return embeddings[idx]
    return None


def _section_tags(section: Dict[str, Any]) -> Set[str]:
    tags = section.get("tags") or []
    if isinstance(tags, dict):
        tags = list(tags.keys())
    normalized = {normalize_text(tag) for tag in tags if tag}
    text = section.get("section_name", "")
    normalized.update(normalize_text(token) for token in text.split())
    return {tag for tag in normalized if tag}


def _table_refs(section: Dict[str, Any]) -> Iterable[str]:
    tables = section.get("tables") or []
    if tables:
        return tables
    meta = section.get("meta", {}) if isinstance(section, dict) else {}
    return meta.get("tables", []) or []


def merge_fluid(sections, profile, context: RAGContext, embeddings=None):
    """
    Merge adjacent sections when similarity and tag constraints satisfied.
    """

    cfg = profile.get("fluid_merge", {})
    sim_threshold = cfg.get("sim_threshold", 0.8)
    must_share = {normalize_text(t) for t in cfg.get("must_share_any", [])}
    keep_tables = cfg.get("keep_tables", False)

    merged: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(sections):
        cur = dict(sections[idx])
        cur.setdefault("provenance", [cur.get("section_id")])
        cur.setdefault("pages", [cur.get("page_start")])
        cur.setdefault("anchors", cur.get("anchors", []))
        text_parts = [cur.get("text") or cur.get("section_name") or ""]
        provenance_pages = set()
        if cur.get("page_start"):
            provenance_pages.add(cur.get("page_start"))
        if cur.get("page_end"):
            provenance_pages.add(cur.get("page_end"))
        provenance_pages.update(cur.get("pages", []))
        provenance_sections = set(cur.get("provenance", []))
        anchors = list(cur.get("anchors", []))
        cur_tags = _section_tags(cur)
        tables: Set[str] = set(_table_refs(cur)) if keep_tables else set()
        j = idx + 1
        while j < len(sections):
            nxt = sections[j]
            nxt_tags = _section_tags(nxt)
            tag_overlap = (cur_tags & nxt_tags & must_share) if must_share else nxt_tags
            if must_share and not tag_overlap:
                break
            cur_emb = _section_embedding(cur, embeddings)
            nxt_emb = _section_embedding(nxt, embeddings)
            sim = _cosine_sim(cur_emb, nxt_emb) if cur_emb is not None and nxt_emb is not None else 0.0
            if sim < sim_threshold:
                break
            text_parts.append(nxt.get("text") or nxt.get("section_name") or "")
            if nxt.get("page_start"):
                provenance_pages.add(nxt.get("page_start"))
            if nxt.get("page_end"):
                provenance_pages.add(nxt.get("page_end"))
            provenance_pages.update(nxt.get("pages", []))
            provenance_sections.update([nxt.get("section_id")])
            anchors.extend(nxt.get("anchors", []))
            cur_tags.update(nxt_tags)
            if keep_tables:
                tables.update(_table_refs(nxt))
            j += 1
        text = "\n".join(part for part in text_parts if part)
        record = {
            "text": text,
            "anchors": anchors,
            "pages": sorted(p for p in provenance_pages if p),
            "provenance": sorted(provenance_sections),
            "resolution": "fluid",
        }
        if keep_tables and tables:
            record["tables"] = sorted(tables)
        merged.append(record)
        idx = max(j, idx + 1)
    return merged
