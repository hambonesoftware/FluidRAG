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
    match = re.match(r"^(?P<prefix>[A-Za-z]+)(?P<num>\d+)", label)
    if not match:
        match = re.match(r"^(?P<num>\d+)", label)
        if not match:
            return label, -1
        return "NUM", int(match.group("num"))
    return match.group("prefix"), int(match.group("num"))


def _window_text(page_text: str, start: int, end: int, padding: int = 120) -> Tuple[int, int, str]:
    win_start = max(0, start - padding)
    win_end = min(len(page_text), end + padding)
    return win_start, win_end, page_text[win_start:win_end]


def _search_methods(label: str, page_text: str, window_start: int, window_end: int) -> List[Dict[str, Any]]:
    window = page_text[window_start:window_end]
    methods: List[Dict[str, Any]] = []
    regex_pattern = re.compile(rf"{re.escape(label)}\s*(?P<text>[^\n]+)")
    match = regex_pattern.search(window)
    if match:
        methods.append(
            {
                "label": label,
                "text": _normalize_space(match.group("text")),
                "method": "regex",
                "confidence": 0.65,
            }
        )
    if not methods:
        lines = window.splitlines()
        for idx, line in enumerate(lines[:-1]):
            if label in line:
                candidate = _normalize_space(line + " " + lines[idx + 1])
                methods.append(
                    {
                        "label": label,
                        "text": candidate,
                        "method": "soft_unwrap",
                        "confidence": 0.58,
                    }
                )
                break
    if not methods and window:
        # OCR window fallback: search for uppercase sequences
        match = re.search(rf"{re.escape(label)}\s*([A-Z][A-Za-z &/]+)", window)
        if match:
            methods.append(
                {
                    "label": label,
                    "text": _normalize_space(match.group(0).replace(label, "", 1)),
                    "method": "ocr_window",
                    "confidence": 0.56,
                }
            )
    return methods


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
            log_entry = {
                "series": prefix if prefix != "NUM" else "NUMERIC",
                "gap": f"{prefix}{gap_numbers[0]}..{prefix}{gap_numbers[-1]}",
                "before": {
                    "label": before_header.label,
                    "page": before_header.page,
                    "span": before_header.span,
                },
                "after": {
                    "label": after_header.label,
                    "page": after_header.page,
                    "span": after_header.span,
                },
                "windows": 0,
                "result": [],
            }
            for missing in gap_numbers:
                label = f"{prefix}{missing}." if prefix != "NUM" else f"{missing})"
                page_index = before_header.page - 1
                page_text = pages_norm[page_index]
                start = before_header.span[1]
                end = after_header.span[0] if before_header.page == after_header.page else len(page_text)
                win_start, win_end, window = _window_text(page_text, start, end)
                token_list = tokens[page_index] if page_index < len(tokens) else []
                window_tokens = [t for t in token_list if win_start <= t.get("start", 0) <= win_end]
                log_entry["windows"] += max(1, len(window_tokens))
                candidates = _search_methods(label, page_text, win_start, win_end)
                for candidate in candidates:
                    candidate_text = candidate["text"].replace(label, "").strip()
                    canonical = _normalize_space(f"{label} {candidate_text}")
                    local_idx = _normalize_space(page_text).find(canonical)
                    if local_idx == -1:
                        continue
                    confidence = candidate["confidence"]
                    if confidence < confidence_threshold:
                        continue
                    new_header = VerifiedHeader(
                        label=label.rstrip(".)") + ("." if label.endswith(".") else ")"),
                        text=candidate_text,
                        page=before_header.page,
                        span=(local_idx, local_idx + len(canonical)),
                        verification={"status": "matched", "method": candidate["method"]},
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
