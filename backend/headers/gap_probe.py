"""Diagnostics for logging gaps in appendix/numeric header sequences."""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

from backend.headers.header_scan import HeaderCandidate
from backend.uf_chunker import UFChunk


_APPENDIX_AN_RE = re.compile(r"^\s*([A-Z])\s*(\d{1,3})(?:[.)]|\b)", re.IGNORECASE)
_APPENDIX_ALN_RE = re.compile(r"^\s*([A-Z])\s*\.\s*(\d{1,3})", re.IGNORECASE)
_APPENDIX_TOP_RE = re.compile(r"^\s*(Appendix|Annex)\s+([A-Z])\b", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"^\s*(\d{1,3})\)")


@dataclass(frozen=True)
class _Series:
    kind: str
    prefix: str


def _canonical_label(label: str) -> str:
    label = (label or "").strip()
    if not label:
        return ""
    match = _APPENDIX_ALN_RE.match(label)
    if match:
        letter = match.group(1).upper()
        number = int(match.group(2))
        return f"{letter}.{number}"
    match = _APPENDIX_AN_RE.match(label)
    if match:
        letter = match.group(1).upper()
        number = int(match.group(2))
        return f"{letter}{number}"
    match = _APPENDIX_TOP_RE.match(label)
    if match:
        prefix = match.group(1).title()
        letter = match.group(2).upper()
        return f"{prefix} {letter}"
    match = _NUMERIC_RE.match(label)
    if match:
        return f"{int(match.group(1))})"
    return label


def _series_for_label(label: str) -> Optional[Tuple[_Series, int]]:
    label = (label or "").strip()
    if not label:
        return None
    match = _APPENDIX_ALN_RE.match(label)
    if match:
        series = _Series("appendix_sub_AlN", match.group(1).upper())
        return series, int(match.group(2))
    match = _APPENDIX_AN_RE.match(label)
    if match:
        series = _Series("appendix_sub_AN", match.group(1).upper())
        return series, int(match.group(2))
    match = _APPENDIX_TOP_RE.match(label)
    if match:
        prefix = match.group(1).title()
        letter = match.group(2).upper()
        series = _Series("appendix_top", prefix)
        index = ord(letter) - ord("A") + 1
        return series, index
    match = _NUMERIC_RE.match(label)
    if match:
        series = _Series("numeric", "")
        return series, int(match.group(1))
    return None


def _render_token(series: _Series, index: int) -> str:
    if series.kind == "appendix_sub_AlN":
        return f"{series.prefix}.{index}"
    if series.kind == "appendix_sub_AN":
        return f"{series.prefix}{index}"
    if series.kind == "appendix_top":
        letter = chr(ord("A") + index - 1)
        return f"{series.prefix} {letter}"
    if series.kind == "numeric":
        return f"{index})"
    return str(index)


