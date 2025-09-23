"""Pass-specific view construction and scoring."""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Dict, List, Sequence

from .instrumentation import token_count
from .rules import RuleConfig, soft_split_on_headings


@dataclass
class PassConfig:
    must_sections: Sequence[str]
    section_allowlist: Sequence[str]
    keywords: Sequence[str]
    hep_z_min: float
    length_budget_tokens: int


DEFAULT_WEIGHTS = {
    "alpha": 0.35,
    "beta": 0.25,
    "gamma": 0.2,
    "delta": 0.15,
    "epsilon": 0.05,
}


def build_views(chunks: Sequence[Dict], pass_configs: Dict[str, Dict], rule_config: Dict | RuleConfig) -> Dict[str, List[Dict]]:
    cfg = rule_config if isinstance(rule_config, RuleConfig) else RuleConfig(**rule_config)
    views: Dict[str, List[Dict]] = {}
    for pass_name, pass_cfg_dict in pass_configs.items():
        pass_cfg = PassConfig(
            must_sections=pass_cfg_dict.get("must_sections", []),
            section_allowlist=pass_cfg_dict.get("section_allowlist", []),
            keywords=pass_cfg_dict.get("keywords", []),
            hep_z_min=float(pass_cfg_dict.get("hep_z_min", -999.0)),
            length_budget_tokens=int(pass_cfg_dict.get("length_budget_tokens", 2000)),
        )
        views[pass_name] = _build_view_for_pass(chunks, pass_cfg, cfg)
    return views


def _build_view_for_pass(chunks: Sequence[Dict], pass_cfg: PassConfig, rule_cfg: RuleConfig) -> List[Dict]:
    allow = set(pass_cfg.section_allowlist or [])
    must = list(pass_cfg.must_sections or [])
    keywords = [kw.lower() for kw in pass_cfg.keywords or []]

    candidates: List[Dict] = []
    for chunk in chunks:
        if chunk.get("meta", {}).get("hep_entropy_z", 0.0) < pass_cfg.hep_z_min:
            continue
        parts = [chunk]
        if rule_cfg.soft_split_on_view and allow:
            parts = soft_split_on_headings(chunk, allow)
        for part in parts:
            part = dict(part)
            part.setdefault("meta", {})
            part["tokens"] = part.get("tokens") or token_count(part.get("text", ""))
            part["score"] = _score_chunk(part, keywords, allow)
            candidates.append(part)

    candidates.sort(key=lambda c: c.get("score", 0.0), reverse=True)

    selected: List[Dict] = []
    seen_sections: Dict[str, Dict] = {}
    token_budget = 0

    for chunk in candidates:
        section = str(chunk.get("section_number") or "")
        if section and section in seen_sections:
            continue
        if token_budget + chunk.get("tokens", 0) > pass_cfg.length_budget_tokens:
            continue
        if section and allow and section not in allow:
            continue
        selected.append(chunk)
        token_budget += chunk.get("tokens", 0)
        if section:
            seen_sections[section] = chunk

    for section in must:
        if section in seen_sections:
            continue
        best = _best_chunk_for_section(candidates, section)
        if not best:
            continue
        if token_budget + best.get("tokens", 0) > pass_cfg.length_budget_tokens:
            continue
        selected.append(best)
        token_budget += best.get("tokens", 0)
        seen_sections[section] = best

    selected = _deduplicate(selected)
    selected.sort(key=lambda c: (c.get("score", 0.0), c.get("section_number", "")), reverse=True)
    return selected


def _score_chunk(chunk: Dict, keywords: Sequence[str], allow: Sequence[str]) -> float:
    weights = DEFAULT_WEIGHTS
    text = chunk.get("text", "")
    tokens = [tok.lower() for tok in text.split()]
    score_bm25 = _bm25_score(tokens, keywords)
    score_emb = _embedding_similarity(tokens, keywords)
    section = str(chunk.get("section_number") or "")
    section_prior = 1.0 if (not allow or section in allow) else -0.5
    hep_z = chunk.get("meta", {}).get("hep_entropy_z", 0.0)
    keyword_hits = sum(text.lower().count(kw) for kw in keywords)
    return (
        weights["alpha"] * score_bm25
        + weights["beta"] * score_emb
        + weights["gamma"] * section_prior
        + weights["delta"] * hep_z
        + weights["epsilon"] * keyword_hits
    )


def _bm25_score(tokens: Sequence[str], keywords: Sequence[str]) -> float:
    if not keywords or not tokens:
        return 0.0
    counts = Counter(tokens)
    N = len(tokens)
    score = 0.0
    for kw in keywords:
        tf = counts.get(kw, 0)
        if not tf:
            continue
        score += (tf * (1.5 + 1)) / (tf + 1.5 * (1 - 0.75 + 0.75 * N / (N + 1)))
    return score


def _embedding_similarity(tokens: Sequence[str], keywords: Sequence[str]) -> float:
    if not keywords or not tokens:
        return 0.0
    tok_counts = Counter(tokens)
    key_counts = Counter(keywords)
    intersection = sum(min(tok_counts.get(word, 0), key_counts.get(word, 0)) for word in key_counts)
    denom = math.sqrt(sum(v * v for v in tok_counts.values())) * math.sqrt(
        sum(v * v for v in key_counts.values())
    )
    if denom == 0:
        return 0.0
    return intersection / denom


def _best_chunk_for_section(chunks: Sequence[Dict], section: str) -> Dict | None:
    section_chunks = [chunk for chunk in chunks if str(chunk.get("section_number") or "") == section]
    if not section_chunks:
        return None
    section_chunks.sort(key=lambda c: c.get("score", 0.0), reverse=True)
    return section_chunks[0]


def _deduplicate(chunks: Sequence[Dict]) -> List[Dict]:
    result: List[Dict] = []
    seen_texts: List[str] = []
    for chunk in chunks:
        text_lines = [line.strip() for line in chunk.get("text", "").splitlines() if line.strip()]
        joined = "\n".join(text_lines)
        if any(_line_overlap(joined, prev) >= 0.85 for prev in seen_texts):
            continue
        seen_texts.append(joined)
        result.append(chunk)
    return result


def _line_overlap(a: str, b: str) -> float:
    set_a = set(a.splitlines())
    set_b = set(b.splitlines())
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / float(len(set_a | set_b))
