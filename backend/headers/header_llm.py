from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Tuple


@dataclass
class VerifiedHeader:
    label: str
    text: str
    page: int
    span: Tuple[int, int]
    verification: Dict[str, Any]
    source: str = "llm"
    confidence: float = 0.8


@dataclass
class VerifiedHeaders:
    headers: List[VerifiedHeader] = field(default_factory=list)
    repair_log: List[Dict[str, Any]] = field(default_factory=list)

    def by_label(self) -> Dict[str, VerifiedHeader]:
        return {header.label: header for header in self.headers}

    def sorted(self) -> List[VerifiedHeader]:
        return sorted(self.headers, key=lambda h: (h.page, h.span[0]))

    def add(self, header: VerifiedHeader) -> None:
        self.headers.append(header)

    def extend(self, headers: Iterable[VerifiedHeader]) -> None:
        for header in headers:
            self.add(header)


HEADER_REGEX = re.compile(r"^(?P<label>(?:A\d+\.|\d+\)))\s*(?P<text>.+)$")


def build_header_prompt(pages_norm: List[str]) -> List[Dict[str, str]]:
    sections = []
    for idx, page in enumerate(pages_norm, start=1):
        sections.append(f"Page {idx}:\n{page}")
    prompt = "\n\n".join(sections)
    return [
        {"role": "system", "content": "You are a diligent header extraction assistant."},
        {"role": "user", "content": prompt},
    ]


def _extract_headers_from_page(page_text: str, page_number: int) -> List[Dict[str, Any]]:
    headers: List[Dict[str, Any]] = []
    for line in page_text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = HEADER_REGEX.match(line)
        if not match:
            continue
        headers.append(
            {
                "label": match.group("label"),
                "text": match.group("text").strip(),
                "page": page_number,
            }
        )
    return headers


def call_llm(messages: List[Dict[str, str]]) -> str:
    if not messages:
        raise ValueError("No messages provided to LLM call")
    user_content = messages[-1]["content"]
    pages = re.split(r"^Page \d+:", user_content, flags=re.MULTILINE)
    headers: List[Dict[str, Any]] = []
    # The first split element is empty string prior to first page marker.
    page_marker_iter = re.finditer(r"^Page (?P<page>\d+):", user_content, flags=re.MULTILINE)
    page_numbers = [int(match.group("page")) for match in page_marker_iter]
    page_sections = [section.strip() for section in pages[1:]]
    for idx, page_text in enumerate(page_sections):
        page_no = page_numbers[idx] if idx < len(page_numbers) else idx + 1
        headers.extend(_extract_headers_from_page(page_text, page_no))
    payload = {"headers": headers}
    return "```json\n" + json.dumps(payload, indent=2) + "\n```"


def parse_fenced_outline(text: str) -> Dict[str, Any]:
    fence_match = re.search(r"```json\n(?P<body>.*?)```", text, flags=re.DOTALL)
    if not fence_match:
        raise ValueError("LLM response missing ```json fence")
    body = fence_match.group("body").strip()
    try:
        return json.loads(body)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM response JSON invalid") from exc


def _normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def verify_headers(headers_json: Dict[str, Any], pages_norm: List[str], pages_raw: Optional[List[str]] = None) -> VerifiedHeaders:
    verified = VerifiedHeaders()
    for entry in headers_json.get("headers", []):
        label = entry.get("label")
        text = entry.get("text", "").strip()
        page = int(entry.get("page", 1))
        if not label or page < 1 or page > len(pages_norm):
            continue
        canonical = _normalize_space(f"{label} {text}")
        page_text = pages_norm[page - 1]
        page_compact = _normalize_space(page_text)
        idx = page_compact.find(canonical)
        verification: Dict[str, Any]
        span: Tuple[int, int]
        if idx != -1:
            verification = {"status": "matched", "method": "normalized"}
            span = (idx, idx + len(canonical))
        else:
            raw_text = pages_raw[page - 1] if pages_raw and page - 1 < len(pages_raw) else page_text
            raw_idx = raw_text.find(label)
            if raw_idx != -1:
                verification = {"status": "matched", "method": "raw"}
                span = (raw_idx, raw_idx + len(label) + len(text) + 1)
            else:
                verification = {"status": "not_found"}
                span = (0, 0)
        verified.add(
            VerifiedHeader(
                label=label,
                text=text,
                page=page,
                span=span,
                verification=verification,
                source="llm",
                confidence=0.8 if verification.get("status") == "matched" else 0.4,
            )
        )
    return verified


