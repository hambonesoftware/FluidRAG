"""Selection helpers for section headers."""
from __future__ import annotations

from typing import Callable, Dict, Iterable, List

from .header_match import APPENDIX_RE, NUMERIC_RE, classify_line
from .header_score import THRESHOLD, score_candidate
from .text_normalize import normalize_for_headers


def _caps_ratio(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for ch in letters if ch.isupper()) / len(letters)


def _should_apply_units_penalty(text: str) -> bool:
    stripped = normalize_for_headers(text)
    if NUMERIC_RE.match(stripped):
        return False
    if APPENDIX_RE.match(stripped):
        return False
    return True


def _style_snapshot(line: Dict, caps_ratio: float) -> Dict[str, float | bool | None]:
    return {
        "font_size": line.get("font_size"),
        "bold": bool(line.get("bold")),
        "font_sigma_rank": float(line.get("font_sigma_rank") or 0.0),
        "caps_ratio": float(caps_ratio),
    }


def _decide(meets_threshold: bool, is_numeric: bool, is_appendix: bool, style: Dict) -> str:
    if meets_threshold:
        return "selected"
    if (is_numeric or is_appendix) and (
        style.get("bold") or float(style.get("font_sigma_rank") or 0.0) >= 0.5
    ):
        return "selected_fallback"
    return "below_threshold"


def select_headers(
    lines: Iterable[Dict],
    units_present_fn: Callable[[str], bool],
) -> List[Dict]:
    """Return the subset of ``lines`` that meet the deterministic threshold."""

    selections: List[Dict] = []

    for line in lines:
        raw_text = line.get("text_norm", "")
        norm_text = normalize_for_headers(raw_text)
        caps_ratio = line.get("caps_ratio") or _caps_ratio(norm_text)
        classification = classify_line(norm_text, caps_ratio)
        if classification["kind"] == "none":
            continue

        features = line.get("features", {})
        score, parts = score_candidate(classification["kind"], features)

        is_numeric = bool(NUMERIC_RE.match(norm_text))
        is_appendix = bool(APPENDIX_RE.match(norm_text))

        parts = {key: float(val) for key, val in parts.items()}
        parts["units_penalty_applied"] = False

        if units_present_fn(norm_text) and _should_apply_units_penalty(norm_text):
            if not (is_numeric or is_appendix):
                score -= 0.6
                parts["units_penalty"] = -0.6
                parts["units_penalty_applied"] = True

        meets_threshold = score >= THRESHOLD
        style = _style_snapshot(line, caps_ratio)
        decision = _decide(meets_threshold, is_numeric, is_appendix, style)
        record = {
            **line,
            **classification,
            "header_norm": norm_text,
            "score": float(score),
            "partials": parts,
            "meets_threshold": meets_threshold,
            "decision": decision,
            "is_numeric": is_numeric,
            "is_appendix": is_appendix,
            "style": style,
            "caps_ratio": caps_ratio,
        }
        selections.append(record)

    return [record for record in selections if record["decision"].startswith("selected")]


__all__ = ["select_headers"]