def _sanitize_token(token: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", token).strip("_") or token


def _pattern_for(series: _Series, index: int) -> re.Pattern[str]:
    if series.kind == "appendix_sub_AlN":
        return re.compile(rf"{re.escape(series.prefix)}\s*\.\s*{index}\b", re.IGNORECASE)
    if series.kind == "appendix_sub_AN":
        return re.compile(rf"{re.escape(series.prefix)}\s*{index}(?:[.)]|\b)", re.IGNORECASE)
    if series.kind == "appendix_top":
        letter = chr(ord("A") + index - 1)
        return re.compile(rf"{re.escape(series.prefix)}\s+{letter}\b", re.IGNORECASE)
    if series.kind == "numeric":
        return re.compile(rf"{index}\)")
    return re.compile(re.escape(str(index)))


def _font_stats(tokens: Sequence[Mapping[str, object]]) -> Tuple[float, float]:
    values = [float(token.get("font_size") or 0.0) for token in tokens if token.get("font_size") is not None]
    if not values:
        return 0.0, 1.0
    mean = sum(values) / len(values)
    variance = sum((val - mean) ** 2 for val in values) / len(values)
    std = math.sqrt(variance) or 1.0
    return mean, std


def _font_sigma(font_size: float, stats: Tuple[float, float]) -> float:
    mean, std = stats
    if std == 0:
        return 0.0
    return (font_size - mean) / std


def _first_reason(reasons: Sequence[str]) -> Optional[str]:
    for reason in reasons:
        if reason:
            return reason
    return None


class GapProbeLogger:
    """Collects structured telemetry when numbering gaps are detected."""

    def __init__(
        self,
        doc_id: str,
        pages_raw: Sequence[str],
        pages_norm: Sequence[str],
        tokens_per_page: Sequence[Sequence[Mapping[str, object]]],
        uf_chunks: Sequence[UFChunk],
        start_scores: Mapping[str, float],
        stop_scores: Mapping[str, float],
        candidates: Sequence[HeaderCandidate],
    ) -> None:
        self.doc_id = doc_id
        self.pages_raw = list(pages_raw)
        self.pages_norm = list(pages_norm)
        self.tokens_per_page = list(tokens_per_page)
        self.uf_chunks = list(uf_chunks)
        self.start_scores = dict(start_scores)
        self.stop_scores = dict(stop_scores)
        self.entries: List[Dict[str, object]] = []
        self._page_font_stats: Dict[int, Tuple[float, float]] = {}
        self._candidate_map: Dict[int, List[HeaderCandidate]] = defaultdict(list)
        for idx, tokens in enumerate(self.tokens_per_page, start=1):
            self._page_font_stats[idx] = _font_stats(tokens)
        for candidate in candidates:
            self._candidate_map[candidate.page].append(candidate)

    def _page_candidates(self, page: int) -> List[str]:
        observed: List[str] = []
        for candidate in sorted(self._candidate_map.get(page, []), key=lambda c: (c.line_index, c.start_char)):
            canon = _canonical_label(candidate.label)
            if canon:
                observed.append(canon)
        return observed

    def _candidate_emitted(self, page: int, token: str) -> bool:
        canon = _canonical_label(token)
        for candidate in self._candidate_map.get(page, []):
            if _canonical_label(candidate.label) == canon:
                return True
        return False

    def _find_token_style(
        self,
        page: int,
        pattern: re.Pattern[str],
    ) -> Optional[Dict[str, object]]:
        tokens = self.tokens_per_page[page - 1] if 0 < page <= len(self.tokens_per_page) else []
        stats = self._page_font_stats.get(page, (0.0, 1.0))
        for token in tokens:
            text = str(token.get("text") or "")
            if pattern.search(text):
                font_size = float(token.get("font_size") or 0.0)
                indent = float(token.get("indent") or 0.0)
                return {
                    "bold": bool(token.get("bold", False)),
                    "font_pt": font_size,
                    "left_x": indent,
                    "font_sigma_rank": _font_sigma(font_size, stats),
                }
        return None

    def _find_chunk(
        self,
        page: int,
        pattern: re.Pattern[str],
    ) -> Optional[UFChunk]:
        for chunk in self.uf_chunks:
            if chunk.page != page:
                continue
            if pattern.search(chunk.text or ""):
                return chunk
        return None

    def _analyze_page_text(
        self,
        page: int,
        pattern: re.Pattern[str],
    ) -> Optional[Dict[str, object]]:
        if page < 1 or page > len(self.pages_raw):
            return None
        text = self.pages_raw[page - 1] or ""
        match = pattern.search(text)
        if not match:
            return None
        start, end = match.span()
        pre_fragment = text[max(0, start - 40) : start]
        post_fragment = text[end : min(len(text), end + 40)]
        line_start = start == 0 or text[start - 1] == "\n"
        paragraph_break = text[max(0, start - 2) : start] == "\n\n" or (start == 0)
        return {
            "match": match.group(0),
            "start": start,
            "end": end,
            "pre": pre_fragment,
            "post": post_fragment,
            "line_start": line_start,
            "paragraph_break": paragraph_break,
        }

    def _page_bridge(self, page: int, token_pattern: re.Pattern[str]) -> Dict[str, object]:
        prev_tail = None
        next_head = None
        bridged = False
        if page > 1 and self.pages_raw[page - 2]:
            prev_tail = self.pages_raw[page - 2][-80:]
            if token_pattern.search(prev_tail):
                bridged = True
        if page < len(self.pages_raw) and self.pages_raw[page]:
            next_head = self.pages_raw[page][:80]
            if token_pattern.search(next_head):
                bridged = True
        return {
            "bridged": bridged,
            "prev_page_tail": prev_tail if bridged else None,
            "next_page_head": next_head if bridged else None,
        }

    def _uf_regex_scan(self, page: int, tokens: Sequence[Tuple[str, re.Pattern[str]]]) -> List[Dict[str, object]]:
        hits: List[Dict[str, object]] = []
        for chunk in self.uf_chunks:
            if chunk.page != page:
                continue
            for token, pattern in tokens:
                match = pattern.search(chunk.text or "")
                if not match:
                    continue
                text = match.group(0).strip()
                chunk_text = chunk.text or ""
                start = match.start()
                line_start = start == 0 or chunk_text[max(0, start - 1)] == "\n"
                hits.append(
                    {
                        "token": token,
                        "chunk_idx": chunk.id,
                        "hit": text,
                        "line_start": line_start,
                        "bold": bool((chunk.style or {}).get("bold")),
                        "font_pt": float((chunk.style or {}).get("font_size") or 0.0),
                    }
                )
        return hits

    def _entropy_for(self, chunk: Optional[UFChunk]) -> Dict[str, float]:
        if not chunk:
            return {}
        return {
            "text": float((chunk.entropy or {}).get("H_tkn", 0.0)),
            "structure_jump": float(self.start_scores.get(chunk.id, 0.0)),
            "space": float((chunk.style or {}).get("indent", 0.0)),
        }

    def detect_gaps(
        self,
        final_headers: Sequence[Mapping[str, object]],
    ) -> None:
        headers_by_page: Dict[int, List[Mapping[str, object]]] = defaultdict(list)
        for header in final_headers:
            page = int(header.get("page", 0) or 0)
            if page <= 0:
                continue
            headers_by_page[page].append(header)
        for page, page_headers in headers_by_page.items():
            ordered = sorted(page_headers, key=lambda h: (int(h.get("span", (0, 0))[0]), _canonical_label(str(h.get("label", "")))))
            observed_candidates = [_canonical_label(str(h.get("label", ""))) or str(h.get("label", "")) for h in ordered]
            for idx in range(len(ordered) - 1):
                prev = ordered[idx]
                nxt = ordered[idx + 1]
                prev_label = str(prev.get("label", ""))
                next_label = str(nxt.get("label", ""))
                prev_series = _series_for_label(prev_label)
                next_series = _series_for_label(next_label)
                if not prev_series or not next_series:
                    continue
                prev_key, prev_index = prev_series
                next_key, next_index = next_series
                if prev_key != next_key:
                    continue
                if next_index - prev_index <= 1:
                    continue
                missing_indices = list(range(prev_index + 1, next_index))
                self._log_gap(
                    page=page,
                    prev_header=prev,
                    prev_idx=idx,
                    series=prev_key,
                    missing_indices=missing_indices,
                    observed=observed_candidates,
                )

    def _log_gap(
        self,
        *,
        page: int,
        prev_header: Mapping[str, object],
        prev_idx: int,
        series: _Series,
        missing_indices: Sequence[int],
        observed: Sequence[str],
    ) -> None:
        tokens = [(_render_token(series, index), _pattern_for(series, index)) for index in missing_indices]
        candidate_stage: Dict[str, object] = {"reasons": []}
        style_map: Dict[str, Optional[Dict[str, object]]] = {}
        entropy_text: Dict[str, float] = {}
        entropy_struct: Dict[str, float] = {}
        entropy_space: Dict[str, float] = {}
        uf_hits = self._uf_regex_scan(page, tokens)
        uf_hits_by_token = defaultdict(list)
        for hit in uf_hits:
            uf_hits_by_token[hit.get("token")].append(hit)
        splitters = {
            "appendix_inline_fired": False,
            "subsection_inline_fired": False,
            "pre_text_fragment": None,
            "post_text_fragment": None,
        }
        bridge_info = self._page_bridge(page, tokens[0][1] if tokens else re.compile(r"")) if tokens else {
            "bridged": False,
            "prev_page_tail": None,
            "next_page_head": None,
        }
        action = "manual_review"
        first_missing_token: Optional[str] = None
        for offset, (token, pattern) in enumerate(tokens):
            emitted = self._candidate_emitted(page, token)
            emitted_key = f"emitted_{_sanitize_token(token)}"
            candidate_stage[emitted_key] = emitted
            reasons: List[str] = []
            presence = self._analyze_page_text(page, pattern)
            style_info = self._find_token_style(page, pattern)
            style_map[token] = style_info
            chunk = self._find_chunk(page, pattern)
            entropy = self._entropy_for(chunk)
            if entropy:
                entropy_text[token] = entropy.get("text", 0.0)
                entropy_struct[token] = entropy.get("structure_jump", 0.0)
                entropy_space[token] = entropy.get("space", 0.0)
            if presence:
                if splitters["pre_text_fragment"] is None:
                    splitters["pre_text_fragment"] = presence.get("pre")
                    splitters["post_text_fragment"] = presence.get("post")
                if not presence.get("line_start"):
                    reasons.append("no_line_start_flag")
                if not presence.get("paragraph_break"):
                    reasons.append("no_paragraph_break")
                if style_info and style_info.get("font_sigma_rank") is not None and style_info["font_sigma_rank"] < -0.5:
                    reasons.append("style_drop?")
                if series.kind.startswith("appendix") and not presence.get("line_start"):
                    splitters["appendix_inline_fired"] = True
                if series.kind == "appendix_sub_AlN" and not presence.get("line_start"):
                    splitters["subsection_inline_fired"] = True
            else:
                reasons.append("not_in_page_text")
            if not emitted and offset > 0 and first_missing_token:
                reasons.append(f"gap_guard ({first_missing_token} missing)")
            if not emitted and not first_missing_token:
                first_missing_token = token
            if not emitted:
                if "no_line_start_flag" in reasons or "no_paragraph_break" in reasons:
                    action = "inline_split_or_para_boundary"
                elif "not_in_page_text" in reasons and action == "manual_review":
                    action = "verify_page_text"
            candidate_stage["reasons"].append({"token": token, "why_not": reasons})
        inline_fired = bool(splitters.get("appendix_inline_fired") or splitters.get("subsection_inline_fired"))
        prev_label = str(prev_header.get("label", ""))
        prev_text = str(prev_header.get("text", ""))
        entry = {
            "event": "gap_probe",
            "doc": self.doc_id,
            "page": page,
            "prev_header": {
                "text": f"{prev_label} {prev_text}".strip(),
                "idx": prev_idx,
            },
            "expected_next": [token for token, _ in tokens],
            "observed_candidates": list(observed),
            "uf_regex_scan": [
                {key: value for key, value in hit.items() if key != "token"}
                for hit in uf_hits
            ],
            "candidate_stage": candidate_stage,
            "splitters": splitters,
            "pagebreak_bridge": bridge_info,
            "style_at_token": {token: style_map.get(token) for token, _ in tokens},
            "entropy": {
                "text": entropy_text,
                "structure_jump": entropy_struct,
                "space": entropy_space,
            },
            "gate": {
                "applied": True,
                "parent_child_rule": False,
                "table_context_rule": False,
                "page_budget": False,
            },
            "decision": "not_emitted_at_candidate_stage",
            "action_suggested": action,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.entries.append(entry)
        reason_top = None
        if candidate_stage.get("reasons"):
            reason_top = _first_reason(candidate_stage["reasons"][0].get("why_not", []))
        self._append_tsv_row(
            page=page,
            prev=_canonical_label(prev_label) or prev_label,
            expected=[token for token, _ in tokens],
            observed=list(observed),
            candidate_stage=candidate_stage,
            uf_hits=uf_hits_by_token,
            inline_fired=inline_fired,
            reason_top=reason_top or "",
        )

    def _append_tsv_row(
        self,
        *,
        page: int,
        prev: str,
        expected: Sequence[str],
        observed: Sequence[str],
        candidate_stage: Mapping[str, object],
        uf_hits: Mapping[str, Sequence[Mapping[str, object]]],
        inline_fired: bool,
        reason_top: str,
    ) -> None:
        if not hasattr(self, "_tsv_rows"):
            self._tsv_rows: List[Dict[str, object]] = []
            self._tsv_tokens: List[str] = []
        for token in expected:
            if token not in self._tsv_tokens:
                self._tsv_tokens.append(token)
        self._tsv_rows.append(
            {
                "page": page,
                "prev": prev,
                "expected": expected,
                "observed": observed,
                "candidate_stage": dict(candidate_stage),
                "uf_hits": {token: len(hits) for token, hits in uf_hits.items()},
                "inline_fired": inline_fired,
                "reason_top": reason_top,
            }
        )

    def write(self, output_dir: Path) -> None:
        jsonl_path = output_dir / "gap_probes.jsonl"
        tsv_path = output_dir / "gap_probes.tsv"
        with jsonl_path.open("w", encoding="utf-8") as handle:
            for entry in self.entries:
                json.dump(entry, handle, ensure_ascii=False)
                handle.write("\n")
        rows: List[Dict[str, object]] = getattr(self, "_tsv_rows", [])
        tokens: List[str] = getattr(self, "_tsv_tokens", [])
        header = ["page", "prev", "next_expected", "found_on_page"]
        for token in tokens:
            header.append(f"emitted_{_sanitize_token(token)}")
        header.append("inline_split_fired")
        for token in tokens:
            header.append(f"uf_hit_{_sanitize_token(token)}")
        header.append("reason_top")
        with tsv_path.open("w", encoding="utf-8") as handle:
            handle.write("\t".join(header) + "\n")
            for row in rows:
                values: List[str] = [
                    str(row["page"]),
                    str(row["prev"]),
                    "|".join(row["expected"]),
                    ",".join(row["observed"]),
                ]
                stage = row["candidate_stage"]
                for token in tokens:
                    key = f"emitted_{_sanitize_token(token)}"
                    emitted = stage.get(key)
                    values.append("1" if emitted else "0")
                values.append("1" if row["inline_fired"] else "0")
                uf_map = row["uf_hits"]
                for token in tokens:
                    values.append("1" if uf_map.get(token) else "0")
                values.append(str(row["reason_top"]))
                handle.write("\t".join(values) + "\n")

    def as_list(self) -> List[Dict[str, object]]:
        return list(self.entries)


__all__ = ["GapProbeLogger", "_canonical_label"]