def _label_series(label: str) -> Tuple[str, int]:
    cleaned = (label or "").strip()
    if not cleaned:
        return "", -1
    numeric = re.match(r"^(?P<num>\d+)\)", cleaned)
    if numeric:
        return "NUM", int(numeric.group("num"))
    appendix = re.match(r"(?i)^(appendix|annex)\s+([A-Z])", cleaned)
    if appendix:
        prefix = appendix.group(1).upper()
        letter = appendix.group(2).upper()
        return prefix, ord(letter) - ord("A") + 1
    base = cleaned.rstrip(".)")
    dotted = re.match(r"^(?P<prefix>[A-Z])\.(?P<num>\d+)$", base)
    if dotted:
        return dotted.group("prefix").upper(), int(dotted.group("num"))
    simple = re.match(r"^(?P<prefix>[A-Z])(?P<num>\d+)$", base)
    if simple:
        return simple.group("prefix").upper(), int(simple.group("num"))
    generic = re.match(r"^(?P<prefix>[A-Za-z]+)(?P<num>\d+)$", base)
    if generic:
        return generic.group("prefix").upper(), int(generic.group("num"))
    return cleaned.upper(), -1


def _window_text(page_text: str, start: int, end: int, padding: int = 120) -> Tuple[int, int, str]:
    win_start = max(0, start - padding)
    win_end = min(len(page_text), end + padding)
    return win_start, win_end, page_text[win_start:win_end]


def _search_candidates(label: str, page_text: str, window_start: int, window_end: int) -> List[Dict[str, Any]]:
    window = page_text[window_start:window_end]
    candidates: List[Dict[str, Any]] = []
    regex_pattern = re.compile(rf"{re.escape(label)}\s*(?P<text>[^\n]+)")
    match = regex_pattern.search(window)
    if match:
        candidates.append(
            {
                "label": label,
                "text": _normalize_space(match.group("text")),
                "method": "regex",
                "confidence": 0.68,
            }
        )
    lines = window.splitlines()
    for idx, line in enumerate(lines[:-1]):
        stripped = line.strip()
        if stripped == label.rstrip(".)") or stripped.startswith(label):
            next_line = lines[idx + 1].strip()
            if next_line:
                candidates.append(
                    {
                        "label": label,
                        "text": _normalize_space(next_line),
                        "method": "header_resegment",
                        "confidence": 0.62,
                    }
                )
        if label in line and idx + 1 < len(lines):
            joined = _normalize_space(line + " " + lines[idx + 1])
            candidates.append(
                {
                    "label": label,
                    "text": joined.replace(label, "", 1).strip(),
                    "method": "soft_unwrap+regex",
                    "confidence": 0.6,
                }
            )
            break
    if window:
        ocr_match = re.search(rf"{re.escape(label)}\s*([A-Z][A-Za-z &/]+)", window)
        if ocr_match:
            candidates.append(
                {
                    "label": label,
                    "text": _normalize_space(ocr_match.group(0).replace(label, "", 1)),
                    "method": "ocr_window",
                    "confidence": 0.56,
                }
            )
    seen: set[Tuple[str, str]] = set()
    unique: List[Dict[str, Any]] = []
    for candidate in candidates:
        key = (candidate["text"], candidate["method"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def _verify_local_match(label: str, text: str, page_text: str, window_start: int, window_end: int) -> Optional[Tuple[int, int, str]]:
    window = page_text[window_start:window_end]
    pattern = re.compile(rf"{re.escape(label)}\s*{re.escape(text)}", re.IGNORECASE)
    match = pattern.search(window)
    if not match:
        return None
    start = window_start + match.start()
    end = window_start + match.end()
    canonical = _normalize_space(page_text[start:end])
    return start, end, canonical


def _series_name(prefix: str) -> str:
    if prefix == "NUM":
        return "NUMERIC"
    if prefix in {"APPENDIX", "ANNEX"}:
        return prefix
    return prefix.upper()


def _infer_label_pattern(label: str) -> str:
    if not label:
        return "generic"
    if re.match(r"^\d+\)$", label):
        return "numeric"
    if re.match(r"(?i)^(appendix|annex)\s+[A-Z]$", label):
        return "appendix_top"
    if re.match(r"^[A-Z]\d+\.$", label):
        return "appendix_sub_AN"
    if re.match(r"^[A-Z]\.\d+$", label):
        return "appendix_sub_AlN"
    return "generic"


def _format_missing_label(prefix: str, number: int, pattern: str) -> str:
    if pattern == "numeric" or prefix == "NUM":
        return f"{number})"
    if pattern == "appendix_top" and prefix in {"APPENDIX", "ANNEX"}:
        letter = chr(ord("A") + number - 1)
        return f"{prefix.title()} {letter}"
    if pattern == "appendix_sub_AlN":
        return f"{prefix}.{number}"
    if pattern == "appendix_sub_AN":
        return f"{prefix}{number}."
    return f"{prefix}{number}."


def aggressive_sequence_repair(
    verified: VerifiedHeaders,
    pages_norm: List[str],
    tokens: List[List[Dict[str, Any]]],
    confidence_threshold: float = 0.55,
) -> VerifiedHeaders:
    sequences: Dict[str, List[Tuple[int, VerifiedHeader]]] = {}
    for header in verified.headers:
        prefix, num = _label_series(header.label)
        if num == -1:
            continue
        sequences.setdefault(prefix, []).append((num, header))
    repaired = VerifiedHeaders(headers=list(verified.headers), repair_log=list(verified.repair_log))
    for prefix, entries in sequences.items():
        entries.sort(key=lambda item: item[0])
        numbers = [num for num, _ in entries]
        for idx in range(len(numbers) - 1):
            current_num = numbers[idx]
            next_num = numbers[idx + 1]
            if next_num - current_num <= 1:
                continue
            gap_numbers = list(range(current_num + 1, next_num))
            before_header = entries[idx][1]
            after_header = entries[idx + 1][1]
            pattern_type = _infer_label_pattern(before_header.label)
            if pattern_type == "generic":
                pattern_type = _infer_label_pattern(after_header.label)
            log_entry = {
                "series": _series_name(prefix),
                "gap": f"{_format_missing_label(prefix, gap_numbers[0], pattern_type)}..{_format_missing_label(prefix, gap_numbers[-1], pattern_type)}",
                "before": {
                    "label": before_header.label,
                    "text": before_header.text,
                    "page": before_header.page,
                    "span": before_header.span,
                },
                "after": {
                    "label": after_header.label,
                    "text": after_header.text,
                    "page": after_header.page,
                    "span": after_header.span,
                },
                "windows": 0,
                "result": [],
            }
            for missing in gap_numbers:
                label = _format_missing_label(prefix, missing, pattern_type)
                page_index = before_header.page - 1
                page_text = pages_norm[page_index]
                start = before_header.span[1]
                end = after_header.span[0] if before_header.page == after_header.page else len(page_text)
                win_start, win_end, _ = _window_text(page_text, start, end)
                token_window = []
                if 0 <= page_index < len(tokens):
                    token_window = [
                        token
                        for token in tokens[page_index]
                        if win_start <= int(token.get("start", 0)) <= win_end
                    ]
                log_entry["windows"] += max(1, len(token_window))
                candidates = _search_candidates(label, page_text, win_start, win_end)
                for candidate in candidates:
                    verification = _verify_local_match(label, candidate["text"], page_text, win_start, win_end)
                    if not verification:
                        continue
                    span_start, span_end, canonical = verification
                    confidence = candidate["confidence"]
                    if confidence < confidence_threshold:
                        continue
                    normalized_label = label
                    new_header = VerifiedHeader(
                        label=normalized_label,
                        text=candidate["text"],
                        page=before_header.page,
                        span=(span_start, span_end),
                        verification={"status": "matched", "method": candidate["method"], "canonical": canonical},
                        source="repair",
                        confidence=confidence,
                    )
                    repaired.add(new_header)
                    log_entry["result"].append(
                        {
                            "label": new_header.label,
                            "text": new_header.text,
                            "page": new_header.page,
                            "span": new_header.span,
                            "method": candidate["method"],
                            "confidence": confidence,
                        }
                    )
                    break
            if log_entry["result"]:
                repaired.repair_log.append(log_entry)
    repaired.headers.sort(key=lambda h: (h.page, h.span[0], h.label))
    return repaired


__all__ = [
    "build_header_prompt",
    "call_llm",
    "parse_fenced_outline",
    "verify_headers",
    "aggressive_sequence_repair",
    "VerifiedHeader",
    "VerifiedHeaders",
]
